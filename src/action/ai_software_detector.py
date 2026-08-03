"""AI软件检测模块。

通过 win32gui 获取前台窗口，psutil 获取进程名，
匹配预设AI软件注册表（WorkBuddy/豆包）。
支持"跟随前台窗口"模式和手动目标切换。

内置注册表：
    - WorkBuddy: 进程名 workbuddy/WorkBuddy, 热键 ctrl+d
    - 豆包: 进程名 Doubao/doubao, 热键 alt+d
"""

import time
from typing import Optional

from src.core.config_manager import ConfigManager
from src.utils.logger import get_logger

_logger = get_logger("AISoftwareDetector")

# 尝试导入系统交互库
try:
    import win32gui
    import win32process
    _HAS_WIN32 = True
except ImportError:
    _HAS_WIN32 = False
    _logger.warning("pywin32 not installed, AI software detection functionality limited")

try:
    import psutil
    _HAS_PSUTIL = True
except ImportError:
    _HAS_PSUTIL = False
    _logger.warning("psutil not installed, process name lookup limited")


class AISoftwareDetector:
    """AI软件检测器。

    检测前台窗口所属的AI软件，提供语音输入热键配置。

    Attributes:
        _software_registry: AI软件注册表。
        _current_target: 当前目标软件名称（None=跟随前台）。
        _follow_foreground: 是否跟随前台窗口。
    """

    def __init__(self, config_manager: ConfigManager) -> None:
        """初始化AI软件检测器。

        Args:
            config_manager: 配置管理器。
        """
        self._config_manager = config_manager
        self._software_registry = config_manager.get_ai_software_registry()
        self._current_target: Optional[str] = None
        self._follow_foreground = True

        _logger.info(
            "AI software detector initialized: %d registered software",
            len(self._software_registry),
        )

    def detect_foreground_ai(self) -> Optional[str]:
        """检测前台窗口所属的AI软件。

        如果设置了手动目标且不跟随前台，返回手动目标。
        否则扫描前台窗口进程名匹配注册表。

        Returns:
            AI软件名称（如 "workbuddy"），未检测到返回 None。
        """
        # 手动目标模式
        if not self._follow_foreground and self._current_target is not None:
            return self._current_target

        # 跟随前台模式
        process_name = self._scan_foreground_process()
        if process_name is None:
            return None

        return self._match_software(process_name)

    def get_hotkey(self, software_name: str) -> list:
        """获取指定AI软件的语音输入热键。

        Args:
            software_name: AI软件名称（注册表key）。

        Returns:
            热键按键序列列表（如 ["ctrl", "d"]），未找到返回空列表。
        """
        software = self._software_registry.get(software_name)
        if software is None:
            _logger.warning("Unknown AI software: %s", software_name)
            return []

        hotkey = software.get("voice_input_hotkey", [])
        _logger.debug("AI software %s hotkey: %s", software_name, hotkey)
        return list(hotkey)

    def set_target(self, software_name: Optional[str]) -> None:
        """设置手动目标AI软件。

        设为 None 则恢复跟随前台模式。

        Args:
            software_name: AI软件名称，或 None。
        """
        if software_name is not None and software_name not in self._software_registry:
            _logger.warning("Unknown AI software: %s", software_name)
            return

        self._current_target = software_name
        self._follow_foreground = software_name is None

        if software_name is not None:
            display_name = self._software_registry[software_name].get(
                "display_name", software_name
            )
            _logger.info("Manual target set: %s", display_name)
        else:
            _logger.info("Switched to follow-foreground-window mode")

    def get_available_software(self) -> list:
        """获取所有已注册的AI软件列表。

        Returns:
            软件信息字典列表，每项包含 name, display_name, process_names, hotkey。
        """
        result = []
        for name, info in self._software_registry.items():
            result.append({
                "name": name,
                "display_name": info.get("display_name", name),
                "process_names": info.get("process_names", []),
                "hotkey": info.get("voice_input_hotkey", []),
                "window_title_keywords": info.get("window_title_keywords", []),
            })
        return result

    def add_custom_software(
        self,
        name: str,
        process_names: list,
        hotkey: list,
        display_name: str = "",
        window_title_keywords: list = None,
    ) -> None:
        """添加自定义AI软件到注册表。

        Args:
            name: 软件标识名（英文小写）。
            process_names: 进程名匹配列表。
            hotkey: 语音输入热键序列。
            display_name: 显示名称。
            window_title_keywords: 窗口标题关键词列表。
        """
        self._software_registry[name] = {
            "display_name": display_name or name,
            "process_names": process_names,
            "voice_input_hotkey": hotkey,
            "window_title_keywords": window_title_keywords or [],
        }
        _logger.info("Custom AI software added: %s", name)

    def get_display_name(self, software_name: str) -> str:
        """获取AI软件的显示名称。

        Args:
            software_name: 软件标识名。

        Returns:
            显示名称，未找到返回 software_name 本身。
        """
        software = self._software_registry.get(software_name)
        if software is None:
            return software_name
        return software.get("display_name", software_name)

    def _scan_foreground_process(self) -> Optional[str]:
        """扫描前台窗口的进程名。

        Returns:
            进程名字符串，获取失败返回 None。
        """
        if not _HAS_WIN32 or not _HAS_PSUTIL:
            return self._scan_foreground_by_title()

        try:
            hwnd = win32gui.GetForegroundWindow()
            if hwnd == 0:
                return None

            # 获取窗口标题
            window_title = win32gui.GetWindowText(hwnd)

            # 获取进程ID
            _, pid = win32process.GetWindowThreadProcessId(hwnd)
            if pid == 0:
                return None

            # 获取进程名
            try:
                process = psutil.Process(pid)
                process_name = process.name()
                _logger.debug(
                    "Foreground window: title=%s, pid=%d, process=%s",
                    window_title[:30],
                    pid,
                    process_name,
                )
                return process_name
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                return None

        except Exception as e:
            _logger.error("Failed to scan foreground process: %s", e)
            return None

    def _scan_foreground_by_title(self) -> Optional[str]:
        """通过窗口标题关键词匹配AI软件（降级方案）。

        Returns:
            匹配到的进程名，未匹配返回 None。
        """
        if not _HAS_WIN32:
            return None

        try:
            hwnd = win32gui.GetForegroundWindow()
            if hwnd == 0:
                return None
            window_title = win32gui.GetWindowText(hwnd)

            for name, info in self._software_registry.items():
                keywords = info.get("window_title_keywords", [])
                for keyword in keywords:
                    if keyword.lower() in window_title.lower():
                        return info.get("process_names", [name])[0]

            return None
        except Exception:
            return None

    def _match_software(self, process_name: str) -> Optional[str]:
        """将进程名匹配到注册表中的AI软件。

        Args:
            process_name: 进程名（如 "WorkBuddy.exe"）。

        Returns:
            匹配的软件标识名，未匹配返回 None。
        """
        process_lower = process_name.lower()

        for name, info in self._software_registry.items():
            for pn in info.get("process_names", []):
                if pn.lower() in process_lower:
                    display_name = info.get("display_name", name)
                    _logger.info("AI software detected: %s (process: %s)", display_name, process_name)
                    return name

        return None

    def is_following_foreground(self) -> bool:
        """返回是否处于跟随前台模式。"""
        return self._follow_foreground

    def get_current_target(self) -> Optional[str]:
        """返回当前目标软件名称。"""
        return self._current_target
