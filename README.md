# Room Presence Detector

Ultrasonic sonar-based room presence detection for Windows. Uses your laptop's built-in speakers and microphone to detect whether someone is in the room, and auto-locks the PC when the room is empty.

## How It Works

The app emits an 18kHz ultrasonic chirp from the speakers every 2 seconds and records the echo via the microphone. Using FFT analysis, it measures the energy in the 17–19kHz band. When a person is in the room, the echo pattern changes (reflections off the person's body alter the signal). The app compares the current echo energy against a calibrated baseline to determine presence.

## Installation

### Prerequisites
- Python 3.11+
- Windows 11

### Setup

```bash
# Create a virtual environment
python -m venv venv
venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

All dependencies install cleanly via pip — no C compiler required. `sounddevice` bundles the PortAudio binary.

## IMPORTANT: Disable Microphone Echo Cancellation

Windows enables echo cancellation on laptop microphones by default. This suppresses speaker audio from reaching the mic — which breaks the sonar approach. **You must disable audio enhancements** before the app will work:

### Method 1: Windows Settings (Windows 11)
1. Open **Settings > System > Sound**
2. Under Input, click your **Microphone**
3. Set **Audio enhancements** to **Off**

### Method 2: Control Panel (works on all Windows versions)
1. Open **Control Panel > Sound** (or run `mmsys.cpl`)
2. Go to the **Recording** tab
3. Right-click your **Microphone** > **Properties**
4. Go to the **Advanced** tab
5. Uncheck **"Enable audio enhancements"**
6. Click **Apply**

The app runs a diagnostic on startup and will show a warning with an "Open Sound Settings" button if echo cancellation is detected.

## Usage

```bash
python -m presence_detector.main
```

On first launch:
1. **Leave the room empty** for 10 seconds while calibration runs
2. The HUD will show "CALIBRATING..." during this phase
3. Once calibrated, the status switches to "PRESENT" or "EMPTY"

### System Tray
- **Left-click** the tray icon to toggle the HUD window
- **Right-click** for the context menu: Show HUD, Recalibrate, Auto-Lock toggle, Quit

### HUD Window
- Drag anywhere to reposition
- Shows real-time status, confidence score, and echo energy
- **Recalibrate** button: re-run calibration (leave the room empty)
- **Auto-Lock** checkbox: enable/disable automatic Windows locking

## Configuration

All parameters are in `presence_detector/config.py`:

| Parameter | Default | Description |
|---|---|---|
| `CHIRP_FREQ` | 18000 Hz | Ultrasonic chirp frequency |
| `CHIRP_DURATION` | 0.05 s | Chirp burst length (50ms) |
| `SAMPLE_RATE` | 44100 Hz | Audio sample rate |
| `RECORD_DURATION` | 0.20 s | Echo recording window |
| `CYCLE_INTERVAL` | 2.0 s | Time between chirps |
| `BAND_LOW` | 17000 Hz | FFT analysis band lower bound |
| `BAND_HIGH` | 19000 Hz | FFT analysis band upper bound |
| `CALIBRATION_DURATION` | 10.0 s | Calibration phase length |
| `PRESENCE_THRESHOLD` | 2.0 | Std deviations from baseline to trigger presence |
| `EMPTY_DEBOUNCE_COUNT` | 3 | Consecutive empty readings before confirming |
| `AUTO_LOCK_ENABLED` | True | Auto-lock the PC when empty |
| `LOCK_DELAY_SECONDS` | 0.0 | Extra delay after debounce before locking |

## Frequency Tuning

If 18kHz is audible to you (common for younger people):

1. Open `presence_detector/config.py`
2. Change `CHIRP_FREQ` to `19000` or `20000`
3. Adjust `BAND_LOW` and `BAND_HIGH` accordingly (e.g., `19000`–`21000` for a 20kHz chirp)
4. Recalibrate after changing

**Note:** Higher frequencies may have weaker speaker/mic response on some laptops. If the app warns about low signal, try lowering the frequency instead.

## Troubleshooting

- **"Microphone echo cancellation is active"**: The most common issue. See the "Disable Microphone Echo Cancellation" section above. The app cannot work until this is fixed.
- **"No microphone found" / "No speaker found"**: Check Windows sound settings, ensure devices are enabled and set as default
- **"Very low signal" warning**: Your laptop's speakers/mic may not respond well at 18kHz. Try lowering `CHIRP_FREQ` to 16000 or 17000
- **False positives**: Increase `PRESENCE_THRESHOLD` (e.g., to 3.0 or 4.0)
- **Slow to detect empty room**: Decrease `EMPTY_DEBOUNCE_COUNT` (minimum 1)
- **App locks too quickly**: Increase `LOCK_DELAY_SECONDS` (e.g., 10.0 for a 10-second grace period)
