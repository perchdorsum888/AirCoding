# AirCoding Delivery Overview

> 🇨🇳 中文版见 [overview.cn.md](overview.cn.md)

## Current Status

PRD v3.1 ✅ → Architecture v1.0 ✅ → Code ✅ → Tests 46/46 ✅ → Fingerprint-style calibration + continuous adaptation ✅

## Calibration System Design (like enrolling a fingerprint)

### 1. Initial Registration Flow

Click the 🎯 button → registration dialog opens, capture each gesture one by one:

| Step | Gesture | Description | Frames |
|------|---------|-------------|--------|
| 1 | 👌 OK | Thumb and index form a circle, other fingers straight | 30 |
| 2 | ✋ Open palm | Five fingers spread, palm facing camera | 30 |
| 3 | ✌️ Scissor | Index and middle fingers extended in a V | 30 |
| 4 | 🤏 Pinch | Thumb tip and index tip touching, other fingers curled | 30 |
| 5 | 🤙 Phone call | Thumb to ear, pinky to mouth | 30 |

**Registration process**:
- Top progress indicator (6 icons: done=green, current=cyan, pending=gray)
- Big emoji + gesture name + action description
- Real-time progress bar (0/30 → 30/30)
- Real-time status showing current gesture recognition result
- Any gesture can be skipped

**Features captured per frame**:
- Extension ratio of 5 fingers (fingertip-to-wrist distance / MCP-to-wrist distance)
- Thumb direction (y component)
- Thumb-index tip distance (pinch feature)
- Index-middle finger angle (scissor feature)

### 2. Continuous Adaptation (auto-learning during use)

- After each successful recognition, landmarks are automatically recorded to the history samples
- Every 100 successful recognitions, thresholds are recomputed
- 70% old data + 30% new data (slow adaptation, avoids sudden jumps)
- Keeps the latest 200 samples (sliding window)
- Profile auto-saved to `%APPDATA%/AirCoding/calibration_profile.json`

### 3. User Profile Persistence

```json
{
  "version": 1,
  "created_at": "2026-07-28 00:30:00",
  "gestures": {
    "fist": { "features": {...}, "sample_count": 30, "calibrated_at": "..." },
    "open_palm": { ... },
    ...
  },
  "face": { "baseline_mean": 0.05, "baseline_std": 0.01, ... }
}
```

## How to Use

| Action | Method |
|--------|--------|
| Launch | double-click `start.bat` |
| Toggle panel | **Ctrl+Alt+K** (global hotkey) |
| Minimize to tray | click ✕ |
| Restore panel | double-click tray / Ctrl+Alt+K |
| Gesture calibration | click 🎯 |
| Tutorial | click 📖 |
| Settings | click ⚙️ |
| Quit | right-click tray → Quit |
