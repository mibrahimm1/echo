import pyaudio
import wave
import requests
import io
import os
import uuid
import asyncio
import edge_tts
from pydub import AudioSegment
from vad_helper import VadGenerator

# Configuration
FORMAT = pyaudio.paInt16
CHANNELS = 1
RATE = 48000
FRAME_DURATION_MS = 30
CHUNK_SIZE = int(RATE * FRAME_DURATION_MS / 1000)

INPUT_DEVICE_INDEX = 1 # Match your USB Device ID
SESSION_ID = str(uuid.uuid4())
SERVER_URL = os.getenv("SERVER_URL", "https://your-new-optimized-server.onrender.com/interact")

print(f"Session ID: {SESSION_ID}")

async def generate_tts(text, output_file):
    """Generates TTS using edge-tts locally"""
    voice = "en-US-AriaNeural" # or en-GB-SoniaNeural
    communicate = edge_tts.Communicate(text, voice)
    await communicate.save(output_file)

def play_audio_file(filename):
    """Plays audio file (converts MP3 to WAV for PyAudio)"""
    try:
        # Load MP3/Other and convert to WAV in memory or temp file
        # PyAudio needs WAV 
        sound = AudioSegment.from_file(filename)
        
        # Ensure correct rate for Pi
        if sound.frame_rate != RATE:
            sound = sound.set_frame_rate(RATE)
            
        p = pyaudio.PyAudio()
        stream = p.open(format=p.get_format_from_width(sound.sample_width),
                        channels=sound.channels,
                        rate=sound.frame_rate,
                        output=True,
                        output_device_index=INPUT_DEVICE_INDEX)
        
        stream.write(sound.raw_data)
        stream.stop_stream()
        stream.close()
        p.terminate()
    except Exception as e:
        print(f"Playback error: {e}")

def main():
    if os.path.exists("welcome.wav"):
        play_audio_file("welcome.wav")
        
    p = pyaudio.PyAudio()
    vad = VadGenerator(mode=3, frame_duration_ms=FRAME_DURATION_MS, sample_rate=RATE)
    
    try:
        stream = p.open(format=FORMAT, channels=CHANNELS, rate=RATE, input=True, input_device_index=INPUT_DEVICE_INDEX, frames_per_buffer=CHUNK_SIZE)
        print("Listening...")
        
        frames = []
        recording = False
        silence_counter = 0
        MAX_SILENCE_CHUNKS = 25 
        
        while True:
            data = stream.read(CHUNK_SIZE, exception_on_overflow=False)
            is_speech = vad.is_speech(data)
            
            if not recording:
                if is_speech:
                    print("Speaking...")
                    recording = True
                    frames = [data]
                    silence_counter = 0
            else:
                frames.append(data)
                if is_speech:
                    silence_counter = 0
                else:
                    silence_counter += 1
                
                if silence_counter > MAX_SILENCE_CHUNKS:
                    print("Processing...")
                    recording = False
                    
                    # 1. Prepare Audio
                    buffer = io.BytesIO()
                    with wave.open(buffer, 'wb') as wf:
                        wf.setnchannels(CHANNELS)
                        wf.setsampwidth(p.get_sample_size(FORMAT))
                        wf.setframerate(RATE)
                        wf.writeframes(b''.join(frames))
                    buffer.seek(0)
                    
                    # 2. Send to Server (Receive JSON)
                    try:
                        files = {'file': ('input.wav', buffer, 'audio/wav')}
                        data = {'session_id': SESSION_ID}
                        response = requests.post(SERVER_URL, files=files, data=data, timeout=60)
                        
                        if response.status_code == 200:
                            resp_json = response.json()
                            text = resp_json.get("text", "")
                            print(f"Response: {text}")
                            
                            # 3. Generate TTS Locally
                            if text:
                                temp_tts = "temp_response.mp3"
                                asyncio.run(generate_tts(text, temp_tts))
                                play_audio_file(temp_tts)
                                if os.path.exists(temp_tts):
                                    os.remove(temp_tts)
                        else:
                            print(f"Error: {response.text}")
                    except Exception as e:
                        print(f"Error: {e}")
                    
                    print("Listening...")
                    
    except KeyboardInterrupt:
        pass
    finally:
        p.terminate()

if __name__ == "__main__":
    main()
