"""Compare accent methods on test voices. Writes WAVs to scratch/compare/ and prints a score table.

  current  : Kokoro accent guide -> Seed-VC v1 (via the running server at :8000)
  guide:X  : Seed-VC v2 accent transfer from reference X -> Seed-VC v1 back to the visitor's voice

Scores: sim = voice similarity to the visitor (CAM++ cosine), fr = Whisper's P(French) language score,
heard = what Whisper hears (intelligibility).
"""
import base64
import glob
import io
import os
import sys
import time
import warnings

warnings.filterwarnings('ignore')
import librosa  # noqa: E402
import numpy as np  # noqa: E402
import requests  # noqa: E402
import soundfile as sf  # noqa: E402
import torch  # noqa: E402
import torchaudio  # noqa: E402
from transformers import WhisperForConditionalGeneration, WhisperProcessor  # noqa: E402

from vc import SR, AccentTransfer, VoiceConverter  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, 'scratch', 'compare')
GUIDES = ['3-worse-ref-3', '4-worse-reference-15s', 'french8_style_reference']


def load(path):
    wav, sr = sf.read(path, dtype='float32')
    wav = wav.mean(1) if wav.ndim > 1 else wav
    wav, _ = librosa.effects.trim(wav, top_db=35)
    return librosa.resample(wav, orig_sr=sr, target_sr=SR)


class Scorer:
    def __init__(self, vc):
        self.vc = vc
        self.proc = WhisperProcessor.from_pretrained('openai/whisper-small')
        self.asr = WhisperForConditionalGeneration.from_pretrained('openai/whisper-small', torch_dtype=torch.float16).cuda()
        tok = self.proc.tokenizer
        self.sot = tok.convert_tokens_to_ids('<|startoftranscript|>')
        self.en, self.fr = tok.convert_tokens_to_ids('<|en|>'), tok.convert_tokens_to_ids('<|fr|>')

    def embed(self, wav22):
        w16 = torch.from_numpy(librosa.resample(wav22, orig_sr=SR, target_sr=16000))[None].float().cuda()
        fb = torchaudio.compliance.kaldi.fbank(w16, num_mel_bins=80, dither=0, sample_frequency=16000)
        with torch.inference_mode():
            return torch.nn.functional.normalize(self.vc.campplus((fb - fb.mean(0, keepdim=True))[None])[0], dim=0)

    @torch.inference_mode()
    def score(self, wav22, ref_emb):
        w16 = librosa.resample(wav22, orig_sr=SR, target_sr=16000)
        feats = self.proc(w16, sampling_rate=16000, return_tensors='pt').input_features.cuda().half()
        logits = self.asr(input_features=feats, decoder_input_ids=torch.tensor([[self.sot]]).cuda()).logits[0, -1].float()
        p_fr = torch.softmax(logits[[self.en, self.fr]], 0)[1].item()
        ids = self.asr.generate(feats, language='en', task='transcribe', max_new_tokens=120)
        heard = self.proc.batch_decode(ids, skip_special_tokens=True)[0].strip()
        return float(self.embed(wav22) @ ref_emb), p_fr, heard


def current_method(path):
    with open(path, 'rb') as f:
        r = requests.post('http://127.0.0.1:8000/api/convert', files={'audio': f},
                          data={'strength': 3, 'voice': 'ff_siwis', 'steps': 25}, timeout=120).json()
    wav, sr = sf.read(io.BytesIO(base64.b64decode(r['audio'])), dtype='float32')
    return librosa.resample(wav, orig_sr=sr, target_sr=SR) if sr != SR else wav


def main(visitors):
    os.makedirs(OUT, exist_ok=True)
    vc = VoiceConverter()
    at = AccentTransfer()
    sc = Scorer(vc)
    for g in GUIDES:
        gw = load(os.path.join(ROOT, 'scratch', 'refs', g + '.wav'))
        at.set_guide(g, gw)
        _, p_fr, heard = sc.score(gw, sc.embed(gw))
        print(f'guide {g}: fr={p_fr:.2f}  "{heard[:70]}"')

    rows = []
    for path in visitors:
        name = os.path.splitext(os.path.basename(path))[0]
        v = load(path)[:SR * 15]
        ref = sc.embed(v)
        results = {'original': (v, 0.0), 'current': None}
        t0 = time.perf_counter()
        results['current'] = (current_method(path), time.perf_counter() - t0)
        for g in GUIDES:
            t0 = time.perf_counter()
            accented = at.restyle(v, g)
            back = vc.convert(accented, v, steps=25)
            results['guide:' + g] = (back / (np.abs(back).max() + 1e-6) * 0.9, time.perf_counter() - t0)
            sf.write(os.path.join(OUT, f'{name}__guidevoice_{g}.wav'), accented, SR)
        for method, (wav, secs) in results.items():
            sf.write(os.path.join(OUT, f'{name}__{method.replace(":", "_")}.wav'), wav, SR)
            sim, p_fr, heard = sc.score(wav, ref)
            rows.append((name, method, sim, p_fr, secs, heard))
            print(f'{name:16} {method:34} sim={sim:.2f} fr={p_fr:.2f} {secs:5.1f}s  "{heard[:80]}"', flush=True)


if __name__ == '__main__':
    main(sys.argv[1:] or sorted(glob.glob(os.path.join(ROOT, 'scratch', 'visitors', '*.wav'))))
