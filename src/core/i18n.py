"""Internationalization (i18n) support for AirCoding.

Default language is English. Chinese (Simplified) is the built-in alternative.

Usage::

    from src.core.i18n import t, set_language, get_language

    set_language("zh")          # once at startup, read from config
    label.setText(t("Waiting for gesture..."))

Design notes:

- English source strings are used directly as keys, so the code stays
  readable and the default language has zero lookup overhead.
- When the current language is English, ``t()`` returns the input
  unchanged (no dictionary access).
- When the current language is Chinese, ``t()`` looks up the translation
  table and falls back to the English source if a string is missing,
  so untranslated strings degrade gracefully instead of showing blanks.
"""

import threading

# --- Current language code ("en" or "zh") -------------------------------
_language = "en"
_lock = threading.Lock()


def get_language() -> str:
    """Return the current language code ("en" or "zh")."""
    return _language


def set_language(code: str) -> None:
    """Set the current language. Any value other than "zh" -> English.

    Args:
        code: Language code, e.g. "en", "zh".
    """
    global _language
    with _lock:
        _language = "zh" if code == "zh" else "en"


def t(text: str) -> str:
    """Translate an English UI string to the current language.

    Args:
        text: English source string (also the dictionary key).

    Returns:
        Translated string in the current language, or the source
        string itself if the current language is English or no
        translation is registered.
    """
    if _language == "zh":
        return _TRANSLATIONS.get(text, text)
    return text


# --- Translation table (English source -> Chinese) ----------------------
# Keep this table sorted roughly by module for maintainability.

