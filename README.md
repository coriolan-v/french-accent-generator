# Après Vous — French Accent Generator

A consent-first standalone prototype for a voice artwork. It records one sentence and uses Amphion Vevo-Style to transfer French-accented English pronunciation while retaining the participant's vocal timbre. Nothing is uploaded.

## Test it

Start the local AI engine in the first PowerShell window:

```powershell
cd C:\_DEV\french-accent-generator
npm run engine
```

The first start downloads the model checkpoints; later starts reuse them. Wait until the window says `Vevo engine ready at http://127.0.0.1:4174`.

Start the artwork in a second PowerShell window:

```powershell
cd C:\_DEV\french-accent-generator
npm run dev
```

Open <http://127.0.0.1:4173> in Chrome or Edge.

1. Tick the consent box.
2. Under **Your French-accent reference**, upload 3–15 seconds of yourself speaking English with the French accent you want transferred.
3. Select **Begin recording** for the participant, or select **Upload recording** for an existing participant clip.
4. Record or choose one participant sentence between 1 and 12 seconds. WAV, MP3, M4A, AAC, OGG, WebM, and FLAC are accepted when the browser can decode them.
5. Select **Original** to confirm the capture.
6. Confirm the top-right status says **Vevo ready / local**.
7. Set **Caricature strength**. Start at 80%. Higher values loosen pronunciation preservation; maximum strength is intentionally less faithful and may distort a word.
8. Select **Apply French accent** and wait for the transformed sentence to play.
9. Alternate between **Original** and **Converted** for an immediate comparison.
10. Select **Erase** and confirm the interface resets.

## How the conversion works

The browser turns the participant's captured sentence into a mono WAV and sends it only to a loopback service on this computer. The local engine:

1. Uses Vevo-Timbre to render the comic reference in the participant's timbre while preserving its delivery.
2. Uses the participant's sentence as linguistic content, the matched reference as accent style, and the participant's original sentence as timbre.
3. Runs a final Vevo-Timbre pass against the untouched participant recording to reduce reference-speaker identity leakage.

There is no text box, transcription, or text-to-speech stage. The engine can only transform the submitted waveform. Per-utterance input and output files are created in a random temporary folder and removed in a `finally` block after the response.

The caricature control progressively masks some source content tokens so the model relies more on the style reference. Identity matching is active at every strength. This strengthens style transfer but cannot deterministically replace individual phonemes or insert filler words; high values can trade intelligibility for exaggeration.

The included setup uses Python 3.10, PyTorch 2.8 with CUDA 12.8, and the computer's RTX 5070. `scripts/setup-vevo.ps1` reproduces the environment.

## Reference and licensing

The active app does not use a bundled archive voice. The reference is supplied in the browser for each session, sent only to the loopback engine, and deleted from the server's temporary working directory after every conversion. Use only a recording you own or have permission to use.

The published Amphion Vevo checkpoints are CC BY-NC 4.0. The source code is MIT-licensed. Review these terms before commercial use.

The strongest hosted alternative found is Resemble AI: a short-lived rapid voice plus speech-to-speech conversion prompted for a French accent. It is not enabled because it would send biometric voice data to a third party.

## Security note

An API token was previously embedded in two older Python scripts. It has been replaced with `ELEVENLABS_API_KEY` environment-variable access. Rotate the old credential before using those experiments again.
