# French-O-Matic physical button

Use an ATmega32U4 Pro Micro, Arduino Leonardo, or Micro with native USB keyboard support. A classic Uno R3 or Nano will not run this keyboard sketch as-is. The computer's microphone captures the audio; the Arduino controls the existing browser app by holding the `R` key.

## Wiring

| Part | Connection |
| --- | --- |
| Button normally-open switch contact | D2 |
| Button other switch contact (COM) | Arduino GND |
| Ring data input (DIN) | D6 through a 330–470 ohm resistor |
| Ring GND | External supply GND and Arduino GND |
| Ring power | External regulated supply matching the ring's marked voltage |
| Arduino USB | Computer running French-O-Matic |

Use the switch terminals, not the big button's lamp terminals. The sketch enables the internal pull-up resistor, so closing the button connects D2 to ground.

Check the ring's rated voltage: WS2811 products can use different supply voltages. Do not feed a 12 V ring supply into an Arduino 5 V pin. Power the ring from its external supply, keep the Arduino USB powered, and connect their grounds. Size the supply for the ring's specified maximum current. For a 5 V ring with 20 conventional RGB pixels, allow approximately 1.2 A at full white (a 5 V, 2 A supply provides margin). A 500–1000 uF capacitor across ring power and ground near the ring is useful; its voltage rating must exceed the supply voltage.

`LED_COUNT = 20` means 20 independently addressable pixels. Some WS2811 strips control groups of three physical LEDs per pixel. Change the count if your hardware uses grouped LEDs.

## Upload and use

### PlatformIO (Pro Micro)

Open the repository root in VS Code with PlatformIO installed. The root `platformio.ini` builds the existing `.ino` directly and installs FastLED and Keyboard automatically.

The default environment is `promicro16` for a **5 V / 16 MHz** Pro Micro. For a **3.3 V / 8 MHz** board, select `promicro8` in PlatformIO or change `default_envs` to `promicro8`. Match the markings on your board; a 3.3 V board may also need a data level shifter for the ring.

From the repository root, use the PlatformIO terminal:

```powershell
pio run -e promicro16
pio run -e promicro16 -t upload
```

Replace `promicro16` with `promicro8` for the 8 MHz board. PlatformIO normally detects the upload port; if needed add `--upload-port COM5` with your actual port. If a clone does not enter its bootloader automatically, briefly connect RST to GND twice to enter the bootloader and retry upload.

After uploading, follow steps 4–5 below to use the browser app.

### Arduino IDE

1. Open `FrenchOMaticButton/FrenchOMaticButton.ino` in Arduino IDE.
2. Install **FastLED** using Library Manager, and install **Keyboard** if it is missing.
3. Select your Leonardo or Micro board and USB port, then upload.
4. Start the engine and web app as described in the main README. Open the app and keep its browser tab focused. The device sends keystrokes to whichever application has focus.
5. Confirm the engine and reference are ready, then hold the big button for at least one second while speaking. Grant microphone permission on first use. Release to finish and automatically process the recording.

The ring breathes blue and rotates slowly while idle, then spins red while the button sends `R`. After 15 seconds it releases `R` and glows amber until you release the button. A held button at startup must be released before it can trigger recording. Switch bounce is filtered without blocking the animation.

The ring shows the button's local state. USB keyboard control provides no feedback about microphone permission, engine readiness, processing, or playback; a red ring does not confirm the browser accepted the recording. Wait until the app finishes processing before recording again.

Adjust `BRIGHTNESS`, `LED_PIN`, or animation speeds in the sketch as needed. If colors are wrong, change `RGB` in `FastLED.addLeds` to your ring's color order (often `GRB`). If the hardware is actually WS2812B, change `WS2811` to `WS2812B` and use the appropriate color order.

## Validation

Hardware checks: power on with the button held (no key should be sent), release and press again, check a short tap, check a normal hold/release, and hold beyond 15 seconds (no second recording until released). Verify the ring has all 20 addressable pixels and the expected colors.

The sketch compiles successfully with PlatformIO for both `promicro16` and `promicro8`. It has not been uploaded or tested on hardware in this workspace.