_TRANSLATIONS = {
    # ============ main_window.py / tray / toast ============
    "Show/Hide Panel": "显示/隐藏面板",
    "Settings...": "设置...",
    "Quit": "退出",
    "Waiting for gesture...": "等待手势...",
    "Confidence: {:.0f}%": "置信度: {:.0f}%",
    "Manual Confirm Mode": "手动确认模式",
    "Auto Approve Mode": "自动批准模式",
    "Voice input activated": "语音输入已激活",
    "Voice input stopped": "语音输入已停止",
    "Panel hidden. Double-click tray icon or press Ctrl+Alt+K to show": "面板已隐藏，双击托盘图标或按 Ctrl+Alt+K 重新显示",
    "Panel minimized to tray. Right-click tray icon to quit": "面板已最小化到托盘，右键托盘图标可退出",

    # ============ main.py startup toasts ============
    "Initializing recognition engine...": "正在初始化识别引擎...",
    "Ready": "就绪",
    "Camera unavailable": "摄像头不可用",
    "Initialization failed": "初始化失败",
    "Camera occupied by another app, waiting to recover...": "摄像头被其他程序占用，等待恢复...",
    "Camera recovered": "摄像头已恢复",
    "Initialization error: {}": "初始化异常: {}",

    # ============ settings_dialog.py ============
    "AirCoding - Settings": "AirCoding - 设置",
    "Hotkeys": "快捷键",
    "Recognition": "识别",
    "Validation": "防误触",
    "Interface": "界面",
    "AI Software": "AI软件",
    "Calibration": "校准",
    "Language:": "语言:",
    "Reset Defaults": "恢复默认",
    "Save": "保存",
    "Cancel": "取消",
    "(Internal logic)": "(内部逻辑)",
    "Gesture Hotkeys": "手势快捷键",
    "Voice Input (Dynamic Hotkey)": "语音输入（动态热键）",
    "Auto-detected from AI software": "由AI软件自动检测",
    "Mode Switch": "模式切换",
    "Internal logic (mode switch)": "内部逻辑（切换模式）",
    "Recognition Sensitivity": "识别灵敏度",
    "Prioritize single hand": "单手识别优先",
    "Finger Extended Threshold:": "手指伸直阈值:",
    "Finger Curled Threshold:": "手指弯曲阈值:",
    "Confirm Frames:": "连续确认帧数:",
    "Cooldown:": "冷却时间:",
    "Phone Call Hold:": "打电话保持时间:",
    "Pinch Hold:": "捏合保持时间:",
    "Panel Position:": "面板位置:",
    "Top Left": "左上角",
    "Top Right": "右上角",
    "Bottom Left": "左下角",
    "Bottom Right": "右下角",
    "Center": "居中",
    "Panel Opacity:": "面板透明度:",
    "Enable Light Effect": "启用灯效",
    "Enable Sound Feedback": "启用声音反馈",
    "Mirror Preview": "镜像预览（画面左右镜像）",
    "Follow AI Software Monitor": "跟随前台AI软件所在显示器",
    "Privacy Notice: camera frames are processed and displayed "
    "locally only. No image or video data is uploaded to the network.": "隐私声明：摄像头画面仅在本地处理和显示，不上传任何图像或视频数据到网络。",
    "IM Software": "IM软件",
    "Custom Software": "自定义软件",
    "+ Add Custom Software": "+ 添加自定义软件",
    "Not configured (disabled)": "未配置（禁用）",
    "Voice Input Hotkey:": "语音输入热键:",
    "Process Name:": "进程名:",
    "Not configured": "未配置",
    "Add Custom Software": "添加自定义软件",
    "Display Name:": "显示名称:",
    "e.g. My App": "如：我的应用",
    "Click the button to capture the foreground window process": "点击右侧按钮自动捕获前台窗口进程",
    "Capture Foreground": "捕获前台进程",
    "Capture failed: cannot get foreground window": "捕获失败：无法获取前台窗口",
    "Capture failed: cannot get process ID": "捕获失败：无法获取进程ID",
    "Capture failed: {}": "捕获失败: {}",
    "Not configured (click the button below to record)": "未配置（点击下方按钮录制）",
    "Record Hotkey": "录制热键",
    "Press combination... (click again to cancel)": "按下组合键...（再次点击取消）",
    "Press combination...": "请按下组合键...",
    "Re-record": "重新录制",
    "-- Select Preset --": "-- 选择预设 --",
    "Or select preset:": "或选择预设:",
    "Usage:\n1. Switch to the target app window, then click "
    "'Capture Foreground'\n2. Click 'Record Hotkey' and press the "
    "voice input shortcut in the target app\n3. Or pick a common "
    "shortcut from the preset list": "使用方式：\n1. 切换到目标软件窗口，点击「捕获前台进程」\n2. 点击「录制热键」后按下目标软件的语音输入快捷键\n3. 或从预设列表中选择常用热键",
    "Error": "错误",
    "Success": "成功",
    "Display name cannot be empty": "显示名称不能为空",
    "Software '{name}' already exists": "软件 '{name}' 已存在",
    "Added: {name}\nProcess: {processes}\nHotkey: {hotkey}": "已添加: {name}\n进程: {processes}\n热键: {hotkey}",
    "Calibration will guide you through each gesture, one by one, "
    "and generate a personalized threshold profile from the collected "
    "data.\n\nWe recommend calibrating in stable lighting conditions.": "校准功能将引导您逐一做出手势，采集数据后自动生成专属阈值配置。\n\n建议在光照条件稳定的环境下进行校准。",
    "Start Calibration": "开始校准",
    "Not calibrated": "未校准",
    "Confirm": "确认",
    "Reset all settings to defaults?": "确定要恢复所有设置到默认值吗？",
    "Calibration will be fully implemented in the next version": "校准功能将在下一版本完整实现",
    "Calibration started. Follow the guide and make the gestures.\n"
    "(The full calibration flow is triggered by the Onboarding module)": "校准功能已启动，请按照引导做出手势。\n（完整校准流程由Onboarding模块触发）",

    # ============ onboarding.py ============
    "OK Gesture": "OK手势",
    "OK Gesture = Press Enter": "OK手势 = 按 Enter 键",
    "Form a circle with thumb and index finger, keep other fingers straight": "拇指和食指成圈，其余三指伸直",
    "Open Palm": "张开手掌",
    "Open Palm = Press Escape": "张开手掌 = 按 Escape 键",
    "Open your palm and spread all five fingers": "请张开手掌，五指伸展",
    "Scissor": "剪刀手",
    "Scissor = Ctrl+Z Undo": "剪刀手 = Ctrl+Z 撤销",
    "Extend index and middle fingers, curl the rest": "请伸出食指和中指，其余弯曲",
    "Phone Call Gesture": "打电话手势",
    "Thumb to ear + pinky to mouth = activate voice input\n"
    "This is AirCoding's core gesture!": "拇指贴耳+小指贴嘴 = 激活语音输入\n这是AirCoding的核心手势！",
    "Make a phone call gesture: thumb to ear, pinky to mouth": "请做出打电话手势：拇指贴耳朵，小指贴嘴",
    "Pinch": "捏合",
    "Pinch = Toggle Mode": "捏合手势 = 切换模式",
    "Touch the tip of your thumb to the tip of your index finger": "请将拇指尖和食指尖捏在一起",
    "Skip Tutorial": "跳过引导",
    "Next →": "下一步 →",
    "Done ✓": "完成 ✓",
    "👋 Welcome to AirCoding": "👋 欢迎使用AirCoding",
    "\nAirCoding recognizes gestures and expressions through your "
    "camera,\nletting you control AI interactions hands-free.\n\n"
    "Next, we will learn the core gestures one by one.\n"
    "Each gesture requires 3 consecutive correct recognitions.": "\nAirCoding通过摄像头识别手势和表情，\n让你隔空控制AI交互。\n\n接下来将逐一学习核心手势。\n每个手势需要连续正确识别3次。",
    "Correct: {}/{}": "正确: {}/{}",
    "🎉 Congratulations!": "🎉 恭喜！",
    "\nYou have learned all the core gestures!\n\n"
    "🤙 Phone Call → Voice Input\n"
    "👌 OK → Enter\n"
    "✋ Open Palm → Escape\n"
    "✌️ Scissor → Ctrl+Z\n\n"
    "You can start using AirCoding now!": "\n你已学会所有核心手势！\n\n🤙 打电话 → 语音输入\n👌 OK手势 → Enter\n✋ 张开 → Escape\n✌️ 剪刀 → Ctrl+Z\n\n现在可以开始使用AirCoding了！",
    "✓ Gesture learned!": "✓ 该手势已学会！",
    "Correct! {}/{}": "正确！{}/{}",
    "✗ Try again": "✗ 请重试",

    # ============ privacy_preview.py ============
    "Starting camera...": "正在启动摄像头...",
    "Align your face here": "请将面部对准此处",

    # ============ calibration / gesture labels ============
    "Voice input": "语音输入",
    "Mode switch": "模式切换",
}
