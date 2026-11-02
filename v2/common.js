// Shared by the operator page (index.html) and the round visitor display (kiosk.html).
const MAX_SECONDS = 15;
const NO_SPEECH_MS = 5000;  // a hands-free recording is cancelled if nobody has spoken by then
const SPEECH_DB = -45;      // mic level (dBFS) that counts as speech; raise it if room noise passes as speech
const SPEECH_MIN_MS = 300;  // total time above that level needed to count as speech
const TICK_MS = 50;
const LIGHTS_VENDOR = 0x1B4F;   // SparkFun Pro Micro (see arduino/PyramidLights)

// Accent settings: chosen on the operator page, used for visitors too, kept across reloads.
const SETTINGS = { strength: '3', voice: 'ff_siwis', speed: '0.9', steps: '25', clean: '0' };
function setting(k) {
  try { return localStorage.getItem(k) ?? SETTINGS[k]; } catch { return SETTINGS[k]; }
}

// The two pages talk over this channel, so they must be open in the same browser.
//   round display -> operator: kiosk {state, lights}, run {input, seconds, result | error, total}, play, log {message}
//   operator -> round display: hello, button {down}, lights
const channel = new BroadcastChannel('frenchify');

const $ = id => document.getElementById(id);

let audioCtx;
function ctx() {
  if (!audioCtx) audioCtx = new (window.AudioContext || window.webkitAudioContext)();
  if (audioCtx.state === 'suspended') audioCtx.resume();
  return audioCtx;
}

// One message from the microphone. It stops by itself after MAX_SECONDS, and after NO_SPEECH_MS
// if nobody has spoken unless `held` (a button kept down while speaking).
// on.tick() runs every TICK_MS; on.stop(blob) gets the recording, or null if nobody spoke.
class Recorder {
  held = false;
  level = -100;   // mic level in dBFS, for meters

  constructor(on) { this.on = on; }
  get active() { return this.mr?.state === 'recording'; }
  get elapsed() { return Math.min((performance.now() - this.t0) / 1000, MAX_SECONDS); }

  // Resolves to false if another recording started while the mic opened (a double press).
  async start() {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true } });
    if (this.active) { stream.getTracks().forEach(t => t.stop()); return false; }
    this.listen(stream);
    const chunks = [], mr = this.mr = new MediaRecorder(stream);
    mr.ondataavailable = e => e.data.size && chunks.push(e.data);
    mr.onstop = () => {
      stream.getTracks().forEach(t => t.stop());
      this.on.stop(this.heardSpeech() ? new Blob(chunks, { type: mr.mimeType }) : null);
    };
    mr.start();
    this.t0 = performance.now();
    this.timer = setInterval(() => this.tick(), TICK_MS);
    this.autoStop = setTimeout(() => this.stop(), MAX_SECONDS * 1000);
    return true;
  }

  stop() {
    if (!this.active) return;
    clearInterval(this.timer);
    clearTimeout(this.autoStop);
    this.mr.stop();
  }

  tick() {
    this.measure();
    this.on.tick?.();
    if (!this.held && !this.heardSpeech() && performance.now() - this.t0 >= NO_SPEECH_MS) this.stop();
  }

  // Speech detection: adds up the time the mic level is above SPEECH_DB, so silent recordings are dropped.
  listen(stream) {
    this.source?.disconnect();
    this.speechMs = 0;
    this.level = -100;
    this.analyser = null;
    if (ctx().state !== 'running') return;   // can't measure, so the recording counts as speech
    this.analyser = ctx().createAnalyser();
    this.analyser.fftSize = 2048;
    this.levels = new Float32Array(this.analyser.fftSize);
    this.source = ctx().createMediaStreamSource(stream);
    this.source.connect(this.analyser);
  }
  measure() {
    if (!this.analyser) return;
    this.analyser.getFloatTimeDomainData(this.levels);
    let sum = 0;
    for (const v of this.levels) sum += v * v;
    this.level = 10 * Math.log10(sum / this.levels.length);
    if (this.level > SPEECH_DB) this.speechMs += TICK_MS;
  }
  heardSpeech() { return !this.analyser || this.speechMs >= SPEECH_MIN_MS; }
}

// Decodes any format the browser understands and keeps the first MAX_SECONDS as mono WAV.
async function toWav(blob) {
  const buf = await ctx().decodeAudioData(await blob.arrayBuffer());
  const n = Math.min(buf.length, buf.sampleRate * MAX_SECONDS);
  const mono = new Float32Array(n);
  for (let c = 0; c < buf.numberOfChannels; c++) {
    const d = buf.getChannelData(c);
    for (let i = 0; i < n; i++) mono[i] += d[i] / buf.numberOfChannels;
  }
  return { wav: encodeWav(mono, buf.sampleRate), seconds: n / buf.sampleRate, trimmed: buf.length > n };
}

// Runs the engine on a WAV with the current settings. Errors carry the HTTP status (422: no speech heard).
async function convert(wav, text = '') {
  const form = new FormData();
  form.append('audio', wav, 'input.wav');
  for (const k of Object.keys(SETTINGS)) form.append(k, setting(k));
  if (text) form.append('text', text);
  const res = await fetch('/api/convert', { method: 'POST', body: form });
  const r = await res.json();
  if (!res.ok) throw Object.assign(new Error(r.error || res.statusText), { status: res.status });
  return r;
}

function b64Blob(b64) {
  const bin = atob(b64), bytes = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
  return new Blob([bytes], { type: 'audio/wav' });
}

function encodeWav(d, sr) {
  const view = new DataView(new ArrayBuffer(44 + d.length * 2));
  const w = (o, s) => [...s].forEach((c, i) => view.setUint8(o + i, c.charCodeAt(0)));
  w(0, 'RIFF'); view.setUint32(4, 36 + d.length * 2, true); w(8, 'WAVE'); w(12, 'fmt ');
  view.setUint32(16, 16, true); view.setUint16(20, 1, true); view.setUint16(22, 1, true);
  view.setUint32(24, sr, true); view.setUint32(28, sr * 2, true); view.setUint16(32, 2, true);
  view.setUint16(34, 16, true); w(36, 'data'); view.setUint32(40, d.length * 2, true);
  for (let i = 0; i < d.length; i++) view.setInt16(44 + i * 2, Math.max(-1, Math.min(1, d[i])) * 0x7fff, true);
  return new Blob([view], { type: 'audio/wav' });
}
