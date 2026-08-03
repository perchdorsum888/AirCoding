"""状态机单元测试。

验证7种灯效状态流转、模式切换、录音状态、回调触发。
"""

import sys
import os
import pytest

# 确保项目根目录在路径中
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from src.core.enums import LightState, SystemMode
from src.core.state_machine import StateMachine


class TestStateMachine:
    """状态机测试类。"""

    @pytest.fixture
    def sm(self):
        """创建状态机实例。"""
        return StateMachine(initial_mode=SystemMode.MANUAL_CONFIRM)

    def test_initial_state(self, sm):
        """测试初始状态。"""
        assert sm.get_light_state() == LightState.STANDBY
        assert sm.get_mode() == SystemMode.MANUAL_CONFIRM
        assert sm.is_recording() is False

    def test_valid_transition_standby_to_recognizing(self, sm):
        """测试合法转换：STANDBY → RECOGNIZING。"""
        assert sm.transition_to(LightState.RECOGNIZING) is True
        assert sm.get_light_state() == LightState.RECOGNIZING

    def test_valid_transition_recognizing_to_triggered(self, sm):
        """测试合法转换：RECOGNIZING → TRIGGERED。"""
        sm.transition_to(LightState.RECOGNIZING)
        assert sm.transition_to(LightState.TRIGGERED) is True
        assert sm.get_light_state() == LightState.TRIGGERED

    def test_valid_transition_triggered_to_standby(self, sm):
        """测试合法转换：TRIGGERED → STANDBY。"""
        sm.transition_to(LightState.RECOGNIZING)
        sm.transition_to(LightState.TRIGGERED)
        assert sm.transition_to(LightState.STANDBY) is True
        assert sm.get_light_state() == LightState.STANDBY

    def test_invalid_transition_rejected(self, sm):
        """测试非法转换被拒绝：STANDBY → TRIGGERED（不直接转换）。"""
        result = sm.transition_to(LightState.TRIGGERED)
        assert result is False
        assert sm.get_light_state() == LightState.STANDBY

    def test_same_state_no_transition(self, sm):
        """测试相同状态转换返回True但不触发回调。"""
        assert sm.transition_to(LightState.STANDBY) is True

    def test_start_recording(self, sm):
        """测试开始录音。"""
        sm.start_recording()
        assert sm.is_recording() is True
        assert sm.get_light_state() == LightState.RECORDING

    def test_stop_recording(self, sm):
        """测试停止录音。"""
        sm.start_recording()
        sm.stop_recording()
        assert sm.is_recording() is False
        # 停止后回到模式对应状态
        assert sm.get_light_state() == LightState.MANUAL_CONFIRM

    def test_stop_recording_not_recording(self, sm):
        """测试未录音时停止录音不报错。"""
        sm.stop_recording()
        assert sm.is_recording() is False

    def test_set_mode_auto_approve(self, sm):
        """测试设置自动批准模式。"""
        sm.set_mode(SystemMode.AUTO_APPROVE)
        assert sm.get_mode() == SystemMode.AUTO_APPROVE
        assert sm.get_light_state() == LightState.AUTO_APPROVE

    def test_set_mode_manual_confirm(self, sm):
        """测试设置手动确认模式。"""
        sm.set_mode(SystemMode.AUTO_APPROVE)
        sm.set_mode(SystemMode.MANUAL_CONFIRM)
        assert sm.get_mode() == SystemMode.MANUAL_CONFIRM
        assert sm.get_light_state() == LightState.MANUAL_CONFIRM

    def test_toggle_mode(self, sm):
        """测试模式切换toggle。"""
        assert sm.get_mode() == SystemMode.MANUAL_CONFIRM
        new_mode = sm.toggle_mode()
        assert new_mode == SystemMode.AUTO_APPROVE
        assert sm.get_mode() == SystemMode.AUTO_APPROVE

        new_mode = sm.toggle_mode()
        assert new_mode == SystemMode.MANUAL_CONFIRM
        assert sm.get_mode() == SystemMode.MANUAL_CONFIRM

    def test_register_callback(self, sm):
        """测试回调注册和触发。"""
        callback_called = []
        def callback(state):
            callback_called.append(state)

        sm.register_callback(LightState.RECOGNIZING, callback)
        sm.transition_to(LightState.RECOGNIZING)
        assert len(callback_called) == 1
        assert callback_called[0] == LightState.RECOGNIZING

    def test_unregister_callback(self, sm):
        """测试回调注销。"""
        callback_called = []
        def callback(state):
            callback_called.append(state)

        sm.register_callback(LightState.RECOGNIZING, callback)
        sm.unregister_callback(LightState.RECOGNIZING, callback)
        sm.transition_to(LightState.RECOGNIZING)
        assert len(callback_called) == 0

    def test_force_state(self, sm):
        """测试强制状态设置（跳过合法性检查）。"""
        sm.force_state(LightState.TRIGGERED)
        assert sm.get_light_state() == LightState.TRIGGERED

    def test_error_state_transition(self, sm):
        """测试错误状态转换。"""
        assert sm.transition_to(LightState.ERROR) is True
        assert sm.get_light_state() == LightState.ERROR

    def test_error_to_standby(self, sm):
        """测试错误状态恢复到待机。"""
        sm.transition_to(LightState.ERROR)
        assert sm.transition_to(LightState.STANDBY) is True

    def test_recording_to_triggered(self, sm):
        """测试录音中可以转到已触发。"""
        sm.start_recording()
        assert sm.transition_to(LightState.TRIGGERED) is True

    def test_auto_approve_to_recognizing(self, sm):
        """测试自动批准状态可以转到识别中。"""
        sm.set_mode(SystemMode.AUTO_APPROVE)
        assert sm.transition_to(LightState.RECOGNIZING) is True

    def test_recording_changes_light_state(self, sm):
        """测试录音开始/停止正确变更灯效状态。"""
        # 开始录音
        sm.start_recording()
        assert sm.get_light_state() == LightState.RECORDING

        # 停止录音后回到模式状态
        sm.stop_recording()
        assert sm.get_light_state() == LightState.MANUAL_CONFIRM

    def test_multiple_callbacks(self, sm):
        """测试同一状态注册多个回调。"""
        call_count = [0]
        def callback1(state):
            call_count[0] += 1
        def callback2(state):
            call_count[0] += 10

        sm.register_callback(LightState.RECOGNIZING, callback1)
        sm.register_callback(LightState.RECOGNIZING, callback2)
        sm.transition_to(LightState.RECOGNIZING)
        assert call_count[0] == 11  # 1 + 10
