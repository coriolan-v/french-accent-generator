const $ = (selector) => document.querySelector(selector);
const instrument = $(".instrument");
const recordButton = $("#recordButton");
const uploadInput = $("#uploadInput");
const inputOptions = $("#inputOptions");
const referenceSelect = $("#referenceSelect");
const customReferencePicker = $("#customReferencePicker");
const referenceInput = $("#referenceInput");
const referenceLabel = $("#referenceLabel");
const strengthInput = $("#strengthInput");
const strengthValue = $("#strengthValue");
const originalButton = $("#originalButton");
const convertedButton = $("#convertedButton");
const transformButton = $("#transformButton");
const eraseButton = $("#eraseButton");
const consent = $("#consent");
const capturedActions = $("#capturedActions");
const message = $("#message");
const clock = $("#clock");
const visualWord = $("#visualWord");
const canvas = $("#waveform");
const engineState = $("#engineState");
const timerProgress = $("#timerProgress");
const timerCaption = $("#timerCaption");

const MAX_RECORDING_SECONDS = 15;
const TIMER_CIRCUMFERENCE = 2 * Math.PI * 47;

let recorder;
let stream;
let chunks = [];
let recordingUrl;
let convertedUrl;
let referenceFile;
let timer;
let recordingTimeout;
let startedAt;
let audioContext;
let analyser;
let frame;
let playing;
let engineReady = false;
let processing = false;
let startingRecording = false;
let recordControlHeld = false;

timerProgress.style.strokeDasharray = String(TIMER_CIRCUMFERENCE);
timerProgress.style.strokeDashoffset = "0";
checkEngine();
loadSelectedReference();
setInterval(checkEngine, 5000);

recordButton.addEventListener("pointerdown", handleRecordPointerDown);
recordButton.addEventListener("pointerup", handleRecordPointerUp);
recordButton.addEventListener("pointercancel", handleRecordPointerUp);
recordButton.addEventListener("lostpointercapture", handleRecordPointerUp);
uploadInput.addEventListener("change", loadUpload);
referenceSelect.addEventListener("change", loadSelectedReference);
referenceInput.addEventListener("change", loadReference);
strengthInput.addEventListener("input", () => {
  strengthValue.value = strengthInput.value;
});
originalButton.addEventListener("click", playOriginal);
convertedButton.addEventListener("click", playConverted);
transformButton.addEventListener("click", transformAccent);
eraseButton.addEventListener("click", erase);
document.addEventListener("keydown", handleRecordKeyDown);
document.addEventListener("keyup", handleRecordKeyUp);

function handleRecordKeyDown(event) {
  if (event.code !== "KeyR" || event.repeat || event.ctrlKey || event.altKey || event.metaKey) return;
  event.preventDefault();
  if (processing) {
    message.textContent = "French-O-Matic is still processing the previous sentence.";
    return;
  }
  recordControlHeld = true;
  startRecording();
}

function handleRecordKeyUp(event) {
  if (event.code !== "KeyR") return;
  event.preventDefault();
  recordControlHeld = false;
  stopRecording();
}

function handleRecordPointerDown(event) {
  if (recordButton.disabled) return;
  event.preventDefault();
  recordButton.setPointerCapture?.(event.pointerId);
  recordControlHeld = true;
  startRecording();
}

function handleRecordPointerUp(event) {
  if (!recordControlHeld) return;
  event.preventDefault();
  recordControlHeld = false;
  stopRecording();
}

