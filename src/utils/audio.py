"""声音反馈模块。

使用 winsound.Beep 封装预定义音效。
支持模式切换音效、错误蜂鸣、触发提示音。
可通过配置开关启用/禁用。
"""

import sys
import threading
from typing import Optional

from src.utils.logger import get_logger

_logger = get_logger("AudioFeedback")

# 预定义音效频率（Hz）和持续时间（ms）
_SOUND_EFFECTS = {
    "mode_up": [(523, 80), (659, 80), (784, 120)],       # 模式切换上升：C5→E5→G5
    "mode_down": [(784, 80), (659, 80), (523, 120)],     # 模式切换下降：G5→E5→C5
    "trigger": [(880, 60)],                                # 触发提示：A5短促
    "error": [(220, 200), (180, 200)],                     # 错误蜂鸣：低频双音
    "recording_start": [(440, 60), (554, 60), (659, 100)], # 录音开始
    "recording_stop": [(659, 60), (554, 60), (440, 100)],  # 录音停止
}


class AudioFeedback:
    """声音反馈控制器。

    使用 winsound.Beep 播放预定义音效。
    声音播放在独立线程中执行，避免阻塞主流程。

    Attributes:
        _enabled: 是否启用声音反馈。
    """

    def __init__(self, enabled: bool = True) -> None:
        """初始化声音反馈控制器。

        Args:
            enabled: 是否启用声音反馈。
        """
        self._enabled = enabled
        self._platform_supported = sys.platform == "win32"

    def play_sound(self, sound_name: str) -> None:
        """播放预定义音效。

        Args:
            sound_name: 音效名称，可选值见 _SOUND_EFFECTS。
        """
        if not self._enabled:
            return
        if not self._platform_supported:
            _logger.debug("Sound feedback unavailable: non-Windows platform")
            return

        effect = _SOUND_EFFECTS.get(sound_name)
        if effect is None:
            _logger.warning("Unknown sound effect name: %s", sound_name)
            return

        # 在独立线程播放，避免阻塞
        thread = threading.Thread(
            target=self._play_beep_sequence,
            args=(effect,),
            daemon=True,
        )
        thread.start()

    def _play_beep_sequence(self, sequence: list) -> None:
        """按顺序播放蜂鸣序列。

        Args:
            sequence: (频率Hz, 持续时间ms) 元组列表。
        """
        try:
            import winsound
            for freq, duration in sequence:
                winsound.Beep(freq, duration)
        except Exception as e:
            _logger.error("Failed to play sound effect: %s", e)

    def set_enabled(self, enabled: bool) -> None:
        """设置声音反馈开关。

        Args:
            enabled: True启用，False禁用。
        """
        self._enabled = enabled
        _logger.info("Sound feedback %s", "enabled" if enabled else "disabled")

    def is_enabled(self) -> bool:
        """返回声音反馈是否启用。"""
        return self._enabled

    def play_mode_up(self) -> None:
        """播放模式切换上升音效。"""
        self.play_sound("mode_up")

    def play_mode_down(self) -> None:
        """播放模式切换下降音效。"""
        self.play_sound("mode_down")

    def play_trigger(self) -> None:
        """播放触发提示音。"""
        self.play_sound("trigger")

    def play_error(self) -> None:
        """播放错误蜂鸣。"""
        self.play_sound("error")

    def play_recording_start(self) -> None:
        """播放录音开始音效。"""
        self.play_sound("recording_start")

    def play_recording_stop(self) -> None:
        """播放录音停止音效。"""
        self.play_sound("recording_stop")
