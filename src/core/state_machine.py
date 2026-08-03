"""状态机模块。

管理7种灯效状态（LightState）和2种系统模式（SystemMode）的状态流转。
提供线程安全的状态访问和状态变更回调注册。
通过 Qt Signal 通知 UI 层状态变更。
"""

import threading
import time
from typing import Callable, Optional

from src.core.enums import LightState, SystemMode
from src.utils.logger import get_logger

_logger = get_logger("StateMachine")

# 尝试导入 PySide6 Signal（可选，用于UI通知）
try:
    from PySide6.QtCore import QObject, Signal

    _HAS_QT = True
except ImportError:
    _HAS_QT = False
    _logger.warning("PySide6 unavailable, StateMachine will run in pure-Python mode")

    class _SignalStub:
        """Signal 桩，用于无 Qt 环境下的兼容。"""
        def __init__(self, *args, **kwargs) -> None:
            self._handlers = []

        def connect(self, handler: Callable) -> None:
            self._handlers.append(handler)

        def emit(self, *args, **kwargs) -> None:
            for handler in self._handlers:
                try:
                    handler(*args, **kwargs)
                except Exception:
                    pass

    class QObject:  # type: ignore[no-redef]
        """QObject 桩。"""
        pass

    def Signal(*args, **kwargs):  # type: ignore[no-redef]
        return _SignalStub()


# 合法状态转换规则：key → 允许转换到的状态集合
_VALID_TRANSITIONS: dict = {
    LightState.STANDBY: {
        LightState.RECOGNIZING,
        LightState.RECORDING,
        LightState.ERROR,
        LightState.AUTO_APPROVE,
        LightState.MANUAL_CONFIRM,
    },
    LightState.RECOGNIZING: {
        LightState.STANDBY,
        LightState.TRIGGERED,
        LightState.RECORDING,
        LightState.ERROR,
    },
    LightState.RECORDING: {
        LightState.STANDBY,
        LightState.TRIGGERED,
        LightState.ERROR,
        LightState.AUTO_APPROVE,
        LightState.MANUAL_CONFIRM,
    },
    LightState.TRIGGERED: {
        LightState.STANDBY,
        LightState.RECOGNIZING,
        LightState.AUTO_APPROVE,
        LightState.MANUAL_CONFIRM,
        LightState.ERROR,
    },
    LightState.ERROR: {
        LightState.STANDBY,
        LightState.AUTO_APPROVE,
        LightState.MANUAL_CONFIRM,
    },
    LightState.AUTO_APPROVE: {
        LightState.STANDBY,
        LightState.RECOGNIZING,
        LightState.ERROR,
        LightState.MANUAL_CONFIRM,
    },
    LightState.MANUAL_CONFIRM: {
        LightState.STANDBY,
        LightState.RECOGNIZING,
        LightState.ERROR,
        LightState.AUTO_APPROVE,
    },
}