async function startRecording() {
  if (processing || startingRecording || recorder?.state === "recording") return;
  if (!consent.checked) {
    message.textContent = "Recording is not enabled.";
    return;
  }
  if (!referenceFile) {
    message.textContent = "Wait for a reference to load, or choose another reference.";
    return;
  }
  if (!engineReady) {
    message.textContent = "The Vevo engine is offline. Start it before recording.";
    return;
  }
  startingRecording = true;
  try {
    stopPlayback();
    clearCapturedAudio();
    stream = await navigator.mediaDevices.getUserMedia({ audio:{ echoCancellation:true, noiseSuppression:true, autoGainControl:true } });
    chunks = [];
    recorder = new MediaRecorder(stream);
    recorder.ondataavailable = (event) => event.data.size && chunks.push(event.data);
    recorder.onstop = captureComplete;
    recorder.start(250);
    startedAt = Date.now();
    timer = setInterval(updateClock, 100);
    setStep(1);
    instrument.className = "instrument recording";
    visualWord.textContent = "parlez";
    inputOptions.hidden = false;
    capturedActions.hidden = true;
    recordButton.textContent = "Recording — release R";
    message.textContent = "Listening. Keep holding R while you speak; release it to finish.";
    updateTimerDisplay(0, true);
    startWaveform();
    recordingTimeout = setTimeout(() => recorder?.state === "recording" && stopRecording(), MAX_RECORDING_SECONDS * 1000);
    updateControls();
    if (!recordControlHeld) stopRecording();
  } catch (error) {
    message.textContent = error.name === "NotAllowedError" ? "Microphone permission was declined." : error.message;
  } finally {
    startingRecording = false;
    updateControls();
  }
}

function stopRecording() {
  if (recorder?.state === "recording") recorder.stop();
}

async function captureComplete() {
  clearInterval(timer);
  clearTimeout(recordingTimeout);
  stopWaveform();
  stream?.getTracks().forEach((track) => track.stop());
  const duration = Math.min(MAX_RECORDING_SECONDS, (Date.now() - startedAt) / 1000);
  clock.textContent = "00:" + String(Math.floor(duration)).padStart(2,"0");
  updateTimerDisplay(duration, false);
  recordButton.textContent = "Hold R to record";
  if (duration < 1) {
    instrument.className = "instrument";
    visualWord.textContent = "encore";
    timerCaption.textContent = "hold for 1 sec";
    message.textContent = "Hold R for at least one second while speaking.";
    updateControls();
    return;
  }
  const blob = new Blob(chunks, { type:recorder.mimeType || "audio/webm" });
  acceptSource(blob, "Sentence captured");
  if (engineReady && referenceFile && consent.checked) await transformAccent();
}

async function loadUpload(event) {
  const file = event.target.files?.[0];
  if (!file) return;
  if (!consent.checked) {
    uploadInput.value = "";
    message.textContent = "Confirm the speaker's permission before choosing a recording.";
    return;
  }
  if (file.size > 25 * 1024 * 1024) {
    uploadInput.value = "";
    message.textContent = "Choose an audio file smaller than 25 MB.";
    return;
  }
  let context;
  try {
    context = new AudioContext();
    const decoded = await context.decodeAudioData(await file.arrayBuffer());
    const duration = decoded.duration;
    if (duration < 1 || duration > 15.5) throw new Error("Choose a recording between 1 and 15 seconds.");
    clock.textContent = `00:${String(Math.round(duration)).padStart(2,"0")}`;
    acceptSource(file, `${file.name} loaded`);
  } catch (error) {
    uploadInput.value = "";
    message.textContent = error.name === "EncodingError" ? "This browser could not decode that audio file." : error.message;
  } finally {
    await context?.close();
  }
}

async function loadSelectedReference() {
  const selected = referenceSelect.value;
  referenceInput.value = "";
  referenceFile = undefined;
  customReferencePicker.hidden = selected !== "custom";
  referenceLabel.textContent = "Choose reference";
  updateControls();

  if (selected === "custom") {
    message.textContent = consent.checked
      ? "Choose a 3–15 second French-accent reference recording."
      : "Reference uploads are not enabled.";
    return;
  }

  message.textContent = "Loading the selected French-accent reference…";
  try {
    const response = await fetch(selected, { cache:"no-store" });
    if (!response.ok) throw new Error("The selected reference could not be loaded.");
    const loadedReference = await response.blob();
    if (referenceSelect.value !== selected) return;
    referenceFile = loadedReference;
    const label = referenceSelect.options[referenceSelect.selectedIndex].textContent;
    message.textContent = `${label} is ready. Press R to record.`;
  } catch (error) {
    message.textContent = error.message;
  } finally {
    updateControls();
  }
}

