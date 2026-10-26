"""Zero-shot voice conversion with Seed-VC, kept loaded in memory and working on numpy arrays."""
import os
import sys

import numpy as np
import torch
import torchaudio
import yaml

sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'seed-vc'))
from hf_utils import load_custom_model_from_hf  # noqa: E402
from modules.audio import mel_spectrogram  # noqa: E402
from modules.bigvgan import bigvgan  # noqa: E402
from modules.campplus.DTDNN import CAMPPlus  # noqa: E402
from modules.commons import build_model, load_checkpoint, recursive_munch  # noqa: E402
from transformers import AutoFeatureExtractor, WhisperModel  # noqa: E402

SR = 22050
MAX_REF_SECONDS = 25


class VoiceConverter:
    def __init__(self, device='cuda'):
        self.device = torch.device(device)
        ckpt, cfg_path = load_custom_model_from_hf(
            'Plachta/Seed-VC',
            'DiT_seed_v2_uvit_whisper_small_wavenet_bigvgan_pruned.pth',
            'config_dit_mel_seed_uvit_whisper_small_wavenet.yml')
        cfg = yaml.safe_load(open(cfg_path, 'r'))
        params = recursive_munch(cfg['model_params'])
        self.model = build_model(params, stage='DiT')
        self.model, *_ = load_checkpoint(self.model, None, ckpt, load_only_params=True,
                                         ignore_modules=[], is_distributed=False)
        for m in self.model.values():
            m.eval().to(self.device)
        self.model.cfm.estimator.setup_caches(max_batch_size=1, max_seq_length=8192)

        spect = cfg['preprocess_params']['spect_params']
        self.hop = spect['hop_length']
        self.to_mel = lambda x: mel_spectrogram(
            x, n_fft=spect['n_fft'], win_size=spect['win_length'], hop_size=self.hop,
            num_mels=spect['n_mels'], sampling_rate=SR, fmin=0, fmax=None, center=False)

        whisper_name = getattr(params.speech_tokenizer, 'name', 'openai/whisper-small')
        self.whisper = WhisperModel.from_pretrained(whisper_name, torch_dtype=torch.float16).to(self.device)
        del self.whisper.decoder
        self.features = AutoFeatureExtractor.from_pretrained(whisper_name)

        campplus_path = load_custom_model_from_hf('funasr/campplus', 'campplus_cn_common.bin', config_filename=None)
        self.campplus = CAMPPlus(feat_dim=80, embedding_size=192)
        self.campplus.load_state_dict(torch.load(campplus_path, map_location='cpu'))
        self.campplus.eval().to(self.device)

        self.vocoder = bigvgan.BigVGAN.from_pretrained('nvidia/bigvgan_v2_22khz_80band_256x', use_cuda_kernel=False)
        self.vocoder.remove_weight_norm()
        self.vocoder = self.vocoder.eval().to(self.device)

    def _content(self, wav16k):
        inputs = self.features([wav16k.squeeze(0).cpu().numpy()], return_tensors='pt',
                               return_attention_mask=True, sampling_rate=16000)
        feats = self.whisper._mask_input_features(inputs.input_features, attention_mask=inputs.attention_mask)
        out = self.whisper.encoder(feats.to(self.device, self.whisper.encoder.dtype), return_dict=True)
        return out.last_hidden_state.float()[:, :wav16k.size(-1) // 320 + 1]

    @torch.inference_mode()
    def convert(self, source: np.ndarray, reference: np.ndarray, steps=25, cfg_rate=0.7, max_ref_seconds=None) -> np.ndarray:
        """Say `source` (22.05 kHz mono, < 30 s) in the voice of `reference` (22.05 kHz mono)."""
        src = torch.from_numpy(source).float()[None].to(self.device)
        # Leave room in the 30 s window for the source, but keep at least 10 s of reference.
        ref_seconds = min(max_ref_seconds or MAX_REF_SECONDS, max(10, 29 - len(source) / SR))
        ref = torch.from_numpy(reference[:int(SR * ref_seconds)]).float()[None].to(self.device)
        src16 = torchaudio.functional.resample(src, SR, 16000)
        ref16 = torchaudio.functional.resample(ref, SR, 16000)

        mel_src, mel_ref = self.to_mel(src), self.to_mel(ref)
        fbank = torchaudio.compliance.kaldi.fbank(ref16, num_mel_bins=80, dither=0, sample_frequency=16000)
        style = self.campplus((fbank - fbank.mean(dim=0, keepdim=True))[None])

        cond = self.model.length_regulator(self._content(src16), ylens=torch.LongTensor([mel_src.size(2)]).to(self.device),
                                           n_quantizers=3, f0=None)[0]
        prompt = self.model.length_regulator(self._content(ref16), ylens=torch.LongTensor([mel_ref.size(2)]).to(self.device),
                                             n_quantizers=3, f0=None)[0]
        # The model sees at most 30 s (reference + source), so long sources go in crossfaded chunks.
        window = SR // self.hop * 30 - mel_ref.size(2)
        overlap = 16
        out, pos = [], 0
        while pos < cond.size(1):
            chunk = cond[:, pos:pos + window]
            cat = torch.cat([prompt, chunk], dim=1)
            with torch.autocast(device_type=self.device.type, dtype=torch.float16):
                mel = self.model.cfm.inference(cat, torch.LongTensor([cat.size(1)]).to(self.device),
                                               mel_ref, style, None, steps, inference_cfg_rate=cfg_rate)
            wave = self.vocoder(mel[:, :, mel_ref.size(-1):].float())[0].squeeze(0).cpu().numpy()
            if out:
                n = overlap * self.hop
                fade = np.cos(np.linspace(0, np.pi / 2, n)) ** 2
                wave[:n] = wave[:n] * (1 - fade) + out[-1][-n:] * fade
                out[-1] = out[-1][:-n]
            out.append(wave)
            if pos + window >= cond.size(1):
                break
            pos += window - overlap
        return np.concatenate(out)


class AccentTransfer:
    """Seed-VC v2 style conversion: re-speaks `source` with the accent (and voice) of a guide recording."""

    MAX_GUIDE_SECONDS = 12   # leaves room for a 15 s source in the AR model's 1500-token window

    def __init__(self, device='cuda'):
        from hydra.utils import instantiate
        from omegaconf import DictConfig
        self.device = torch.device(device)
        cfg_path = os.path.join(os.path.dirname(__file__), 'seed-vc', 'configs', 'v2', 'vc_wrapper.yaml')
        self.w = instantiate(DictConfig(yaml.safe_load(open(cfg_path, 'r'))))
        self.w.load_checkpoints()
        self.w.to(self.device).eval()
        self.w.setup_ar_caches(max_batch_size=1, max_seq_len=4096, dtype=torch.float16, device=self.device)
        self.guides = {}   # name -> precomputed guide features

    def _prepare_guide(self, guide: np.ndarray):
        w, dev = self.w, self.device
        g = guide[:SR * self.MAX_GUIDE_SECONDS]
        g22 = torch.from_numpy(g).float()[None].to(dev)
        g16 = torchaudio.functional.resample(g22, SR, 16000)
        with torch.autocast(device_type=dev.type, dtype=torch.float16):
            wide = w._process_content_features(g16, is_narrow=False)
            narrow = w._process_content_features(g16, is_narrow=True)
            style = w.compute_style(g16)
            mel = w.mel_fn(g22)
            prompt, _ = w.cfm_length_regulator(wide, ylens=torch.LongTensor([mel.size(2)]).to(dev))
        return {'wide': wide, 'narrow': w.duration_reduction_func(narrow[0], 1)[0],
                'style': style, 'mel': mel, 'prompt': prompt}

    def set_guide(self, name, guide: np.ndarray):
        with torch.inference_mode():
            self.guides[name] = self._prepare_guide(guide)

    @torch.inference_mode()
    def restyle(self, source: np.ndarray, guide_name, steps=30, top_p=0.9, temperature=1.0,
                repetition_penalty=1.0, cfg=(0.7, 0.7)) -> np.ndarray:
        w, dev, g = self.w, self.device, self.guides[guide_name]
        s22 = torch.from_numpy(source).float()[None].to(dev)
        s16 = torchaudio.functional.resample(s22, SR, 16000)
        src_mel_len = w.mel_fn(s22).size(2)
        with torch.autocast(device_type=dev.type, dtype=torch.float16):
            src_wide = w._process_content_features(s16, is_narrow=False)
            src_narrow = w.duration_reduction_func(w._process_content_features(s16, is_narrow=True)[0], 1)[0]
            ar_cond = w.ar_length_regulator(torch.cat([g['narrow'], src_narrow], dim=0)[None])[0]
            ar_out = w.ar.generate(ar_cond, g['wide'], compiled_decode_fn=None, top_p=top_p,
                                   temperature=temperature, repetition_penalty=repetition_penalty)
            mel_len = int(src_mel_len / src_wide.size(-1) * ar_out.size(-1))
            cond, _ = w.cfm_length_regulator(ar_out, ylens=torch.LongTensor([mel_len]).to(dev))
            cat = torch.cat([g['prompt'], cond], dim=1)
            mel = w.cfm.inference(cat, torch.LongTensor([cat.size(1)]).to(dev), g['mel'], g['style'], steps,
                                  inference_cfg_rate=list(cfg), random_voice=False)
            mel = mel[:, :, g['mel'].size(-1):]
        return w.vocoder(mel.float()).squeeze().cpu().numpy()

    @torch.inference_mode()
    def timbre(self, source: np.ndarray, reference: np.ndarray, steps=30, cfg=(0.7, 0.7)) -> np.ndarray:
        """v2 timbre-only conversion: keep the source's pronunciation, take the reference's voice."""
        w, dev = self.w, self.device
        g = self._prepare_guide(reference)
        s22 = torch.from_numpy(source).float()[None].to(dev)
        s16 = torchaudio.functional.resample(s22, SR, 16000)
        with torch.autocast(device_type=dev.type, dtype=torch.float16):
            wide = w._process_content_features(s16, is_narrow=False)
            cond, _ = w.cfm_length_regulator(wide, ylens=torch.LongTensor([w.mel_fn(s22).size(2)]).to(dev))
            cat = torch.cat([g['prompt'], cond], dim=1)
        with torch.autocast(device_type=dev.type, dtype=torch.float32):
            mel = w.cfm.inference(cat, torch.LongTensor([cat.size(1)]).to(dev), g['mel'], g['style'], steps,
                                  inference_cfg_rate=list(cfg), random_voice=False)
        mel = mel[:, :, g['mel'].size(-1):]
        return w.vocoder(mel.float()).squeeze().cpu().numpy()
