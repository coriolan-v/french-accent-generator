"""Confirm the tuned voice-conversion settings on every test voice (old vs new settings)."""
import glob
import os
import warnings

warnings.filterwarnings('ignore')
import soundfile as sf  # noqa: E402

from compare_guides import OUT, ROOT, Scorer, load  # noqa: E402
from pipeline import FrenchAccentPipeline  # noqa: E402
from vc import SR  # noqa: E402

SETTINGS = {'old cfg0.7 ref25': dict(cfg_rate=0.7, ref_seconds=25),
            'new cfg0.3 ref5': dict(cfg_rate=0.3, ref_seconds=5),
            'cfg0.3 ref10': dict(cfg_rate=0.3, ref_seconds=10)}

p = FrenchAccentPipeline()
sc = Scorer(p.vc)
for path in sorted(glob.glob(os.path.join(ROOT, 'scratch', 'visitors', '*.wav'))):
    name = os.path.splitext(os.path.basename(path))[0]
    wav, sr = sf.read(path, dtype='float32')
    ref = sc.embed(load(path)[:SR * 15])
    text = None
    for label, kw in SETTINGS.items():
        r = p.run(wav, sr, text=text, **kw)
        text = r['text']   # same words for every setting
        sf.write(os.path.join(OUT, f'confirm__{name}__{label.replace(" ", "_")}.wav'), r['audio'], r['sr'])
        sim, fr, heard = sc.score(r['audio'], ref)
        print(f'{name:16} {label:18} sim={sim:.2f} fr={fr:.2f}  "{heard[:60]}"', flush=True)