async function loadReference(event) {
  const file = event.target.files?.[0];
  if (!file) return;
  if (!consent.checked) {
    referenceInput.value = "";
    message.textContent = "Confirm permission before choosing a reference recording.";
    return;
  }
  if (file.size > 25 * 1024 * 1024) {
    referenceInput.value = "";
    message.textContent = "Choose a reference file smaller than 25 MB.";
    return;
  }
  let context;
  try {
    context = new AudioContext();
    const decoded = await context.decodeAudioData(await file.arrayBuffer());
    if (decoded.duration < 3 || decoded.duration > 15.5) throw new Error("Choose a French-accent reference between 3 and 15 seconds.");
    referenceFile = file;
    referenceLabel.textContent = file.name;
    message.textContent = `${file.name} is ready. Press R to record.`;
    updateControls();
  } catch (error) {
    referenceInput.value = "";
    referenceFile = undefined;
    referenceLabel.textContent = "Upload reference";
    message.textContent = error.name === "EncodingError" ? "This browser could not decode that reference file." : error.message;
    updateControls();
  } finally {
    await context?.close();
  }
}

function acceptSource(blob, description) {
  if (recordingUrl) URL.revokeObjectURL(recordingUrl);
  recordingUrl = URL.createObjectURL(blob);
  instrument.className = "instrument";
  visualWord.textContent = "voilà";
  recordButton.textContent = "Hold R to record";
  inputOptions.hidden = true;
  capturedActions.hidden = false;
  if (!engineReady) message.textContent = `${description}. Start the Vevo engine, then apply the accent.`;
  else if (!referenceFile) message.textContent = `${description}. Now upload your French-accent reference.`;
  else message.textContent = `${description}. Processing the French accent automatically…`;
  updateControls();
}

function playOriginal() {
  stopPlayback();
  playing = new Audio(recordingUrl);
  playing.play();
  setStep(1);
  visualWord.textContent = "vous";
  message.textContent = "Playing the untouched recording.";
}

function playConverted() {
  stopPlayback();
  playing = new Audio(convertedUrl);
  playing.play();
  setStep(3);
  visualWord.textContent = "écoutez";
  message.textContent = "Playing the converted recording. Switch to Original for an immediate comparison.";
}

async function transformAccent() {
  if (processing) return;
  processing = true;
  stopPlayback();
  setStep(2);
  instrument.className = "instrument processing";
  visualWord.textContent = "un instant";
  timerCaption.textContent = "processing";
  capturedActions.hidden = true;
  message.textContent = "Separating the sentence, French accent style, and your vocal timbre locally…";
  updateControls();
  try {
    if (!referenceFile) throw new Error("Upload your French-accent reference first.");
    const [wav, referenceWav] = await Promise.all([audioToWav(recordingUrl), audioToWav(referenceFile, 15)]);
    const response = await fetch("/api/transform", {
      method:"POST",
      headers:{ "content-type":"application/json" },
      body:JSON.stringify({
        audioBase64:arrayBufferToBase64(wav),
        referenceAudioBase64:arrayBufferToBase64(referenceWav),
        caricatureStrength:Number(strengthInput.value) / 100,
        consent:consent.checked,
      }),
    });
    const result = await response.json();
    if (!response.ok) throw new Error(result.error || "Accent conversion failed.");
    const output = base64ToBlob(result.audioBase64,"audio/wav");
    if (convertedUrl) URL.revokeObjectURL(convertedUrl);
    convertedUrl = URL.createObjectURL(output);
    convertedButton.hidden = false;
    playing = new Audio(convertedUrl);
    let playedAutomatically = true;
    try {
      await playing.play();
    } catch {
      playedAutomatically = false;
    }
    instrument.className = "instrument";
    setStep(3);
    visualWord.textContent = "écoutez";
    timerCaption.textContent = "ready · hold R again";
    const identityNote = result.identityProtection ? " with participant identity protection" : "";
    const playbackNote = playedAutomatically ? "The converted recording is playing." : "Select Converted to play it.";
    message.textContent = `Your ${Math.round(result.caricatureStrength * 100)}% caricature completed locally in ${result.processingSeconds.toFixed(1)} seconds${identityNote}. ${playbackNote} Press R for the next person.`;
  } catch (error) {
    instrument.className = "instrument";
    visualWord.textContent = "pas encore";
    timerCaption.textContent = "try again";
    message.textContent = error.message;
  } finally {
    processing = false;
    capturedActions.hidden = false;
    updateControls();
  }
}

