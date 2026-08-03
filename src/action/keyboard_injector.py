"""键盘事件注入模块。

pynput 优先（兼容性最好），SendInput 备选。
组合键注入：依次按下所有键 → 等待10ms → 逆序释放所有键。
"""

import time
import ctypes
from typing import Optional

from src.utils.logger import get_logger

_logger = get_logger("KeyboardInjector")

try:
    from pynput.keyboard import Controller as PynputController, Key, KeyCode
    _HAS_PYNPUT = True
except ImportError:
    _HAS_PYNPUT = False

# pynput 特殊键映射
SPECIAL_KEY_MAP = {
    "enter": Key.enter, "escape": Key.esc, "esc": Key.esc,
    "tab": Key.tab, "space": Key.space,
    "backspace": Key.backspace, "delete": Key.delete,
    "up": Key.up, "down": Key.down,
    "left": Key.left, "right": Key.right,
    "home": Key.home, "end": Key.end,
    "page_up": Key.page_up, "page_down": Key.page_down,
} if _HAS_PYNPUT else {}

MODIFIER_KEY_MAP = {
    "ctrl": Key.ctrl, "control": Key.ctrl,
    "alt": Key.alt, "shift": Key.shift,
    "cmd": Key.cmd, "win": Key.cmd,
} if _HAS_PYNPUT else {}

# SendInput 虚拟键码（备选）
_VK_MAP = {
    "ctrl": 0x11, "control": 0x11, "alt": 0x12, "shift": 0x10,
    "cmd": 0x5B, "win": 0x5B,
    "enter": 0x0D, "return": 0x0D, "escape": 0x1B, "esc": 0x1B,
    "tab": 0x09, "space": 0x20, "backspace": 0x08, "delete": 0x2E,
    "up": 0x26, "down": 0x28, "left": 0x25, "right": 0x27,
    "home": 0x24, "end": 0x23, "page_up": 0x21, "page_down": 0x22,
    "f1": 0x70, "f2": 0x71, "f3": 0x72, "f4": 0x73,
    "f5": 0x74, "f6": 0x75, "f7": 0x76, "f8": 0x77,
    "f9": 0x78, "f10": 0x79, "f11": 0x7A, "f12": 0x7B,
}

INPUT_KEYBOARD = 0x0001
KEYEVENTF_KEYUP = 0x0002


class KeyboardInjector:
    """键盘事件注入器。pynput优先，SendInput备选。"""

    def __init__(self) -> None:
        self._controller = PynputController() if _HAS_PYNPUT else None
        self._use_pynput = _HAS_PYNPUT
        _logger.info("Keyboard injector initialized: %s", "pynput" if self._use_pynput else "SendInput")

    def inject_key(self, key: str) -> bool:
        """注入单个按键。"""
        try:
            if self._use_pynput:
                key_obj = self._resolve_key(key)
                self._controller.press(key_obj)
                time.sleep(0.02)
                self._controller.release(key_obj)
            else:
                vk = self._get_vk_code(key)
                if vk == 0:
                    _logger.error("Unknown key: %s", key)
                    return False
                self._sendinput_key(vk, down=True)
                time.sleep(0.02)
                self._sendinput_key(vk, down=False)
            _logger.info("Key injected: %s", key)
            return True
        except Exception as e:
            _logger.error("Key injection failed: %s, error: %s", key, e)
            return False

    def inject_hotkey(self, *keys: str) -> bool:
        """注入组合键：依次按下 → 等待 → 逆序释放。"""
        if not keys:
            return False
        try:
            if self._use_pynput:
                for key in keys:
                    self._controller.press(self._resolve_key(key))
                time.sleep(0.02)
                for key in reversed(keys):
                    self._controller.release(self._resolve_key(key))
            else:
                for key in keys:
                    vk = self._get_vk_code(key)
                    if vk == 0:
                        return False
                    self._sendinput_key(vk, down=True)
                    time.sleep(0.01)
                time.sleep(0.02)
                for key in reversed(keys):
                    vk = self._get_vk_code(key)
                    self._sendinput_key(vk, down=False)
                    time.sleep(0.01)
            _logger.info("Hotkey injected: %s", "+".join(keys))
            return True
        except Exception as e:
            _logger.error("Hotkey injection failed: %s, error: %s", "+".join(keys), e)
            return False

    def inject_text(self, text: str) -> bool:
        if not text:
            return False
        try:
            if self._use_pynput:
                self._controller.type(text)
            else:
                for char in text:
                    vk = ord(char.upper())
                    self._sendinput_key(vk, down=True)
                    time.sleep(0.005)
                    self._sendinput_key(vk, down=False)
                    time.sleep(0.005)
            return True
        except Exception as e:
            _logger.error("Text injection failed: %s", e)
            return False

    def _resolve_key(self, key: str):
        """将按键名称解析为 pynput Key/KeyCode 对象。"""
        key_lower = key.lower()
        if key_lower in MODIFIER_KEY_MAP:
            return MODIFIER_KEY_MAP[key_lower]
        if key_lower in SPECIAL_KEY_MAP:
            return SPECIAL_KEY_MAP[key_lower]
        if len(key) == 1:
            return KeyCode.from_char(key)
        if key_lower.startswith("f") and key_lower[1:].isdigit():
            return getattr(Key, f"f{key_lower[1:]}", KeyCode.from_char(key))
        return KeyCode.from_char(key)

    def _get_vk_code(self, key: str) -> int:
        key_lower = key.lower()
        if key_lower in _VK_MAP:
            return _VK_MAP[key_lower]
        if len(key) == 1:
            return ord(key.upper())
        return 0

    @staticmethod
    def _sendinput_key(vk: int, down: bool) -> None:
        """SendInput 备选方案。"""
        class MOUSEINPUT(ctypes.Structure):
            _fields_ = [("dx", ctypes.c_long), ("dy", ctypes.c_long),
                ("mouseData", ctypes.c_ulong), ("dwFlags", ctypes.c_ulong),
                ("time", ctypes.c_ulong), ("dwExtraInfo", ctypes.c_void_p)]
        class KEYBDINPUT(ctypes.Structure):
            _fields_ = [("wVk", ctypes.c_ushort), ("wScan", ctypes.c_ushort),
                ("dwFlags", ctypes.c_ulong), ("time", ctypes.c_ulong),
                ("dwExtraInfo", ctypes.c_void_p)]
        class HARDWAREINPUT(ctypes.Structure):
            _fields_ = [("uMsg", ctypes.c_ulong), ("wParamL", ctypes.c_ushort), ("wParamH", ctypes.c_ushort)]
        class INPUT(ctypes.Structure):
            class _INPUT(ctypes.Union):
                _fields_ = [("ki", KEYBDINPUT), ("mi", MOUSEINPUT), ("hi", HARDWAREINPUT)]
            _anonymous_ = ("_input",)
            _fields_ = [("type", ctypes.c_ulong), ("_input", _INPUT)]

        inp = INPUT()
        inp.type = INPUT_KEYBOARD
        inp.ki.wVk = vk
        inp.ki.dwFlags = 0 if down else KEYEVENTF_KEYUP
        inp.ki.time = 0
        inp.ki.dwExtraInfo = None
        ctypes.windll.user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(inp))
