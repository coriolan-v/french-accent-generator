import sounddevice as sd
import soundfile as sf
from TTS.api import TTS

SAMPLE_RATE = 16000
INPUT_CLIP = "input.wav"
OUTPUT_CLIP = "french_accent.wav"

# ---------- Step 1: Record ----------
def record_audio(filename, duration=5):
    print(f"🎤 Recording {duration}s...")
    audio = sd.rec(int(duration * SAMPLE_RATE), samplerate=SAMPLE_RATE, channels=1, dtype="float32")
    sd.wait()
    sf.write(filename, audio, SAMPLE_RATE)
    print(f"✅ Saved recording: {filename}")

# ---------- Step 2: Generate with French accent ----------
def generate_accented_tts(text):
    # Pretrained French TTS model (can speak English text with French accent)
    tts = TTS(model_name="tts_models/fr/css10/vits", progress_bar=False, gpu=False)

    print(f"🗣️ Generating with French accent: {text}")
    tts.tts_to_file(text=text, file_path=OUTPUT_CLIP)
    print(f"✅ Saved accented speech: {OUTPUT_CLIP}")

    # Play result (Windows)
    import os
    os.system(f'start {OUTPUT_CLIP}')

# ---------- Main ----------
if __name__ == "__main__":
    # Step 1: Record
    record_audio(INPUT_CLIP, duration=6)

    # 👉 Instead of transcription, we can hardcode or ask user to type
    sentence = input("Type the sentence you just said (so TTS can repeat it):\n> ")

    # Step 2: Generate French-accented replay
    generate_accented_tts(sentence)
