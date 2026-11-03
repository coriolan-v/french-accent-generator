#include <Keyboard.h>
#include <FastLED.h>

// SparkFun Pro Micro (ATmega32u4, native USB). The button acts as a USB keyboard
// key: F13 is held down while the button is pressed, and index.html decides
// between hold-to-talk and a hands-free message. The page reports its state
// back over USB serial, and the LED strip around the base of the Louvre
// pyramid shows it.
constexpr uint8_t BUTTON_PIN = 2;
constexpr uint8_t LED_PIN = 3;
constexpr uint16_t LED_COUNT = 103;
constexpr uint8_t BRIGHTNESS = 150;
constexpr uint16_t MAX_MILLIAMPS = 500;  // USB-safe; raise when the strip has its own 5 V supply.
constexpr uint8_t RECORD_KEY = KEY_F13;  // index.html listens for F13; it types nothing.
constexpr unsigned long DEBOUNCE_MS = 30;
constexpr unsigned long RECORD_MS = 15000;  // Matches MAX_SECONDS in index.html.
constexpr unsigned long CANCEL_BLINK_MS = 1500;
constexpr unsigned long FADE_MS = 1500;  // Crossfade into idle; the round display fades over the same time.
constexpr unsigned long FRAME_MS = 20;
constexpr uint8_t BREATHS_PER_MIN = 10;

// To find the real LED count: set LED_COUNT too high (e.g. 150), upload, and click
// "LED numbers" on the operator page. LED 0 is green, every 10th LED is red.

const CRGB WARM_WHITE(212, 100, 20);
const CRGB FLAG_BLUE(0, 0, 255);
const CRGB FLAG_WHITE(255, 255, 255);
const CRGB FLAG_RED(255, 0, 0);

// What the web page is doing; it sends one letter per change (see readHost).
enum State : uint8_t { IDLE, RECORDING, WORKING, PLAYING, CANCELLED, NUMBERS };

CRGB leds[LED_COUNT];
// The flag layout comes from the page as "F", stretches along the strip from LED 0, then ";".
// "F25r26w25b;" is 25 red LEDs, then 26 white, then 25 blue; the rest stays dark.
char flag[LED_COUNT];  // per LED: 'b', 'w', 'r', or anything else for dark
bool readingFlag = false;
uint16_t flagAt = 0;
uint16_t flagRun = 0;
State state = IDLE;
uint8_t idlePeak = 0;
bool rawPressed = false;
bool stablePressed = false;
bool armed = false;
bool keyHeld = false;
unsigned long rawChangedAt = 0;
unsigned long pressedAt = 0;
unsigned long stateAt = 0;
unsigned long lastFrameAt = 0;
// The last frame before idle, as the strip showed it, to crossfade from.
CRGB fadeFrom[LED_COUNT];
unsigned long fadeAt = 0;
State shown = IDLE;
uint8_t shownBrightness = 255;

void readButton(unsigned long now) {
  const bool pressed = digitalRead(BUTTON_PIN) == LOW;
  if (pressed != rawPressed) {
    rawPressed = pressed;
    rawChangedAt = now;
  }
  if (now - rawChangedAt < DEBOUNCE_MS) return;

  // Require a released button after boot, before sending any keystrokes.
  if (!rawPressed) armed = true;
  if (stablePressed == rawPressed) return;
  stablePressed = rawPressed;

  if (stablePressed && armed) {
    pressedAt = now;
    Keyboard.press(RECORD_KEY);
    keyHeld = true;
  } else if (!stablePressed && keyHeld) {
    Keyboard.release(RECORD_KEY);
    keyHeld = false;
  }
}

void readFlag(char c) {
  if (c >= '0' && c <= '9') {
    flagRun = flagRun * 10 + (c - '0');
  } else if (c == ';') {
    memset(flag + flagAt, 0, LED_COUNT - flagAt);
    readingFlag = false;
  } else {
    for (; flagRun > 0 && flagAt < LED_COUNT; --flagRun) flag[flagAt++] = c;
    flagRun = 0;
  }
}

// One letter per state: I idle, R recording, W working, P playing (the flag),
// C cancelled, N LED numbers. "F...;" sets the flag layout (see flag).
void readHost(unsigned long now) {
  while (Serial.available()) {
    const char c = Serial.read();
    if (c == 'F') {
      readingFlag = true;
      flagAt = flagRun = 0;
      continue;
    }
    if (readingFlag) {
      readFlag(c);
      continue;
    }
    switch (c) {
      case 'I': state = IDLE; break;
      case 'R': state = RECORDING; break;
      case 'W': state = WORKING; break;
      case 'P': state = PLAYING; break;
      case 'C': state = CANCELLED; break;
      case 'N': state = NUMBERS; break;
      default: continue;
    }
    stateAt = now;
  }
  if (state == CANCELLED && now - stateAt >= CANCEL_BLINK_MS) state = IDLE;
}

