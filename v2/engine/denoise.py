"""Remove background noise (crowd chatter, music, hum) from a visitor recording with DeepFilterNet3.

Install (DeepFilterNet pins numpy<2 but runs fine on numpy 2, so skip its dependencies):
    uv pip install --python .venv\\Scripts\\python.exe --no-deps deepfilternet==0.5.6 deepfilterlib==0.5.6 appdirs==1.4.4
The model (~8 MB) downloads on first start to %LOCALAPPDATA%\\DeepFilterNet.
"""
import sys
import types

import librosa
import numpy as np
import torch

# DeepFilterNet imports torchaudio.backend (removed in torchaudio 2.x) only for a type hint.
if 'torchaudio.backend.common' not in sys.modules:
    _common = types.ModuleType('torchaudio.backend.common')
    _common.AudioMetaData = object
    sys.modules['torchaudio.backend'] = types.ModuleType('torchaudio.backend')
    sys.modules['torchaudio.backend.common'] = _common
from df.enhance import enhance, init_df  # noqa: E402

# Most noise each level may remove, in dB (None = no limit). A limit keeps some background, which sounds more natural.
LEVELS = {1: 12, 2: 24, 3: None}


class Denoiser:
    def __init__(self):
        self.model, self.state, _ = init_df(log_level='WARNING', log_file=None)
        self.sr = self.state.sr()

    @torch.inference_mode()
    def clean(self, wav: np.ndarray, sr: int, level: int) -> np.ndarray:
        """Mono float32 at `sr` in, same out. Level 0 (or unknown) returns the input untouched."""
        if level not in LEVELS:
            return wav
        x = librosa.resample(wav, orig_sr=sr, target_sr=self.sr) if sr != self.sr else wav
        # cuDNN compiles new kernels for every new clip length (~0.8 s each); plain kernels take 0.1-0.4 s.
        with torch.backends.cudnn.flags(enabled=False):
            y = enhance(self.model, self.state, torch.from_numpy(x).float()[None], atten_lim_db=LEVELS[level])[0].numpy()
        return (librosa.resample(y, orig_sr=self.sr, target_sr=sr) if sr != self.sr else y)[:len(wav)]
