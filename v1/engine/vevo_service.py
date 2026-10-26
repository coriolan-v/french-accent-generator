"""Local HTTP wrapper for Amphion Vevo-Style accent conversion."""

import base64
import json
import os
import socket
import shutil
import sys
import tempfile
import threading
import time
import wave
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
AMPHION_ROOT = PROJECT_ROOT / "vendor" / "Amphion"
MODEL_CACHE = PROJECT_ROOT / "models" / "Vevo"
RUNTIME_ROOT = PROJECT_ROOT / "runtime"
ENGINE_PORT = int(os.environ.get("VEVO_ENGINE_PORT", "4174"))

if not AMPHION_ROOT.exists():
    raise RuntimeError("Amphion is missing. Run scripts/setup-vevo.ps1 first.")

RUNTIME_ROOT.mkdir(parents=True, exist_ok=True)

sys.path.insert(0, str(AMPHION_ROOT))
os.chdir(AMPHION_ROOT)

# Device Guard prevents Numba from executing its generated cache code and can
# leave librosa.filters consuming CPU indefinitely during import. Vevo's model
# inference uses PyTorch/CUDA, so disabling this optional Librosa JIT is safe.
os.environ.setdefault("NUMBA_DISABLE_JIT", "1")

import librosa
import torch
from huggingface_hub import snapshot_download
from models.vc.vevo.vevo_utils import VevoInferencePipeline, save_audio

INFERENCE_LOCK = threading.Lock()
MAX_STYLE_SECONDS = 6.0


def trim_pcm_wav(path, maximum_seconds):
    trimmed_path = path.with_name(f"{path.stem}-trimmed.wav")
    with wave.open(str(path), "rb") as source:
        parameters = source.getparams()
        maximum_frames = round(source.getframerate() * maximum_seconds)
        frames = source.readframes(min(source.getnframes(), maximum_frames))
    with wave.open(str(trimmed_path), "wb") as target:
        target.setparams(parameters)
        target.writeframes(frames)
    trimmed_path.replace(path)


def model_snapshot(pattern):
    return Path(snapshot_download(
        repo_id="amphion/Vevo",
        repo_type="model",
        cache_dir=str(MODEL_CACHE),
        allow_patterns=[pattern],
    ))


def load_pipeline():
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    if device.type != "cuda":
        raise RuntimeError("A CUDA GPU is required for acceptable Vevo performance.")
    print(f"Loading Vevo on {torch.cuda.get_device_name(0)}", flush=True)
    content_root = model_snapshot("tokenizer/vq32/*")
    style_root = model_snapshot("tokenizer/vq8192/*")
    ar_root = model_snapshot("contentstyle_modeling/Vq32ToVq8192/*")
    fmt_root = model_snapshot("acoustic_modeling/Vq8192ToMels/*")
    vocoder_root = model_snapshot("acoustic_modeling/Vocoder/*")
    pipeline = VevoInferencePipeline(
        content_tokenizer_ckpt_path=str(content_root / "tokenizer" / "vq32" / "hubert_large_l18_c32.pkl"),
        content_style_tokenizer_ckpt_path=str(style_root / "tokenizer" / "vq8192"),
        ar_cfg_path=str(AMPHION_ROOT / "models" / "vc" / "vevo" / "config" / "Vq32ToVq8192.json"),
        ar_ckpt_path=str(ar_root / "contentstyle_modeling" / "Vq32ToVq8192"),
        fmt_cfg_path=str(AMPHION_ROOT / "models" / "vc" / "vevo" / "config" / "Vq8192ToMels.json"),
        fmt_ckpt_path=str(fmt_root / "acoustic_modeling" / "Vq8192ToMels"),
        vocoder_cfg_path=str(AMPHION_ROOT / "models" / "vc" / "vevo" / "config" / "Vocoder.json"),
        vocoder_ckpt_path=str(vocoder_root / "acoustic_modeling" / "Vocoder"),
        device=device,
    )
    original_generate = pipeline.ar_model.generate

    def generate_with_duration_limit(*args, **kwargs):
        requested_minimum = getattr(pipeline, "minimum_output_tokens", 50)
        requested_maximum = getattr(pipeline, "maximum_output_tokens", 2000)
        input_ids = kwargs.get("input_ids")
        prompt_ids = kwargs.get("prompt_output_ids")
        input_length = (input_ids.shape[1] if input_ids is not None else 0) + (
            prompt_ids.shape[1] if prompt_ids is not None else 0
        )
        available_tokens = max(50, 2000 - input_length - 16)
        maximum_tokens = min(requested_maximum, available_tokens)
        kwargs["min_new_tokens"] = min(requested_minimum, maximum_tokens)
        kwargs["max_length"] = min(2000, input_length + maximum_tokens + 8)
        return original_generate(*args, **kwargs)

    pipeline.ar_model.generate = generate_with_duration_limit
    return pipeline


PIPELINE = load_pipeline()


