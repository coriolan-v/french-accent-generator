import os, sys, torch, soundfile as sf
from huggingface_hub import snapshot_download
import librosa

# --- Add Amphion repo path manually ---
repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "Amphion"))
if repo_root not in sys.path:
    sys.path.insert(0, repo_root)

# Now import Amphion modules
from amphion.models.vc.vevo.inference import VevoInferencePipeline

# 1) point to the ckpts you downloaded above
ckpt_root = "./ckpts/Vevo"
content_style_tokenizer_ckpt = os.path.join(ckpt_root, "tokenizer", "vq8192")
ar_ckpt = os.path.join(ckpt_root, "contentstyle_modeling", "PhoneToVq8192")
fmt_ckpt = os.path.join(ckpt_root, "acoustic_modeling", "Vq8192ToMels")
vocoder_ckpt = os.path.join(ckpt_root, "acoustic_modeling", "Vocoder")

device = "cuda" if torch.cuda.is_available() else "cpu"

pipe = VevoInferencePipeline(
    content_style_tokenizer_ckpt_path=content_style_tokenizer_ckpt,
    ar_cfg_path=os.path.join(repo_root, "models/vc/vevo/config/PhoneToVq8192.json"),
    ar_ckpt_path=ar_ckpt,
    fmt_cfg_path=os.path.join(repo_root, "models/vc/vevo/config/Vq8192ToMels.json"),
    fmt_ckpt_path=fmt_ckpt,
    vocoder_cfg_path=os.path.join(repo_root, "models/vc/vevo/config/Vocoder.json"),
    vocoder_ckpt_path=vocoder_ckpt,
    device=device,
)

# 2) your input sentence (what you recorded)
src_wav_path = "input.wav"  # your recorded sentence

# 3) a short reference of a *native French speaker speaking English*
style_ref_wav_path = "ref_french_accent.wav"

# 4) run style conversion (accent transfer) while preserving your timbre
gen = pipe.inference_ar_and_fm(
    src_wav_path=src_wav_path,
    src_text=None,
    style_ref_wav_path=style_ref_wav_path,
    timbre_ref_wav_path=src_wav_path,  # preserve *your* voice timbre
    style_ref_wav_text=None,
    src_text_language="en",
    style_ref_wav_text_language="en",
)

sf.write("output_french_accent.wav", gen, 24000)
print("✅ Saved: output_french_accent.wav")