class StateMachine(QObject if _HAS_QT else object):
    """中央状态管理器。

    管理 LightState（7种）和 SystemMode（2种）的状态流转。
    所有状态变更经过统一调度，确保灯效/模式/录音状态的一致性。

    Signals:
        state_changed: 灯效状态变更信号。
        mode_changed: 系统模式变更信号。
        recording_state_changed: 录音状态变更信号。
    """

    # Qt Signals（UI线程订阅）
    state_changed = Signal(LightState)
    mode_changed = Signal(SystemMode)
    recording_state_changed = Signal(bool)

    def __init__(self, initial_mode: SystemMode = SystemMode.MANUAL_CONFIRM) -> None:
        """初始化状态机。

        Args:
            initial_mode: 初始系统模式（默认手动确认）。
        """
        if _HAS_QT:
            super().__init__()

        self._lock = threading.Lock()
        self._light_state: LightState = LightState.STANDBY
        self._mode: SystemMode = initial_mode
        self._is_recording: bool = False
        self._callbacks: dict = {}  # state → list of callbacks
        self._recording_start_time: float = 0.0

        _logger.info(
            "State machine initialized: light=%s, mode=%s",
            self._light_state.value,
            self._mode.value,
        )

    def transition_to(self, state: LightState) -> bool:
        """尝试转换到指定的灯效状态。

        仅允许合法的状态转换，非法转换将被拒绝并记录日志。

        Args:
            state: 目标灯效状态。

        Returns:
            True 如果转换成功，False 如果转换被拒绝。
        """
        with self._lock:
            if state == self._light_state:
                return True

            allowed = _VALID_TRANSITIONS.get(self._light_state, set())
            if state not in allowed:
                _logger.warning(
                    "Illegal state transition: %s → %s (rejected)",
                    self._light_state.value,
                    state.value,
                )
                return False

            old_state = self._light_state
            self._light_state = state
            _logger.info("State transition: %s → %s", old_state.value, state.value)

            callbacks = self._callbacks.get(state, []).copy()

        # 锁外触发回调和信号
        for callback in callbacks:
            try:
                callback(state)
            except Exception as e:
                _logger.error("State callback execution failed: %s", e)

        self.state_changed.emit(state)
        return True

    def set_mode(self, mode: SystemMode) -> None:
        """设置系统模式，并切换对应的待机灯效状态。

        Args:
            mode: 目标系统模式。
        """
        with self._lock:
            if mode == self._mode:
                return
            old_mode = self._mode
            self._mode = mode
            _logger.info("Mode switch: %s → %s", old_mode.value, mode.value)

        # 锁外触发信号
        self.mode_changed.emit(mode)

        # 切换对应的待机灯效
        if mode == SystemMode.AUTO_APPROVE:
            self.transition_to(LightState.AUTO_APPROVE)
        else:
            self.transition_to(LightState.MANUAL_CONFIRM)

    def toggle_mode(self) -> SystemMode:
        """切换系统模式（自动批准 ↔ 手动确认）。

        Returns:
            切换后的新模式。
        """
        if self._mode == SystemMode.AUTO_APPROVE:
            new_mode = SystemMode.MANUAL_CONFIRM
        else:
            new_mode = SystemMode.AUTO_APPROVE
        self.set_mode(new_mode)
        return new_mode

    def start_recording(self) -> None:
        """开始录音状态。

        切换灯效到 RECORDING，标记录音状态为 True。
        """
        with self._lock:
            if self._is_recording:
                return
            self._is_recording = True
            self._recording_start_time = time.monotonic()
            _logger.info("Recording started")

        self.recording_state_changed.emit(True)
        self.transition_to(LightState.RECORDING)

    def stop_recording(self) -> None:
        """停止录音状态。

        切换灯效回待机状态，标记录音状态为 False。
        """
        with self._lock:
            if not self._is_recording:
                return
            self._is_recording = False
            duration = time.monotonic() - self._recording_start_time
            _logger.info("Recording stopped, lasted %.1f seconds", duration)

        self.recording_state_changed.emit(False)

        # 回到当前模式对应的待机状态
        if self._mode == SystemMode.AUTO_APPROVE:
            self.transition_to(LightState.AUTO_APPROVE)
        else:
            self.transition_to(LightState.MANUAL_CONFIRM)

    def register_callback(self, state: LightState, callback: Callable) -> None:
        """注册状态变更回调。

        当状态转换到指定状态时，回调将被调用。

        Args:
            state: 目标灯效状态。
            callback: 回调函数，签名为 callback(state: LightState)。
        """
        with self._lock:
            if state not in self._callbacks:
                self._callbacks[state] = []
            self._callbacks[state].append(callback)
        _logger.debug("State callback registered: %s", state.value)

    def unregister_callback(self, state: LightState, callback: Callable) -> None:
        """注销状态变更回调。

        Args:
            state: 目标灯效状态。
            callback: 要注销的回调函数。
        """
        with self._lock:
            if state in self._callbacks and callback in self._callbacks[state]:
                self._callbacks[state].remove(callback)

    def get_light_state(self) -> LightState:
        """获取当前灯效状态（线程安全）。"""
        with self._lock:
            return self._light_state

    def get_mode(self) -> SystemMode:
        """获取当前系统模式（线程安全）。"""
        with self._lock:
            return self._mode

    def is_recording(self) -> bool:
        """获取当前录音状态（线程安全）。"""
        with self._lock:
            return self._is_recording

    def force_state(self, state: LightState) -> None:
        """强制设置灯效状态（跳过转换合法性检查）。

        仅用于错误恢复等特殊场景。

        Args:
            state: 目标灯效状态。
        """
        with self._lock:
            old_state = self._light_state
            self._light_state = state
            _logger.warning("Forced state set: %s → %s", old_state.value, state.value)
            callbacks = self._callbacks.get(state, []).copy()

        for callback in callbacks:
            try:
                callback(state)
            except Exception as e:
                _logger.error("State callback execution failed: %s", e)

        self.state_changed.emit(state)
