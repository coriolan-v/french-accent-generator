# French-O-Matic

A consent-first standalone prototype for a voice artwork. It records one sentence and uses Amphion Vevo-Style to transfer French-accented English pronunciation while retaining the participant's vocal timbre. Nothing is uploaded.

## Test it

Start the local AI engine in the first PowerShell window:

```powershell
cd C:\_DEV\french-accent-generator
npm run engine
```

The first start downloads the model checkpoints; later starts reuse them. Wait until the window says `Vevo engine ready at http://127.0.0.1:4174`.

The npm command uses `scripts/run-python.mjs` to start the trusted base Python interpreter with the packages already installed in `.venv`. This avoids Windows Device Guard blocking the unsigned launcher copied into `.venv\Scripts`.

Start the artwork in a second PowerShell window:

```powershell
cd C:\_DEV\french-accent-generator
npm run dev
```

Open <http://127.0.0.1:4173> in Chrome or Edge.

1. The numbered **1 — Worse French accent** reference loads automatically. Use the dropdown to choose numbered references 2–4 or upload a custom 3–15 second reference.
2. Confirm the top-right status says **Vevo ready / local**. Speech preservation is locked on; choose a more or less exaggerated reference to change the accent character.
3. Hold `R` while speaking and release it to finish. Recording stops automatically after fifteen seconds even if the key remains held.
4. French-O-Matic processes the sentence and plays the converted audio automatically.
5. Press `R` again for the next participant, or use **Original**, **Converted**, and **Erase** for manual testing.

## How the conversion works

The browser turns the participant's captured sentence into a mono WAV and sends it only to a loopback service on this computer. The local engine:

1. Uses Vevo-Timbre to render the comic reference in the participant's timbre while preserving its delivery.
2. Uses the participant's sentence as linguistic content, the matched reference as accent style, and the participant's original sentence as timbre.
3. Runs a final Vevo-Timbre pass against the untouched participant recording to reduce reference-speaker identity leakage.

There is no text box, transcription, or text-to-speech stage. The engine can only transform the submitted waveform. Per-utterance input and output files are created in a random temporary folder and removed in a `finally` block after the response.

Source-content masking is disabled because it can delete words and make long output collapse. The first six seconds of the selected style reference are used so a full fifteen-second participant recording still fits Vevo's generation context. Lower and upper generation bounds target roughly 80–120% of the input duration. Identity matching remains active, but Vevo still cannot guarantee word-perfect conversion or deliberately insert filler words.

The included setup uses Python 3.10, PyTorch 2.8 with CUDA 12.8, and the computer's RTX 5070. `scripts/setup-vevo.ps1` reproduces the environment.

## Reference and licensing

The active app offers the four locally supplied, numbered `.m4a` recordings in `assets` as reference presets. A custom reference can also be supplied in the browser. The selected audio is sent only to the loopback engine, and temporary conversion files are deleted after every request. Use recordings only when you own them or have permission to use them.

The published Amphion Vevo checkpoints are CC BY-NC 4.0. The source code is MIT-licensed. Review these terms before commercial use.

The strongest hosted alternative found is Resemble AI: a short-lived rapid voice plus speech-to-speech conversion prompted for a French accent. It is not enabled because it would send biometric voice data to a third party.

## Security note

An API token was previously embedded in two older Python scripts. It has been replaced with `ELEVENLABS_API_KEY` environment-variable access. Rotate the old credential before using those experiments again.
