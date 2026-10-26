"""Which voice-conversion settings keep the accent of an accented source while taking the visitor's voice?"""
import base64
import io
import os
import warnings

warnings.filterwarnings('ignore')
import librosa  # noqa: E402
import numpy as np  # noqa: E402
import requests  # noqa: E402
import soundfile as sf  # noqa: E402
from chatterbox.tts import ChatterboxTTS  # noqa: E402

from compare_guides import OUT, ROOT, Scorer, load  # noqa: E402
from compare_tts import TEXT  # noqa: E402
from vc import SR, AccentTransfer, VoiceConverter  # noqa: E402

GUIDE = '4-worse-reference-15s'


def kokoro_guide(path):
    with open(path, 'rb') as f:
        r = requests.post('http://127.0.0.1:8000/api/convert', files={'audio': f},
                          data={'strength': 3, 'voice': 'ff_siwis', 'steps': 5}, timeout=120).json()
    wav, sr = sf.read(io.BytesIO(base64.b64decode(r['guide'])), dtype='float32')
    return librosa.resample(wav, orig_sr=sr, target_sr=SR) if sr != SR else wav


def main():
    vc = VoiceConverter()
    at = AccentTransfer()
    sc = Scorer(vc)
    tts = ChatterboxTTS.from_pretrained(device='cuda')

    you = sc.embed(load(os.path.join(ROOT, 'scratch', 'visitors', 'you_testing.wav')))
    for g in ['1-Worse-French-accent', '2-worste-ref-2', '3-worse-ref-3', '4-worse-reference-15s', 'french8_style_reference']:
        print(f'voice similarity you_testing <-> {g}: {float(sc.embed(load(os.path.join(ROOT, "scratch", "refs", g + ".wav"))) @ you):.2f}')

    variants = {
        'v1 cfg0.7 ref25': lambda s, v: vc.convert(s, v, cfg_rate=0.7),
        'v1 cfg0.3 ref25': lambda s, v: vc.convert(s, v, cfg_rate=0.3),
        'v1 cfg0.0 ref25': lambda s, v: vc.convert(s, v, cfg_rate=0.0),
        'v1 cfg0.7 ref5': lambda s, v: vc.convert(s, v, cfg_rate=0.7, max_ref_seconds=5),
        'v1 cfg0.3 ref5': lambda s, v: vc.convert(s, v, cfg_rate=0.3, max_ref_seconds=5),
        'v2 timbre .7/.7': lambda s, v: at.timbre(s, v, cfg=(0.7, 0.7)),
        'v2 timbre .7/.3': lambda s, v: at.timbre(s, v, cfg=(0.7, 0.3)),
    }
    gpath = os.path.join(ROOT, 'scratch', 'refs', GUIDE + '.wav')
    for name, text in TEXT.items():
        vpath = os.path.join(ROOT, 'scratch', 'visitors', name + '.wav')
        v = load(vpath)[:SR * 15]
        ref = sc.embed(v)
        sources = {
            'kokoro': kokoro_guide(vpath),
            'chatterbox': librosa.resample(tts.generate(text, audio_prompt_path=gpath, exaggeration=0.5, cfg_weight=0.3)
                                           .squeeze(0).numpy(), orig_sr=tts.sr, target_sr=SR),
        }
        for sname, s in sources.items():
            _, fr0, _ = sc.score(s, ref)
            print(f'\n{name} / {sname} source: fr={fr0:.2f}')
            for vname, fn in variants.items():
                out = fn(s, v)
                out = out / (np.abs(out).max() + 1e-6) * 0.9
                sf.write(os.path.join(OUT, f'tune__{name}__{sname}__{vname.replace(" ", "_").replace("/", "-")}.wav'), out, SR)
                sim, fr, heard = sc.score(out, ref)
                print(f'   {vname:18} sim={sim:.2f} fr={fr:.2f}  "{heard[:60]}"', flush=True)


if __name__ == '__main__':
    main()
