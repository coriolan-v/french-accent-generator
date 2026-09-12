$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
$uvCache = Join-Path $projectRoot ".uv-cache"
$venvPython = Join-Path $projectRoot ".venv\Scripts\python.exe"
$amphionRoot = Join-Path $projectRoot "vendor\Amphion"

$env:UV_CACHE_DIR = $uvCache

if (-not (Test-Path -LiteralPath $venvPython)) {
  uv venv --python 3.10 (Join-Path $projectRoot ".venv")
}

if (-not (Test-Path -LiteralPath $amphionRoot)) {
  New-Item -ItemType Directory -Path (Split-Path -Parent $amphionRoot) -Force | Out-Null
  git clone --depth 1 https://github.com/open-mmlab/Amphion.git $amphionRoot
}

uv pip install --python $venvPython torch==2.8.0 torchaudio==2.8.0 --index-url https://download.pytorch.org/whl/cu128
uv pip install --python $venvPython -r (Join-Path $projectRoot "requirements-local.txt")

& $venvPython -c "import torch; print('Torch:', torch.__version__); print('CUDA:', torch.cuda.is_available()); print('GPU:', torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'none')"
