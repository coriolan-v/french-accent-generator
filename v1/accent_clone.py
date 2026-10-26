import sounddevice as sd
import numpy as np
import scipy.io.wavfile as wav
import whisper
import os
import requests
from elevenlabs import ElevenLabs

# ============ CONFIG ============
ELEVEN_API_KEY = os.environ.get("ELEVENLABS_API_KEY", "")
SETUP_CLIP = "setup.wav"
INPUT_CLIP = "input.wav"
OUTPUT_CLIP = "output.wav"
SAMPLE_RATE = 16000

# Init ElevenLabs + Whisper
client = ElevenLabs(api_key=ELEVEN_API_KEY)
stt_model = whisper.load_model("small")  # "tiny" faster, "base/small" more accurate

# ---------- Record function ----------
def record_audio(filename, duration=5):
    print(f"🎤 Recording {duration}s...")
    audio = sd.rec(int(duration * SAMPLE_RATE), samplerate=SAMPLE_RATE,
                   channels=1, dtype='int16')
    sd.wait()
    wav.write(filename, SAMPLE_RATE, audio)
    print(f"✅ Saved {filename}")

# ---------- Step 1: Create instant clone via REST ----------
def create_clone():
    url = "https://api.elevenlabs.io/v1/voices/add"
    headers = {"xi-api-key": ELEVEN_API_KEY}

    with open(SETUP_CLIP, "rb") as f:
        files = {"files": f}
        data = {
            "name": "MyFrenchClone",
            "description": "User's cloned voice"
        }
        resp = requests.post(url, headers=headers, files=files, data=data)

    if resp.status_code != 200:
        raise RuntimeError(f"Clone failed: {resp.status_code} {resp.text}")

    result = resp.json()
    print("✅ Clone created:", result)
    return result["voice_id"]

# ---------- Step 2: Loop: record → transcribe → French accent ----------
def run_loop(voice_id):
    print("\n=== Ready! Press Enter to record a sentence. Type 'q' + Enter to quit. ===")
    while True:
        cmd = input(">> ")
        if cmd.lower().startswith("q"):
            break

        record_audio(INPUT_CLIP, duration=5)

        # Transcribe
        result = stt_model.transcribe(INPUT_CLIP, fp16=False)
        text = result["text"].strip()
        print("📝 Transcribed:", text)

        # Synthesize with French accent instruction
        tts_text = f"Read this in English with a French accent: {text}"

        audio_stream = client.text_to_speech.convert(
            voice_id=voice_id,
            model_id="eleven_multilingual_v2",
            text=tts_text,
        )

        # Save audio
        with open(OUTPUT_CLIP, "wb") as f:
            for chunk in audio_stream:
                f.write(chunk)

        print("🔊 Playing back in French accent...")
        os.system(f'start {OUTPUT_CLIP}')  # Windows playback

# ---------- Main ----------
if __name__ == "__main__":
    # Step 1: Record a short setup clip
    input("=== Voice Setup ===\nPress Enter when ready...")
    record_audio(SETUP_CLIP, duration=8)

    # Step 2: Create the voice clone
    voice_id = create_clone()

    # Step 3: Run interactive loop
    run_loop(voice_id)
