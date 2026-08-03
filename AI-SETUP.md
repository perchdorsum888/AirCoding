# AirCoding Environment Setup Guide (For AI Agents)

> **Purpose**: This document is meant to be read and executed by Claude-like AI coding assistants (Claude Code, WorkBuddy, Cursor, Windsurf, etc.) to configure the AirCoding project from zero to a working state.
> **Principles**: Follow the steps strictly in order; every step includes "command → expected output → failure recovery"; never skip verification.
>
> 🇨🇳 中文版见 [AI-SETUP.cn.md](AI-SETUP.cn.md)

---

## 0. What This Project Is

AirCoding is a **Windows desktop application** that uses your webcam to recognize hand/face gestures in real time and maps them to keyboard keys and voice-input hotkeys — built for hands-free control in vibecoding workflows.

| Dimension | Description |
|-----------|-------------|
| Stack | Python + MediaPipe (gesture recognition) + PySide6/Qt6 (GUI) + OpenCV (camera) + pynput (keyboard injection) |
| Runtime form | Always-on floating panel + system tray icon, NOT a CLI tool |
| Hardware dependency | **A working webcam is required** (built-in or USB) |
| Platform limit | **Windows 10/11 only** (depends on pywin32, uiautomation etc. — cannot run on macOS/Linux) |

---

## 1. Prerequisites Check (Gate 0 — stop if not met)

### 1.1 Operating System

- **Required**: Windows 10 or Windows 11 (64-bit)
- Verify: `cmd /c ver` — output should contain `Windows` with version ≥ 10.0

### 1.2 Python Version (Critical Constraint)

- **Required**: Python **3.10 / 3.11 / 3.12** — exactly one of these
- **Forbidden**: Python 3.13+ — MediaPipe has no compatible wheel for 3.13; install will fail
- **Forbidden**: Python 3.9 or lower — PySide6 ≥ 6.5 needs 3.9+, and the code uses newer syntax

Verify (run in project root):

```powershell
python -c "import sys; v=sys.version_info[:2]; print(v); exit(0 if (3,10)<=v<(3,13) else 1)"
```

Expected: `(3, 10)`, `(3, 11)` or `(3, 12)`, exit code 0.

**Recovery**: If the version is wrong, have the user install 3.12.x from https://www.python.org/downloads/ and check **Add Python to PATH**. If the py launcher is present, you can use `py -3.12` instead of `python`.

### 1.3 Hardware

- A webcam exists and is not exclusively held by another app (verify at runtime — see §5).

---

## 2. Critical Constraints & Known Traps (READ BEFORE EXECUTING)

These three items are hard-won lessons. Violating any of them causes runtime failures or hard-to-diagnose bugs:

### 2.1 MediaPipe Version Ceiling (THE most important trap)

- `requirements.txt` already pins `mediapipe>=0.10.0,<0.10.15`. **Do not loosen this.**
- **Why**: MediaPipe 0.10.15+ removed the legacy `mediapipe.python.solutions` API that this project's code depends on.
- **Symptom** (if 0.10.15+ is installed): the app starts, UI shows, camera LED lights up, but the **preview is blank**; the log (`%APPDATA%\AirCoding\logs\aircoding.log`) contains `No module named 'mediapipe.python'`.
- **Fix**: `.venv_run\Scripts\python.exe -m pip install "mediapipe>=0.10.0,<0.10.15" --force-reinstall`

### 2.2 Virtual Environment MUST Be Named `.venv_run`

- `start.bat` hardcodes the path `.venv_run\Scripts\pythonw.exe`.
- You MUST use this exact directory name when creating the venv, or the launcher cannot find the interpreter.

### 2.3 `start.bat` Conventions (the only .bat launcher in the repo)

- `start.bat` is the only batch file in the repo (a launcher, NOT an installer — `安装.bat` was removed).
- It is a pure-ASCII script (no Chinese output), so **there is no encoding constraint**; but when editing keep:
  - Line endings: **CRLF** (Windows style)
  - The hardcoded path `.venv_run\Scripts\pythonw.exe` must not change
- If you ever add Chinese output to it, it must be GBK (CP936) encoded. Conversion command:
  ```powershell
  $p="full path to start.bat"; $t=[IO.File]::ReadAllText($p,[Text.Encoding]::UTF8); $t=($t -replace "`r`n","`n") -replace "`n","`r`n"; [IO.File]::WriteAllText($p,$t,[Text.Encoding]::GetEncoding(936))
  ```