async function checkEngine() {
  try {
    const response = await fetch("/api/health", { cache:"no-store" });
    const health = await response.json();
    engineReady = health.engine === "vevo-ready";
  } catch { engineReady = false; }
  engineState.className = `engine-state ${engineReady ? "ready" : "offline"}`;
  engineState.innerHTML = `<i></i>${engineReady ? "Vevo ready / local" : "Vevo engine offline"}`;
  updateControls();
}

function updateControls() {
  const isRecording = recorder?.state === "recording";
  recordButton.disabled = isRecording ? false : processing || startingRecording || !engineReady || !referenceFile || !consent.checked;
  uploadInput.disabled = processing || startingRecording || !consent.checked;
  referenceSelect.disabled = processing || startingRecording || isRecording;
  referenceInput.disabled = processing || startingRecording || isRecording || !consent.checked || referenceSelect.value !== "custom";
  transformButton.disabled = processing || !engineReady || !recordingUrl || !referenceFile || !consent.checked;
}

async function audioToWav(source, maxSeconds = Infinity) {
  const encoded = typeof source === "string" ? await fetch(source).then((response) => response.arrayBuffer()) : await source.arrayBuffer();
  const context = new AudioContext();
  const decoded = await context.decodeAudioData(encoded);
  const mono = decoded.numberOfChannels === 1 ? decoded.getChannelData(0) : mixToMono(decoded);
  const maximumSamples = Math.min(mono.length, Math.floor(maxSeconds * decoded.sampleRate));
  const wav = encodeWav(mono.subarray(0, maximumSamples),decoded.sampleRate);
  await context.close();
  return wav;
}

function mixToMono(buffer) {
  const output = new Float32Array(buffer.length);
  for (let channel = 0; channel < buffer.numberOfChannels; channel += 1) {
    const values = buffer.getChannelData(channel);
    for (let index = 0; index < values.length; index += 1) output[index] += values[index] / buffer.numberOfChannels;
  }
  return output;
}

function encodeWav(samples,sampleRate) {
  const buffer = new ArrayBuffer(44 + samples.length * 2);
  const view = new DataView(buffer);
  const text = (offset,value) => [...value].forEach((letter,index) => view.setUint8(offset + index,letter.charCodeAt(0)));
  text(0,"RIFF"); view.setUint32(4,36 + samples.length * 2,true); text(8,"WAVE"); text(12,"fmt ");
  view.setUint32(16,16,true); view.setUint16(20,1,true); view.setUint16(22,1,true); view.setUint32(24,sampleRate,true);
  view.setUint32(28,sampleRate * 2,true); view.setUint16(32,2,true); view.setUint16(34,16,true); text(36,"data");
  view.setUint32(40,samples.length * 2,true);
  samples.forEach((sample,index) => view.setInt16(44 + index * 2,Math.max(-1,Math.min(1,sample)) * 0x7fff,true));
  return buffer;
}

function arrayBufferToBase64(buffer) {
  const bytes = new Uint8Array(buffer);
  let binary = "";
  for (let offset = 0; offset < bytes.length; offset += 0x8000) binary += String.fromCharCode(...bytes.subarray(offset,offset + 0x8000));
  return btoa(binary);
}

