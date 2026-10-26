"""Run the pipeline on WAV files and report voice similarity (does the output still sound like the input speaker?).

Usage: python test_pipeline.py input.wav [more.wav ...]   -> writes <name>_french.wav next to scratch/
"""
import os
import sys
import warnings

warnings.filterwarnings('ignore')
import librosa  # noqa: E402
import numpy as np  # noqa: E402
import soundfile as sf  # noqa: E402
import torch  # noqa: E402
import torchaudio  # noqa: E402

from pipeline import FrenchAccentPipeline  # noqa: E402

OUT = os.path.join(os.path.dirname(__file__), '..', 'scratch')


def speaker_embedding(p, wav22):
    wav16 = torch.from_numpy(librosa.resample(wav22, orig_sr=22050, target_sr=16000))[None].float().cuda()
    fb = torchaudio.compliance.kaldi.fbank(wav16, num_mel_bins=80, dither=0, sample_frequency=16000)
    with torch.inference_mode():
        e = p.vc.campplus((fb - fb.mean(0, keepdim=True))[None])[0]
    return torch.nn.functional.normalize(e, dim=0)


def main(paths):
    os.makedirs(OUT, exist_ok=True)
    p = FrenchAccentPipeline()
    for path in paths:
        wav, sr = sf.read(path, dtype='float32')
        r = p.run(wav, sr)
        name = os.path.splitext(os.path.basename(path))[0]
        sf.write(os.path.join(OUT, f'{name}_french.wav'), r['audio'], r['sr'])
        sf.write(os.path.join(OUT, f'{name}_guide.wav'), r['guide'], r['sr'])
        ref22 = librosa.resample(wav if wav.ndim == 1 else wav.mean(1), orig_sr=sr, target_sr=22050)
        e_in, e_out, e_guide = (speaker_embedding(p, x) for x in (ref22, r['audio'], r['guide']))
        retext = p.transcribe(librosa.resample(r['audio'], orig_sr=22050, target_sr=16000))
        print(f'\n== {name}')
        print('heard   :', r['text'])
        print('accented:', r['phonemes_fr'])
        print('re-heard:', retext)
        print(f'voice similarity to visitor: output {float(e_in @ e_out):.2f}  vs  French guide {float(e_in @ e_guide):.2f}')
        print('timings :', {k: round(v, 2) for k, v in r['timings'].items()})


if __name__ == '__main__':
    main(sys.argv[1:])
