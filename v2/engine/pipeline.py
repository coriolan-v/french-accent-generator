"""Visitor recording -> same words, same voice, thick French accent."""
import time

import librosa
import numpy as np
import torch
from kokoro import KPipeline
from transformers import pipeline as hf_pipeline

from accent import frenchify
from vc import SR as VC_SR, VoiceConverter

KOKORO_SR = 24000
MAX_PHONEMES = 400   # Kokoro accepts up to 510 per call


class FrenchAccentPipeline:
    def __init__(self, device='cuda'):
        self.asr = hf_pipeline('automatic-speech-recognition', model='openai/whisper-large-v3-turbo',
                               torch_dtype=torch.float16, device=device)
        self.tts = KPipeline(lang_code='a', repo_id='hexgrad/Kokoro-82M', device=device)
        self.vc = VoiceConverter(device)

    def transcribe(self, wav16k):
        out = self.asr({'raw': wav16k, 'sampling_rate': 16000},
                       generate_kwargs={'language': 'en', 'task': 'transcribe'})
        return out['text'].strip()

    def speak(self, phonemes, voice, speed):
        chunks, cur = [], ''
        for word in phonemes.split(' '):
            if len(cur) + len(word) + 1 > MAX_PHONEMES:
                chunks.append(cur)
                cur = ''
            cur = f'{cur} {word}'.strip()
        chunks.append(cur)
        audio = [r.audio.numpy() for c in chunks if c for r in self.tts.generate_from_tokens(c, voice=voice, speed=speed)]
        return np.concatenate(audio) if audio else np.zeros(0, np.float32)

    def run(self, wav, sr, strength=3, voice='ff_siwis', speed=0.9, steps=25, text=None,
            cfg_rate=0.3, ref_seconds=10):
        # Weak guidance + a shorter visitor reference keep more of the guide's accent (confirm_settings.py).
        t = {}
        t0 = time.perf_counter()
        wav = librosa.to_mono(wav.T) if wav.ndim > 1 else wav
        wav, _ = librosa.effects.trim(wav.astype(np.float32), top_db=35)
        if len(wav) < sr * 0.3:
            raise ValueError('No speech detected')
        wav16 = librosa.resample(wav, orig_sr=sr, target_sr=16000)
        ref = librosa.resample(wav, orig_sr=sr, target_sr=VC_SR)

        if text is None:
            text = self.transcribe(wav16)
        t['transcribe'] = time.perf_counter() - t0
        if not text:
            raise ValueError('No words recognised')

        phonemes_en, _ = self.tts.g2p(text)
        phonemes_fr = frenchify(phonemes_en, strength)
        guide = self.speak(phonemes_fr, voice, speed)
        t['tts'] = time.perf_counter() - t0 - sum(t.values())

        guide22 = librosa.resample(guide, orig_sr=KOKORO_SR, target_sr=VC_SR)
        out = self.vc.convert(guide22, ref, steps=steps, cfg_rate=cfg_rate, max_ref_seconds=ref_seconds)
        t['convert'] = time.perf_counter() - t0 - sum(t.values())

        out = out / (np.abs(out).max() + 1e-6) * 0.9
        return {
            'text': text, 'phonemes_en': phonemes_en, 'phonemes_fr': phonemes_fr,
            'guide': guide22, 'audio': out.astype(np.float32), 'sr': VC_SR, 'timings': t,
        }
