"""防误触验证模块。

实现三级防误触机制：
1. 帧一致性确认：连续N帧（默认3帧）检测到相同手势
2. 保持时间确认：特定手势需保持指定时长（打电话0.5s，捏合1.5s，挑眉0.5s）
3. 冷却时间：触发后500ms内不响应同种手势
4. 置信度门控：置信度低于阈值（0.7）的手势不确认

使用 collections.deque(maxlen=3) 维护帧历史，
保持时间用 time.monotonic() 计时。
"""

import time
from collections import deque
from typing import Optional

from src.core.enums import GestureType
from src.utils.logger import get_logger

_logger = get_logger("GestureValidator")

# 默认配置
DEFAULT_CONFIRM_FRAMES = 3
DEFAULT_COOLDOWN_MS = 500
DEFAULT_CONFIDENCE_THRESHOLD = 0.85  # 提高阈值避免误触发（原0.7太低）
DEFAULT_HOLD_DURATIONS = {
    GestureType.PHONE_CALL: 500,
    GestureType.PINCH: 1500,
}


class GestureValidator:
    """防误触验证器。

    防误触三级机制：
        1. 帧一致性：连续 _confirm_frames 帧检测到相同手势
        2. 保持时间：需要保持的手势（如打电话/捏合/挑眉）需持续指定时长
        3. 冷却时间：触发后 _cooldown_ms 内不响应
        4. 置信度门控：置信度 < _confidence_threshold 的手势被拒绝

    Attributes:
        _confirm_frames: 确认帧数。
        _hold_durations: 各手势保持时间（毫秒）。
        _cooldown_ms: 冷却时间（毫秒）。
        _confidence_threshold: 置信度阈值。
        _frame_history: 帧历史滑动窗口。
        _hold_start_time: 各手势保持开始时间。
        _last_trigger_time: 上次触发时间。
        _last_confirmed_gesture: 上次确认的手势。
    """

    def __init__(
        self,
        confirm_frames: int = DEFAULT_CONFIRM_FRAMES,
        hold_durations: Optional[dict] = None,
        cooldown_ms: int = DEFAULT_COOLDOWN_MS,
        confidence_threshold: float = DEFAULT_CONFIDENCE_THRESHOLD,
    ) -> None:
        """初始化防误触验证器。

        Args:
            confirm_frames: 确认帧数（默认3）。
            hold_durations: 各手势保持时间字典，key为GestureType，value为毫秒。
            cooldown_ms: 冷却时间（毫秒）。
            confidence_threshold: 置信度阈值。
        """
        self._confirm_frames = confirm_frames
        self._hold_durations = hold_durations or dict(DEFAULT_HOLD_DURATIONS)
        self._cooldown_ms = cooldown_ms
        self._confidence_threshold = confidence_threshold

        self._frame_history: deque = deque(maxlen=confirm_frames)
        self._hold_start_time: dict = {}  # gesture → monotonic time
        self._last_trigger_time: float = 0.0
        self._last_confirmed_gesture: GestureType = GestureType.NONE

    def validate(self, gesture: GestureType, confidence: float) -> bool:
        """验证手势是否通过防误触检查。

        Args:
            gesture: 当前帧检测到的手势。
            confidence: 当前手势置信度。

        Returns:
            True 如果手势通过所有防误触检查。
        """
        # NONE 手势重置帧历史（无论置信度如何）
        if gesture == GestureType.NONE:
            self._frame_history.clear()
            self._hold_start_time.clear()
            return False

        # 置信度门控
        if not self._check_confidence(confidence):
            return False

        # 帧一致性检查
        if not self._check_frame_consistency(gesture):
            return False

        # 冷却时间检查
        if not self._check_cooldown():
            return False

        # 保持时间检查
        if not self._check_hold_duration(gesture):
            return False

        # 全部通过，记录触发
        self._last_trigger_time = time.monotonic()
        self._last_confirmed_gesture = gesture
        self._hold_start_time.pop(gesture, None)
        self._frame_history.clear()  # 清空帧历史，下次触发需重新积累

        _logger.info(
            "Gesture confirmed: %s, confidence=%.2f",
            gesture.value,
            confidence,
        )
        return True

    def _check_confidence(self, confidence: float) -> bool:
        """检查置信度是否达标。

        Args:
            confidence: 置信度。

        Returns:
            True 如果置信度达标。
        """
        return confidence >= self._confidence_threshold

    def _check_frame_consistency(self, gesture: GestureType) -> bool:
        """检查帧一致性。

        将当前手势加入帧历史，检查是否连续 _confirm_frames 帧一致。
        如果中途出现不同手势，重置历史。

        Args:
            gesture: 当前手势。

        Returns:
            True 如果连续帧一致。
        """
        self._frame_history.append(gesture)

        # 检查帧历史是否已满且全部一致
        if len(self._frame_history) < self._confirm_frames:
            return False

        # 检查最近 _confirm_frames 帧是否全部相同
        first = self._frame_history[0]
        for g in self._frame_history:
            if g != first:
                return False

        return True

    def _check_hold_duration(self, gesture: GestureType) -> bool:
        """检查保持时间。

        对于需要保持的手势，记录开始时间并检查是否已保持足够时长。
        不需要保持的手势直接通过。

        Args:
            gesture: 当前手势。

        Returns:
            True 如果保持时间达标或不需要保持。
        """
        hold_ms = self._hold_durations.get(gesture, 0)

        if hold_ms <= 0:
            # 不需要保持，直接通过
            return True

        now = time.monotonic()

        if gesture not in self._hold_start_time:
            # 首次检测到，记录开始时间
            self._hold_start_time[gesture] = now
            _logger.debug(
                "Gesture hold timing started: %s, must hold %dms",
                gesture.value,
                hold_ms,
            )
            return False

        # 检查是否已保持足够时长
        elapsed_ms = (now - self._hold_start_time[gesture]) * 1000
        if elapsed_ms >= hold_ms:
            _logger.debug(
                "Gesture hold completed: %s, held for %.0fms",
                gesture.value,
                elapsed_ms,
            )
            return True

        return False

    def _check_cooldown(self) -> bool:
        """检查冷却时间。

        Returns:
            True 如果冷却时间已过。
        """
        if self._last_trigger_time == 0.0:
            return True

        elapsed_ms = (time.monotonic() - self._last_trigger_time) * 1000
        return elapsed_ms >= self._cooldown_ms

    def reset(self) -> None:
        """重置验证器状态（帧历史、保持计时、冷却）。"""
        self._frame_history.clear()
        self._hold_start_time.clear()
        self._last_trigger_time = 0.0
        self._last_confirmed_gesture = GestureType.NONE
        _logger.debug("Validator state reset")

    def update_config(self, config: dict) -> None:
        """更新防误触配置。

        Args:
            config: 配置字典，可包含 confirm_frames, hold_durations,
                    cooldown_ms, confidence_threshold。
        """
        if "confirm_frames" in config:
            self._confirm_frames = int(config["confirm_frames"])
            self._frame_history = deque(maxlen=self._confirm_frames)

        if "hold_durations" in config:
            new_durations = config["hold_durations"]
            # 将字符串key转为GestureType
            for key, value in new_durations.items():
                try:
                    gesture = GestureType(key) if isinstance(key, str) else key
                    self._hold_durations[gesture] = int(value)
                except (ValueError, TypeError):
                    pass

        if "cooldown_ms" in config:
            self._cooldown_ms = int(config["cooldown_ms"])

        if "confidence_threshold" in config:
            self._confidence_threshold = float(config["confidence_threshold"])

        _logger.info("Anti-misfire config updated")

    @property
    def last_confirmed_gesture(self) -> GestureType:
        """返回上次确认的手势。"""
        return self._last_confirmed_gesture

    @property
    def is_in_cooldown(self) -> bool:
        """返回是否处于冷却中。"""
        if self._last_trigger_time == 0.0:
            return False
        return not self._check_cooldown()