function base64ToBlob(value,mimeType) {
  const bytes = Uint8Array.from(atob(value),(character) => character.charCodeAt(0));
  return new Blob([bytes],{ type:mimeType });
}

function clearCapturedAudio() {
  if (recordingUrl) URL.revokeObjectURL(recordingUrl);
  if (convertedUrl) URL.revokeObjectURL(convertedUrl);
  recordingUrl = undefined;
  convertedUrl = undefined;
  convertedButton.hidden = true;
  capturedActions.hidden = true;
  inputOptions.hidden = false;
}

function erase() {
  stopPlayback();
  stream?.getTracks().forEach((track) => track.stop());
  chunks = [];
  clearTimeout(recordingTimeout);
  clearCapturedAudio();
  recordButton.textContent = "Hold R to record";
  uploadInput.value = "";
  referenceSelect.selectedIndex = 0;
  strengthInput.value = "80";
  strengthValue.value = "80";
  consent.checked = true;
  clock.textContent = "00:00";
  instrument.className = "instrument";
  visualWord.textContent = "bonjour";
  resetTimerDisplay();
  setStep(1);
  message.textContent = "Recording erased. Reloading the default reference…";
  loadSelectedReference();
}

function stopPlayback() {
  if (playing) { playing.pause(); playing.src = ""; playing = undefined; }
  audioContext?.close();
  audioContext = undefined;
}

function setStep(number) {
  document.querySelectorAll(".step").forEach((step) => step.classList.toggle("active", Number(step.dataset.step) === number));
}

function updateClock() {
  const seconds = Math.min(MAX_RECORDING_SECONDS, (Date.now() - startedAt) / 1000);
  clock.textContent = "00:" + String(Math.floor(seconds)).padStart(2,"0");
  updateTimerDisplay(seconds, true);
}

function updateTimerDisplay(elapsedSeconds, isRecording) {
  const progress = Math.max(0, Math.min(1, elapsedSeconds / MAX_RECORDING_SECONDS));
  timerProgress.style.strokeDashoffset = String(TIMER_CIRCUMFERENCE * progress);
  if (isRecording) {
    const remaining = Math.max(0, MAX_RECORDING_SECONDS - elapsedSeconds);
    timerCaption.textContent = remaining.toFixed(1) + " sec";
  } else {
    timerCaption.textContent = elapsedSeconds.toFixed(1) + " sec captured";
  }
}

function resetTimerDisplay() {
  clock.textContent = "00:00";
  timerProgress.style.strokeDashoffset = "0";
  timerCaption.textContent = MAX_RECORDING_SECONDS + " sec max";
}

function startWaveform() {
  audioContext = new AudioContext();
  analyser = audioContext.createAnalyser();
  analyser.fftSize = 512;
  audioContext.createMediaStreamSource(stream).connect(analyser);
  const data = new Uint8Array(analyser.frequencyBinCount);
  const draw = () => {
    const width = canvas.clientWidth;
    const height = canvas.clientHeight;
    const ratio = window.devicePixelRatio || 1;
    canvas.width = width * ratio;
    canvas.height = height * ratio;
    const context = canvas.getContext("2d");
    context.scale(ratio,ratio);
    context.clearRect(0,0,width,height);
    analyser.getByteTimeDomainData(data);
    context.strokeStyle = "#e84b31";
    context.lineWidth = 2;
    context.beginPath();
    data.forEach((value,index) => {
      const x = index / (data.length - 1) * width;
      const y = value / 255 * height;
      if (index) context.lineTo(x,y); else context.moveTo(x,y);
    });
    context.stroke();
    frame = requestAnimationFrame(draw);
  };
  draw();
}

function stopWaveform() {
  cancelAnimationFrame(frame);
  audioContext?.close();
  audioContext = undefined;
  canvas.getContext("2d").clearRect(0,0,canvas.width,canvas.height);
}