---

## 3. Get the Code

```bash
git clone https://github.com/mushi888/AirCoding.git
cd AirCoding
```

If the user already has a local copy, skip cloning and `cd` into the project root (you should see `main.py`, `requirements.txt`, `start.bat`).

---

## 4. Environment Installation (single path)

> `安装.bat` was removed in favor of this guide — the AI agent IS the installer. Follow the steps below exactly; they cover everything the old script did (venv creation, pip source choice, dependency install, verification).

### Step 1: Create venv (name MUST be `.venv_run`)

```powershell
python -m venv .venv_run
```

### Step 2: Upgrade pip

```powershell
.venv_run\Scripts\python.exe -m pip install --upgrade pip
```

### Step 3: Install all dependencies (~400MB, 3-15 min depending on network)

```powershell
.venv_run\Scripts\python.exe -m pip install -r requirements.txt --retries 5 --timeout 120
# Global users: pip uses PyPI by default (no flags needed)
# China users: append -i https://pypi.tuna.tsinghua.edu.cn/simple
```

**Step 3 recovery**: if pip is interrupted, just re-run the same command — pip skips already-installed packages (idempotent).

---

## 5. Installation Verification (Gate 1 — all must pass)

### 5.1 Dependency Import Check

```powershell
.venv_run\Scripts\python.exe -c "import mediapipe, cv2, numpy, PySide6, pynput, win32gui, psutil, uiautomation, yaml; print('deps OK, mediapipe =', mediapipe.__version__)"
```

- Expected: `deps OK, mediapipe = 0.10.14` (version must be `0.10.x` with `x < 15`)
- If mediapipe ≥ 0.10.15 → apply the §2.1 downgrade

### 5.2 MediaPipe API Compatibility Check (project-specific, MANDATORY)

```powershell
.venv_run\Scripts\python.exe -c "from mediapipe.python.solutions import hands, face_mesh; h=hands.Hands(); f=face_mesh.FaceMesh(); h.close(); f.close(); print('MediaPipe legacy API OK')"
```

- Expected: `MediaPipe legacy API OK`
- Side effect: MediaPipe downloads its bundled models (hands/face_mesh) on first run — normal.
- If `ModuleNotFoundError: No module named 'mediapipe.python'` → mediapipe too new, apply §2.1 fix.

### 5.3 Unit Tests

```powershell
.venv_run\Scripts\python.exe -m pytest tests/ -q
```

- Expected: `46 passed` (warnings allowed; failed/error not allowed)

---

## 6. Launch the App

| Method | Command | Use case |
|--------|---------|----------|
| Silent launch (recommended) | double-click `start.bat` | Daily use, no console window |
| Dev mode | `.venv_run\Scripts\python.exe main.py` | Debugging, live logs in console |
| pythonw direct | `.venv_run\Scripts\pythonw.exe -B main.py` | Same as start.bat |

**Must run from the project root** (code uses relative imports `from src.xxx`; wrong CWD gives `ModuleNotFoundError: No module named 'src'`).

---

## 7. Post-Launch Acceptance (Gate 2 — confirm the app actually works)

Check the following after launch:

1. **UI appears**: semi-transparent floating panel in the bottom-right corner (default).
2. **Camera active**: webcam LED is on.
3. **Video preview works**: the preview area shows the camera feed (with skeleton overlay). **If the preview is blank but the LED is on → 90% a mediapipe version issue (see §2.1)**.
4. **First-run tutorial**: the onboarding flow appears on first launch and writes its config when done.
5. **Gestures work**: try the gestures below and watch the panel light effect and injected keys.

| Gesture | Triggered action |
|---------|------------------|
| 👌 OK | Enter |
| ✋ Open palm | Escape |
| ✌️ Scissor | Ctrl+Z |
| 🤏 Pinch (hold 1.5s) | Toggle Auto-Approve / Manual Confirm mode |
| 🤙 Phone call | Detect foreground AI app and inject its voice-input hotkey |

6. **Global hotkey**: `Ctrl+Alt+K` toggles the panel.

### Recognition not accurate?