void showNumbers() {
  fill_solid(leds, LED_COUNT, CRGB(0, 0, 20));
  for (uint16_t i = 10; i < LED_COUNT; i += 10) leds[i] = CRGB::Red;
  leds[0] = CRGB::Green;
}

// Slow warm-white breathing, scaled here in 16 bits instead of by FastLED. Each
// LED rounds up at a different point, so the strip fades evenly instead of all
// LEDs jumping between the few 8-bit levels available at low brightness.
void showIdle() {
  const uint16_t wave = beatsin16(BREATHS_PER_MIN, 0, 65535);
  const uint16_t eased = scale16(wave, wave);  // Squared, so the fade looks even to the eye.
  const uint16_t level = scale16(idlePeak * 257U, 16384 + scale16(eased, 49151));  // 25-100 % of peak.
  for (uint16_t i = 0; i < LED_COUNT; ++i) {
    const uint32_t dither = uint32_t(uint8_t(i * 159)) << 8;  // Rounding points spread along the strip.
    leds[i].r = (WARM_WHITE.r * uint32_t(level) + dither) >> 16;
    leds[i].g = (WARM_WHITE.g * uint32_t(level) + dither) >> 16;
    leds[i].b = (WARM_WHITE.b * uint32_t(level) + dither) >> 16;
  }
}

void animateBase(unsigned long now) {
  if (now - lastFrameAt < FRAME_MS) return;
  lastFrameAt = now;

  if (state == IDLE && shown != IDLE) {
    for (uint16_t i = 0; i < LED_COUNT; ++i) {
      fadeFrom[i] = leds[i];
      fadeFrom[i].nscale8(shownBrightness);
    }
    fadeAt = now;
  }
  shown = state;

  if (state == NUMBERS) {
    showNumbers();
  } else if (state == IDLE) {
    showIdle();
    if (now - fadeAt < FADE_MS) {
      const fract8 toIdle = (now - fadeAt) * 255 / FADE_MS;
      for (uint16_t i = 0; i < LED_COUNT; ++i) leds[i] = blend(fadeFrom[i], leds[i], toIdle);
    }
    shownBrightness = 255;
    FastLED.show(255);  // Already scaled within the power budget, and so is a blend of two such frames.
    return;
  } else if (state == RECORDING) {
    // Red fills the base like the UI's 15 s progress bar.
    const uint16_t filled = min((now - stateAt) * LED_COUNT / RECORD_MS, (unsigned long)LED_COUNT);
    fill_solid(leds, LED_COUNT, CRGB(30, 0, 0));
    fill_solid(leds, filled, CRGB(255, 10, 0));
  } else if (state == WORKING) {
    // Warm comet circling the base while the engine converts the voice.
    fadeToBlackBy(leds, LED_COUNT, 40);
    leds[(now / 25) % LED_COUNT] = WARM_WHITE;
  } else if (state == PLAYING) {
    // The French flag while the result plays, laid out by the page.
    for (uint16_t i = 0; i < LED_COUNT; ++i) {
      leds[i] = flag[i] == 'b' ? FLAG_BLUE : flag[i] == 'w' ? FLAG_WHITE : flag[i] == 'r' ? FLAG_RED : CRGB(0, 0, 0);
    }
  } else {
    // Cancelled because nobody spoke: blink amber, then back to idle.
    fill_solid(leds, LED_COUNT, (now - stateAt) / 250 % 2 ? CRGB(0, 0, 0) : CRGB(255, 80, 0));
  }
  // Scale to BRIGHTNESS, or lower if the frame would draw more than MAX_MILLIAMPS.
  shownBrightness = calculate_max_brightness_for_power_mW(leds, LED_COUNT, BRIGHTNESS, 5UL * MAX_MILLIAMPS);
  FastLED.show(shownBrightness);
}

void setup() {
  pinMode(BUTTON_PIN, INPUT_PULLUP);
  rawPressed = digitalRead(BUTTON_PIN) == LOW;
  stablePressed = rawPressed;
  rawChangedAt = millis();
  FastLED.addLeds<WS2812B, LED_PIN, GRB>(leds, LED_COUNT);
  // Temporal dithering needs a far higher frame rate; the idle fade dithers along the strip instead.
  FastLED.setDither(DISABLE_DITHER);
  // Brightest idle level within the power budget. FastLED's estimate dims the LEDs'
  // own ~1 mA draw along with the colors, so reserve that, plus a margin for rounding.
  fill_solid(leds, LED_COUNT, WARM_WHITE);
  idlePeak = calculate_max_brightness_for_power_mW(leds, LED_COUNT, BRIGHTNESS, 5UL * (MAX_MILLIAMPS - LED_COUNT) * 9 / 10);
  FastLED.clear(true);
  Serial.begin(115200);
  Keyboard.begin();
}

void loop() {
  const unsigned long now = millis();
  readButton(now);
  if (Serial.dtr()) {
    readHost(now);
  } else {
    // Web page not connected: the strip can only follow the button itself.
    state = keyHeld ? RECORDING : IDLE;
    stateAt = pressedAt;
  }
  animateBase(now);
}
