import os
import uuid
import json
from fastapi import FastAPI, UploadFile, File, HTTPException, Form
from groq import Groq
from dotenv import load_dotenv

load_dotenv()

app = FastAPI()

@app.get("/")
async def health_check():
    return {"status": "ok"}

# Initialize Groq Client
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
if not GROQ_API_KEY:
    print("Warning: GROQ_API_KEY not set in .env")

client = Groq(api_key=GROQ_API_KEY)

# System Prompt
SYSTEM_PROMPT = "You are Echo, a helpful, concise, and intelligent AI assistant. Answer the user's questions clearly and briefly. Do not ramble."

# Session Management
SESSIONS_DIR = "sessions"
os.makedirs(SESSIONS_DIR, exist_ok=True)

def get_session_history(session_id: str):
    path = os.path.join(SESSIONS_DIR, f"{session_id}.json")
    if os.path.exists(path):
        try:
            with open(path, "r") as f:
                return json.load(f)
        except:
            return []
    return []

def save_session_history(session_id: str, history: list):
    path = os.path.join(SESSIONS_DIR, f"{session_id}.json")
    with open(path, "w") as f:
        json.dump(history, f)

@app.post("/interact")
async def interact(file: UploadFile = File(...), session_id: str = Form(...)):
    """
    Low Latency Endpoint:
    Receives Audio -> Returns Text (JSON).
    TTS is handled by the client.
    """
    temp_audio_filename = f"temp_{uuid.uuid4()}.wav"
    try:
        # Step 0: Save UploadFile to disk
        content = await file.read()
        
        with open(temp_audio_filename, "wb") as buffer:
            buffer.write(content)

        # Step 1: Speech-to-Text (Groq Whisper)
        with open(temp_audio_filename, "rb") as f:
            transcription = client.audio.transcriptions.create(
                file=(temp_audio_filename, f.read()),
                model="whisper-large-v3",
                response_format="json",
                language="en",
                temperature=0.0
            )
        
        user_text = transcription.text
        print(f"User Transcribed ({session_id}): {user_text}")

        # Cleanup input file
        if os.path.exists(temp_audio_filename):
             os.remove(temp_audio_filename)

        if not user_text:
             raise HTTPException(status_code=400, detail="Could not transcribe audio")

        # Step 2: Text Generation (Groq LLaMA 3) with History
        history = get_session_history(session_id)
        
        messages = [{"role": "system", "content": SYSTEM_PROMPT}]
        messages.extend(history)
        messages.append({"role": "user", "content": user_text})

        completion = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=messages,
            temperature=0.7,
            max_tokens=150,
        )
        
        text_response = completion.choices[0].message.content
        print(f"Groq Response ({session_id}): {text_response}")

        # Update History
        history.append({"role": "user", "content": user_text})
        history.append({"role": "assistant", "content": text_response})
        save_session_history(session_id, history)

        # Return JSON
        return {
            "text": text_response,
            "session_id": session_id
        }

    except Exception as e:
        print(f"Error processing request: {e}")
        if os.path.exists(temp_audio_filename):
            try:
                os.remove(temp_audio_filename)
            except:
                pass
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