Open Settings (⚙️ on the panel) and run **gesture calibration** (fingerprint-style registration: 6 gestures × 30 frames each). Data is saved to `%APPDATA%\AirCoding\calibration_profile.json` and keeps adapting during use.

---

## 8. Troubleshooting Table (symptom → cause → fix)

| Symptom | Likely cause | Fix |
|---------|--------------|-----|
| UI OK + camera LED on + blank preview | mediapipe ≥ 0.10.15 (API removed) | downgrade per §2.1 |
| Log: `No module named 'mediapipe.python'` | same as above | downgrade per §2.1 |
| start.bat: `Python venv not found` | venv name isn't `.venv_run` or missing | rebuild per §4, name MUST be `.venv_run` |
| start.bat garbled/failing | file got corrupted or wrong line endings | re-save with CRLF line endings per §2.3 |
| `No module named 'src'` on launch | wrong working directory | `cd` to project root first |
| pip can't find mediapipe | Python is 3.13+ | install 3.10~3.12 (see §1.2) |
| Camera won't open / LED off | held by another app (Teams, Zoom, WeChat) | close the holder and restart; the app also auto-recovers |
| Gestures unresponsive | not calibrated / hand outside valid area | keep hand inside dashed circle; run calibration |
| Unit tests fail | polluted environment (repeated installs/uninstalls) | delete `.venv_run` and do a fresh install per §4 |

**Log location**: `%APPDATA%\AirCoding\logs\aircoding.log` (falls back to project `logs/` if APPDATA is unset). First troubleshooting step: read the last 50 lines.

---

## 9. Runtime Data Locations (for troubleshooting & backup)

| Data | Path | Description |
|------|------|-------------|
| User config | `%APPDATA%\AirCoding\user_config.yaml` | Overrides same keys in `config/default_config.yaml` |
| Calibration profile | `%APPDATA%\AirCoding\calibration_profile.json` | Gesture features & thresholds |
| Runtime log | `%APPDATA%\AirCoding\logs\aircoding.log` | Primary troubleshooting source |
| Factory config | `config/default_config.yaml` in repo | Do not edit; use user config |

**Factory reset**: delete the whole `%APPDATA%\AirCoding\` directory (config, calibration, logs all reset) — project code untouched.

---

## 10. Helper Tools

```powershell
# Real-camera gesture test (collects 30 frames per gesture, prints recognition quality report)
.venv_run\Scripts\python.exe test_runner.py --frames 30

# Fully automatic mode (no Enter needed)
.venv_run\Scripts\python.exe test_runner.py --frames 30 --auto

# Analyze a past test log
.venv_run\Scripts\python.exe test_runner.py --analyze <log-file-path>
```

---

## 11. Project Structure Quick Reference

```
AirCoding/
├── main.py                  # Entry: module init + signal wiring + Qt event loop
├── test_runner.py           # Real-camera test tool
├── start.bat                  # Silent launcher (hardcodes .venv_run path)
├── AI-SETUP.md              # This guide (AI-agent environment setup)
├── requirements.txt         # Deps (mediapipe ceiling <0.10.15 — do not touch)
├── config/default_config.yaml  # Factory config (gestures/thresholds/AI registry/effects)
├── resources/               # App icons
├── src/
│   ├── core/                # enums, config, i18n, state machine
│   ├── camera/              # capture (10fps dedicated thread), image preprocessing
│   ├── recognition/         # MediaPipe inference, gesture classifier, calibration
│   ├── action/              # keyboard injection, AI app detection, auto-approval
│   ├── ui/                  # main window, privacy preview, settings, onboarding, effects
│   └── utils/               # logging, audio feedback
└── tests/                   # pytest unit tests (46 cases)
```

---

## 12. Definition of Done

The AI agent has finished this guide only when ALL of the following are "yes":

- [ ] Python version is within 3.10~3.12
- [ ] `.venv_run` exists and every dependency in `requirements.txt` installed
- [ ] mediapipe < 0.10.15, and `mediapipe.python.solutions` imports
- [ ] `pytest tests/ -q` fully passes (46 passed)
- [ ] After launch: UI shows, camera LED on, **preview shows video**
- [ ] At least one gesture (✋ recommended) triggers its keyboard action

All met → environment is ready, the app works. Any not met → locate and fix via §8.
