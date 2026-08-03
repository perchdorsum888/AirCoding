"""手势映射配置模块。

5种手势映射（不区分左右手）：
  👌 OK手势 → Enter（确认）
  ✋ → Escape
  ✌️ → Ctrl+Z
  🤙 → 语音输入（动态热键）
  🤏 → 模式切换（内部逻辑）
"""

from dataclasses import dataclass, field
from typing import Optional

from src.core.enums import GestureType, HandSide


@dataclass
class GestureMapping:
    """手势映射配置项。"""
    gesture: GestureType
    hand_side: HandSide
    action_name: str
    key_sequence: list = field(default_factory=list)
    emoji: str = ""
    confirm_frames: int = 3
    hold_duration_ms: int = 0
    cooldown_ms: int = 500
    confidence_threshold: float = 0.85
    action_color: str = "#FFFFFF"


def _build_default_mappings() -> list:
    """构建5种默认手势映射（不区分左右手）。"""
    THRESHOLD = 0.85
    return [
        GestureMapping(
            gesture=GestureType.OK,
            hand_side=HandSide.RIGHT,
            action_name="Enter",
            key_sequence=["enter"],
            emoji="👌",
            confidence_threshold=THRESHOLD,
            action_color="#34C759",
        ),
        GestureMapping(
            gesture=GestureType.OPEN_PALM,
            hand_side=HandSide.RIGHT,
            action_name="Escape",
            key_sequence=["escape"],
            emoji="✋",
            confidence_threshold=THRESHOLD,
            action_color="#5AC8FA",
        ),
        GestureMapping(
            gesture=GestureType.SCISSOR,
            hand_side=HandSide.RIGHT,
            action_name="撤销 Ctrl+Z",
            key_sequence=["ctrl", "z"],
            emoji="✌️",
            confidence_threshold=THRESHOLD,
            action_color="#FF9500",
        ),
        GestureMapping(
            gesture=GestureType.PHONE_CALL,
            hand_side=HandSide.RIGHT,
            action_name="语音输入激活",
            key_sequence=[],
            emoji="🤙",
            hold_duration_ms=500,
            confidence_threshold=THRESHOLD,
            action_color="#FF2D55",
        ),
        GestureMapping(
            gesture=GestureType.PINCH,
            hand_side=HandSide.RIGHT,
            action_name="模式切换",
            key_sequence=[],
            emoji="🤏",
            hold_duration_ms=1500,
            cooldown_ms=1000,
            confidence_threshold=THRESHOLD,
            action_color="#AF52DE",
        ),
    ]


DEFAULT_GESTURE_MAPPINGS: list = _build_default_mappings()

GESTURE_EMOJI: dict = {
    GestureType.NONE: "",
    GestureType.PHONE_CALL: "🤙",
    GestureType.OK: "👌",
    GestureType.PINCH: "🤏",
    GestureType.OPEN_PALM: "✋",
    GestureType.SCISSOR: "✌️",
}

GESTURE_ACTION_COLOR: dict = {
    GestureType.NONE: "#FFFFFF",
    GestureType.PHONE_CALL: "#FF2D55",
    GestureType.OK: "#34C759",
    GestureType.PINCH: "#AF52DE",
    GestureType.OPEN_PALM: "#5AC8FA",
    GestureType.SCISSOR: "#FF9500",
}


def build_mappings_from_config(config_mappings: list) -> list:
    """从配置字典列表构建 GestureMapping 对象列表。"""
    mappings = []
    for item in config_mappings:
        try:
            gesture = GestureType(item.get("gesture", "none"))
        except ValueError:
            continue
        try:
            hand_side = HandSide(item.get("hand_side", "right"))
        except ValueError:
            hand_side = HandSide.RIGHT
        mapping = GestureMapping(
            gesture=gesture,
            hand_side=hand_side,
            action_name=item.get("action_name", ""),
            key_sequence=item.get("key_sequence", []),
            emoji=item.get("emoji", GESTURE_EMOJI.get(gesture, "")),
            confirm_frames=item.get("confirm_frames", 3),
            hold_duration_ms=item.get("hold_duration_ms", 0),
            cooldown_ms=item.get("cooldown_ms", 500),
            confidence_threshold=item.get("confidence_threshold", 0.85),
            action_color=item.get("action_color", "#FFFFFF"),
        )
        mappings.append(mapping)
    return mappings


def get_mapping_by_gesture_and_side(
    mappings: list,
    gesture: GestureType,
    hand_side: HandSide,
) -> Optional[GestureMapping]:
    """从映射列表中查找指定手势的映射（不区分手侧）。"""
    for mapping in mappings:
        if mapping.gesture == gesture:
            return mapping
    return None