class Handler(BaseHTTPRequestHandler):
    def send_json(self, status, payload):
        data = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.path == "/health":
            self.send_json(200, {"status": "ready", "engine": "Amphion Vevo-Style", "uploads": False})
        else:
            self.send_json(404, {"error": "Not found"})

    def do_POST(self):
        if self.path != "/transform":
            return self.send_json(404, {"error": "Not found"})
        work_dir = Path(tempfile.mkdtemp(prefix="utterance_", dir=RUNTIME_ROOT))
        started = time.perf_counter()
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length <= 0 or length > 32 * 1024 * 1024:
                raise ValueError("Invalid recording size.")
            payload = json.loads(self.rfile.read(length))
            if payload.get("consent") is not True:
                raise ValueError("Consent is required.")
            input_path = work_dir / "input.wav"
            style_path = work_dir / "style.wav"
            output_path = work_dir / "output.wav"
            input_path.write_bytes(base64.b64decode(payload["audioBase64"], validate=True))
            style_path.write_bytes(base64.b64decode(payload["referenceAudioBase64"], validate=True))
            original_style_duration = librosa.get_duration(path=style_path)
            if original_style_duration > MAX_STYLE_SECONDS:
                trim_pcm_wav(style_path, MAX_STYLE_SECONDS)
            duration = librosa.get_duration(path=input_path)
            if duration < 1.0 or duration > 16.0:
                raise ValueError("Please record one sentence between 1 and 15 seconds.")
            style_duration = librosa.get_duration(path=style_path)
            if style_duration < 3.0 or style_duration > MAX_STYLE_SECONDS + 0.1:
                raise ValueError("Please use a French-accent reference of at least 3 seconds.")
            strength = float(payload.get("caricatureStrength", 0.80))
            if not 0.0 <= strength <= 1.0:
                raise ValueError("Caricature strength must be between 0 and 1.")

            # Randomly masking source tokens strengthened the caricature but also
            # allowed words and whole phrases to disappear. Preserve every source
            # token. A shorter style prompt leaves room for long source utterances
            # inside Vevo's fixed autoregressive context.
            content_mask_ratio = -1
            with INFERENCE_LOCK:
                PIPELINE.minimum_output_tokens = max(50, round(duration * 40))
                PIPELINE.maximum_output_tokens = max(60, round(duration * 60))
                # Raw style references can leak the reference speaker's sex,
                # pitch range, and vocal colour. Vevo-Timbre preserves the comic
                # delivery while first dressing that reference in the current
                # participant's timbre.
                matched_style_path = work_dir / "identity-matched-style.wav"
                matched_style = PIPELINE.inference_fm(
                    src_wav_path=str(style_path),
                    timbre_ref_wav_path=str(input_path),
                    flow_matching_steps=20,
                )
                save_audio(matched_style, output_path=str(matched_style_path))

                generated = PIPELINE.inference_ar_and_fm(
                    src_wav_path=str(input_path),
                    src_text=None,
                    style_ref_wav_path=str(matched_style_path),
                    timbre_ref_wav_path=str(input_path),
                    vc_input_mask_ratio=content_mask_ratio,
                    flow_matching_steps=24,
                )

                # Reapply only the participant's timbre after accent generation.
                # This retains the generated accent/style tokens while reducing
                # identity leakage from the original reference speaker.
                accented_path = work_dir / "accented.wav"
                save_audio(generated, output_path=str(accented_path))
                generated = PIPELINE.inference_fm(
                    src_wav_path=str(accented_path),
                    timbre_ref_wav_path=str(input_path),
                    flow_matching_steps=20,
                )
                save_audio(generated, output_path=str(output_path))
            output_duration = librosa.get_duration(path=output_path)
            self.send_json(200, {
                "audioBase64": base64.b64encode(output_path.read_bytes()).decode("ascii"),
                "mimeType": "audio/wav",
                "reference": "custom",
                "caricatureStrength": strength,
                "accentPasses": 1,
                "identityProtection": True,
                "contentMasking": False,
                "inputSeconds": duration,
                "outputSeconds": output_duration,
                "referenceSeconds": style_duration,
                "processingSeconds": time.perf_counter() - started,
            })
        except (ValueError, KeyError, json.JSONDecodeError) as error:
            self.send_json(400, {"error": str(error)})
        except Exception as error:
            print(f"Conversion error: {error}", file=sys.stderr, flush=True)
            self.send_json(500, {"error": "Vevo could not convert this recording."})
        finally:
            shutil.rmtree(work_dir, ignore_errors=True)

    def log_message(self, format, *args):
        return


class ExclusiveThreadingHTTPServer(ThreadingHTTPServer):
    # HTTPServer enables SO_REUSEADDR by default. Windows does not allow that
    # option to be combined with SO_EXCLUSIVEADDRUSE, so explicitly disable it.
    allow_reuse_address = False

    def server_bind(self):
        if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        super().server_bind()


if __name__ == "__main__":
    server = ExclusiveThreadingHTTPServer(("127.0.0.1", ENGINE_PORT), Handler)
    print(f"Vevo engine ready at http://127.0.0.1:{ENGINE_PORT}", flush=True)
    server.serve_forever()
