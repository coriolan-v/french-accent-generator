#include <Keyboard.h>
#include <FastLED.h>

// Arduino Leonardo / Micro (ATmega32u4, native USB).
constexpr uint8_t BUTTON_PIN = 2;
constexpr uint8_t LED_PIN = 6;
constexpr uint8_t LED_COUNT = 20;
constexpr uint8_t BRIGHTNESS = 64;
constexpr unsigned long DEBOUNCE_MS = 30;
constexpr unsigned long MAX_HOLD_MS = 15000;
constexpr unsigned long FRAME_MS = 20;

CRGB leds[LED_COUNT];
bool rawPressed = false;
bool stablePressed = false;
bool armed = false;
bool keyHeld = false;
unsigned long rawChangedAt = 0;
unsigned long pressedAt = 0;
unsigned long lastFrameAt = 0;

void releaseRecordKey() {
  if (keyHeld) Keyboard.release('r');
  keyHeld = false;
}

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
    Keyboard.press('r');
    keyHeld = true;
  } else if (!stablePressed) {
    releaseRecordKey();
  }
}

void animateRing(unsigned long now) {
  if (now - lastFrameAt < FRAME_MS) return;
  lastFrameAt = now;

  if (keyHeld) {
    fill_solid(leds, LED_COUNT, CRGB(24, 0, 0));
    const uint8_t head = ((now - pressedAt) / 65) % LED_COUNT;
    for (uint8_t tail = 0; tail < 6; ++tail) {
      const uint8_t index = (head + LED_COUNT - tail) % LED_COUNT;
      leds[index] = CRGB(255 >> tail, 30 >> tail, 4 >> tail);
    }
  } else if (stablePressed && armed) {
    // Fifteen-second limit reached: release before another recording.
    fill_solid(leds, LED_COUNT, CRGB(32, 12, 0));
  } else {
    // Soft blue breathing glow with a slow orbiting highlight.
    const uint8_t glow = beatsin8(12, 8, 35);
    fill_solid(leds, LED_COUNT, CRGB(0, glow / 2, glow));
    const uint8_t head = (now / 180) % LED_COUNT;
    leds[head] = CRGB(10, 60, 100);
    leds[(head + LED_COUNT - 1) % LED_COUNT] = CRGB(0, 30, 60);
  }
  FastLED.show();
}

void setup() {
  pinMode(BUTTON_PIN, INPUT_PULLUP);
  rawPressed = digitalRead(BUTTON_PIN) == LOW;
  stablePressed = rawPressed;
  rawChangedAt = millis();
  FastLED.addLeds<WS2811, LED_PIN, RGB>(leds, LED_COUNT);
  FastLED.setBrightness(BRIGHTNESS);
  FastLED.clear(true);
  Keyboard.begin();
}

void loop() {
  const unsigned long now = millis();
  readButton(now);
  if (keyHeld && now - pressedAt >= MAX_HOLD_MS) releaseRecordKey();
  animateRing(now);
}
