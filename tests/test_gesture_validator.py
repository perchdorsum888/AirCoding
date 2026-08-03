"""防误触验证器单元测试。

模拟连续帧序列，验证3帧确认逻辑、保持时间计时、冷却时间阻断、置信度门控。
"""

import sys
import os
import time
import pytest

# 确保项目根目录在路径中
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from src.core.enums import GestureType
from src.recognition.gesture_validator import GestureValidator


class TestGestureValidator:
    """防误触验证器测试类。"""

    @pytest.fixture
    def validator(self):
        """创建验证器实例（3帧确认，500ms冷却，0.7置信度）。"""
        return GestureValidator(
            confirm_frames=3,
            hold_durations={},
            cooldown_ms=500,
            confidence_threshold=0.7,
        )

    def test_single_frame_not_confirmed(self, validator):
        """测试单帧不确认（需3帧一致）。"""
        result = validator.validate(GestureType.FIST, 0.9)
        assert result is False

    def test_two_frames_not_confirmed(self, validator):
        """测试两帧不确认。"""
        validator.validate(GestureType.FIST, 0.9)
        result = validator.validate(GestureType.FIST, 0.9)
        assert result is False

    def test_three_frames_confirmed(self, validator):
        """测试三帧一致确认通过。"""
        validator.validate(GestureType.FIST, 0.9)
        validator.validate(GestureType.FIST, 0.9)
        result = validator.validate(GestureType.FIST, 0.9)
        assert result is True

    def test_inconsistent_frames_not_confirmed(self, validator):
        """测试不一致帧序列不确认。"""
        validator.validate(GestureType.FIST, 0.9)
        validator.validate(GestureType.OPEN_PALM, 0.9)  # 中途变化
        result = validator.validate(GestureType.FIST, 0.9)
        assert result is False

    def test_low_confidence_not_confirmed(self, validator):
        """测试低置信度被门控拒绝。"""
        validator.validate(GestureType.FIST, 0.5)  # 低于0.7
        validator.validate(GestureType.FIST, 0.5)
        result = validator.validate(GestureType.FIST, 0.5)
        assert result is False

    def test_none_gesture_resets_history(self, validator):
        """测试NONE手势重置帧历史。"""
        validator.validate(GestureType.FIST, 0.9)
        validator.validate(GestureType.FIST, 0.9)
        validator.validate(GestureType.NONE, 0.0)  # 重置
        result = validator.validate(GestureType.FIST, 0.9)
        assert result is False  # 需要重新积累3帧

    def test_cooldown_blocks_immediate_retrigger(self, validator):
        """测试冷却时间阻断立即重复触发。"""
        # 完成3帧确认
        validator.validate(GestureType.FIST, 0.9)
        validator.validate(GestureType.FIST, 0.9)
        validator.validate(GestureType.FIST, 0.9)

        # 立即再次尝试（冷却中）
        validator.validate(GestureType.FIST, 0.9)
        validator.validate(GestureType.FIST, 0.9)
        result = validator.validate(GestureType.FIST, 0.9)
        assert result is False  # 被冷却阻断

    def test_cooldown_expires(self, validator):
        """测试冷却时间过期后可再次触发。

        使用极短冷却时间避免实际等待。
        """
        short_validator = GestureValidator(
            confirm_frames=2,
            hold_durations={},
            cooldown_ms=50,  # 50ms冷却
            confidence_threshold=0.7,
        )
        # 第一次触发
        short_validator.validate(GestureType.FIST, 0.9)
        short_validator.validate(GestureType.FIST, 0.9)

        # 等待冷却过期
        time.sleep(0.1)

        # 第二次触发
        short_validator.validate(GestureType.FIST, 0.9)
        result = short_validator.validate(GestureType.FIST, 0.9)
        assert result is True

    def test_hold_duration_not_met(self):
        """测试保持时间未达标。"""
        validator = GestureValidator(
            confirm_frames=1,
            hold_durations={GestureType.PINCH: 300},  # 300ms保持
            cooldown_ms=100,
            confidence_threshold=0.7,
        )
        # 第1帧：开始保持计时
        result = validator.validate(GestureType.PINCH, 0.9)
        assert result is False  # 保持时间未达标

    def test_hold_duration_met(self):
        """测试保持时间达标后确认。"""
        validator = GestureValidator(
            confirm_frames=1,
            hold_durations={GestureType.PINCH: 50},  # 50ms保持
            cooldown_ms=100,
            confidence_threshold=0.7,
        )
        # 第1帧：开始保持计时
        validator.validate(GestureType.PINCH, 0.9)
        # 等待保持时间
        time.sleep(0.08)
        # 第2帧：保持时间已达标
        result = validator.validate(GestureType.PINCH, 0.9)
        assert result is True

    def test_reset(self, validator):
        """测试重置验证器状态。"""
        validator.validate(GestureType.FIST, 0.9)
        validator.validate(GestureType.FIST, 0.9)
        validator.reset()
        # 重置后需要重新积累3帧
        validator.validate(GestureType.FIST, 0.9)
        validator.validate(GestureType.FIST, 0.9)
        result = validator.validate(GestureType.FIST, 0.9)
        assert result is True

    def test_update_config(self, validator):
        """测试配置更新。"""
        validator.update_config({
            "confirm_frames": 2,
            "cooldown_ms": 1000,
            "confidence_threshold": 0.8,
        })
        assert validator._confirm_frames == 2
        assert validator._cooldown_ms == 1000
        assert validator._confidence_threshold == 0.8

    def test_different_gestures_in_sequence(self, validator):
        """测试不同手势序列不互相确认。"""
        validator.validate(GestureType.FIST, 0.9)
        validator.validate(GestureType.OPEN_PALM, 0.9)
        validator.validate(GestureType.SCISSOR, 0.9)
        # 三帧各不相同，不应确认
        result = validator.validate(GestureType.FIST, 0.9)
        assert result is False

    def test_is_in_cooldown(self, validator):
        """测试冷却状态查询。"""
        assert validator.is_in_cooldown is False
        # 触发确认
        validator.validate(GestureType.FIST, 0.9)
        validator.validate(GestureType.FIST, 0.9)
        validator.validate(GestureType.FIST, 0.9)
        assert validator.is_in_cooldown is True

    def test_last_confirmed_gesture(self, validator):
        """测试上次确认手势记录。"""
        assert validator.last_confirmed_gesture == GestureType.NONE
        validator.validate(GestureType.FIST, 0.9)
        validator.validate(GestureType.FIST, 0.9)
        validator.validate(GestureType.FIST, 0.9)
        assert validator.last_confirmed_gesture == GestureType.FIST
