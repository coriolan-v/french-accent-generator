import sounddevice as sd
import numpy as np
import scipy.io.wavfile as wav
import whisper
import os
from elevenlabs import ElevenLabs

# ============ CONFIG ============
ELEVEN_API_KEY = "sk_c7165d09cbc276348039b414fa2d1bd1b912c8024db7d2b9"   # <-- put your ElevenLabs key
INPUT_CLIP = "input.wav"
OUTPUT_CLIP = "output.wav"
SAMPLE_RATE = 16000

# Init ElevenLabs + Whisper
client = ElevenLabs(api_key=ELEVEN_API_KEY)
stt_model = whisper.load_model("small")  # "tiny" = faster, "small" = better accuracy

# ---------- Record function ----------
def record_audio(filename, duration=5):
    print(f"🎤 Recording {duration}s...")
    audio = sd.rec(int(duration * SAMPLE_RATE), samplerate=SAMPLE_RATE,
                   channels=1, dtype='int16')
    sd.wait()
    wav.write(filename, SAMPLE_RATE, audio)
    print(f"✅ Saved {filename}")

# ---------- Main Loop ----------
def run_loop(voice_id="pNInz6obpgDQGcFmaJgB"):  
    """
    Default voice is 'Antoine' (a French voice). 
    You can replace with any other ElevenLabs voice ID you like.
    """
    print("\n=== Ready! Press Enter to record a sentence. Type 'q' + Enter to quit. ===")
    while True:
        cmd = input(">> ")
        if cmd.lower().startswith("q"):
            break

        # Step 1: record input
        record_audio(INPUT_CLIP, duration=5)

        # Step 2: transcribe to English text
        result = stt_model.transcribe(INPUT_CLIP, fp16=False)
        text = result["text"].strip()
        print("📝 Transcribed:", text)

        # Step 3: wrap text in French language tag to force accent
        tts_text = f'<lang xml:lang="fr-FR">{text}</lang>'

        # Step 4: synthesize with ElevenLabs multilingual model
        audio_stream = client.text_to_speech.convert(
            voice_id=voice_id,
            model_id="eleven_multilingual_v2",
            text=tts_text,
        )

        # Step 5: save audio
        with open(OUTPUT_CLIP, "wb") as f:
            for chunk in audio_stream:
                f.write(chunk)

        print("🔊 Playing back with French accent...")
        os.system(f'start {OUTPUT_CLIP}')  # Windows playback

# ---------- Run ----------
if __name__ == "__main__":
    run_loop()