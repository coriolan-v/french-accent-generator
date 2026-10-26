"""Approach 2: Chatterbox speaks the visitor's words cloning a guide's accent, then Seed-VC v1 restores the visitor's voice.
Writes to scratch/compare/ and prints scores (see compare_guides.py for their meaning)."""
import os
import time
import warnings

warnings.filterwarnings('ignore')
import librosa  # noqa: E402
import numpy as np  # noqa: E402
import soundfile as sf  # noqa: E402
from chatterbox.tts import ChatterboxTTS  # noqa: E402

from compare_guides import OUT, ROOT, Scorer, load  # noqa: E402
from vc import SR, VoiceConverter  # noqa: E402

TEXT = {
    'you_testing': "Hello, testing French accent generator. Let's hope this works. Strong English native accent.",
    'you_squirrels': 'Three very angry squirrels threw their horrible red umbrellas through the window because the weather was absolutely ridiculous.',
    'visitor_male': 'Hello, my name is Thomas, and I think this is the best thing in the whole world. Would you like a croissant?',
}
GUIDES = ['3-worse-ref-3', '4-worse-reference-15s', 'french8_style_reference']
SETTINGS = [(0.5, 0.3), (0.7, 0.0)]   # (exaggeration, cfg_weight); lower cfg follows the guide's delivery more


def main():
    tts = ChatterboxTTS.from_pretrained(device='cuda')
    vc = VoiceConverter()
    sc = Scorer(vc)
    for name, text in TEXT.items():
        v = load(os.path.join(ROOT, 'scratch', 'visitors', name + '.wav'))[:SR * 15]
        ref = sc.embed(v)
        for g in GUIDES:
            gpath = os.path.join(ROOT, 'scratch', 'refs', g + '.wav')
            for exag, cfg in SETTINGS:
                t0 = time.perf_counter()
                spoken = tts.generate(text, audio_prompt_path=gpath, exaggeration=exag, cfg_weight=cfg).squeeze(0).numpy()
                spoken = librosa.resample(spoken, orig_sr=tts.sr, target_sr=SR)
                t1 = time.perf_counter()
                back = vc.convert(spoken, v, steps=25)
                back = back / (np.abs(back).max() + 1e-6) * 0.9
                t2 = time.perf_counter()
                tag = f'{name}__tts_{g}_e{exag}_c{cfg}'
                sf.write(os.path.join(OUT, tag + '_guidevoice.wav'), spoken, SR)
                sf.write(os.path.join(OUT, tag + '.wav'), back, SR)
                _, fr_mid, _ = sc.score(spoken, ref)
                sim, fr, heard = sc.score(back, ref)
                print(f'{name:14} {g:24} e={exag} c={cfg}  guide-fr={fr_mid:.2f} | final sim={sim:.2f} fr={fr:.2f} '
                      f'tts {t1 - t0:.1f}s vc {t2 - t1:.1f}s  "{heard[:70]}"', flush=True)


if __name__ == '__main__':
    main()
