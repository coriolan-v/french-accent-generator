"""Local web server: serves the pages and runs the French accent pipeline on the GPU.

Run:  .venv\\Scripts\\python server.py   then open http://localhost:8000 (operator page;
the round visitor display is /kiosk, opened from there).
"""
import base64
import io
import os
import threading
import traceback
import warnings

warnings.filterwarnings('ignore')
import soundfile as sf  # noqa: E402
import uvicorn  # noqa: E402
from fastapi import FastAPI, File, Form, UploadFile  # noqa: E402
from fastapi.responses import FileResponse, JSONResponse  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MAX_SECONDS = 15
GUIDE_VOICES = ['ff_siwis', 'am_michael', 'bm_george', 'af_heart']

app = FastAPI()
state = {'pipeline': None, 'error': None}
gpu_lock = threading.Lock()


def load():
    try:
        from pipeline import FrenchAccentPipeline
        state['pipeline'] = FrenchAccentPipeline()
        print('Models loaded, ready on http://localhost:8000')
    except Exception as e:
        traceback.print_exc()
        state['error'] = str(e)


def wav_b64(audio, sr):
    buf = io.BytesIO()
    sf.write(buf, audio, sr, format='WAV', subtype='PCM_16')
    return base64.b64encode(buf.getvalue()).decode()


def page_file(name, media_type=None):
    # no-cache: the browser checks for edits on every load instead of reusing an old copy.
    return FileResponse(os.path.join(ROOT, name), media_type=media_type, headers={'Cache-Control': 'no-cache'})


@app.get('/')
def index():
    return page_file('index.html')


@app.get('/kiosk')
def kiosk():
    return page_file('kiosk.html')


@app.get('/common.js')
def common_js():
    return page_file('common.js', 'text/javascript')


@app.get('/api/health')
def health():
    return {'ready': state['pipeline'] is not None, 'error': state['error'], 'voices': GUIDE_VOICES}


@app.post('/api/convert')
def convert(audio: UploadFile = File(...), strength: int = Form(3), voice: str = Form('ff_siwis'),
            speed: float = Form(0.9), steps: int = Form(25), text: str = Form(''), clean: int = Form(0)):
    p = state['pipeline']
    if p is None:
        return JSONResponse({'error': 'Models are still loading, try again in a moment.'}, status_code=503)
    try:
        wav, sr = sf.read(io.BytesIO(audio.file.read()), dtype='float32')
        wav = wav[:sr * MAX_SECONDS]
        with gpu_lock:
            r = p.run(wav, sr, strength=max(1, min(3, strength)),
                      voice=voice if voice in GUIDE_VOICES else 'ff_siwis',
                      speed=max(0.6, min(1.3, speed)), steps=max(5, min(60, steps)),
                      text=text.strip() or None, clean=max(0, min(3, clean)))
    except ValueError as e:
        return JSONResponse({'error': str(e)}, status_code=422)
    except Exception as e:
        traceback.print_exc()
        return JSONResponse({'error': f'Processing failed: {e}'}, status_code=500)
    return {
        'text': r['text'], 'phonemes': r['phonemes_fr'],
        'audio': wav_b64(r['audio'], r['sr']), 'guide': wav_b64(r['guide'], r['sr']),
        'cleaned': wav_b64(r['cleaned'], r['sr']) if r['cleaned'] is not None else None,
        'timings': {k: round(v, 2) for k, v in r['timings'].items()},
    }


if __name__ == '__main__':
    threading.Thread(target=load, daemon=True).start()
    uvicorn.run(app, host='127.0.0.1', port=8000, log_level='warning')
