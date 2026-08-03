"""手势→键盘映射模块。

查询 GestureConfig 获取手势对应的键盘动作。
右手→主操作（语音输入/确认/拒绝/Enter/Escape/Ctrl+Z/模式切换），
左手→辅助操作（Ctrl+C/Ctrl+V/自定义）。
支持自定义快捷键覆盖。
"""

from typing import Optional

from src.core.enums import GestureType, HandSide
from src.core.config_manager import ConfigManager
from src.core.gesture_config import (
    GestureMapping,
    DEFAULT_GESTURE_MAPPINGS,
    GESTURE_EMOJI,
    GESTURE_ACTION_COLOR,
    build_mappings_from_config,
    get_mapping_by_gesture_and_side,
)
from src.utils.logger import get_logger

_logger = get_logger("GestureMapper")


class GestureMapper:
    """手势→键盘映射器。

    维护手势到键盘动作的映射表，支持左右手分流和自定义快捷键。

    Attributes:
        _gesture_map: 手势映射列表。
        _config_manager: 配置管理器引用。
    """

    def __init__(self, config_manager: ConfigManager) -> None:
        """初始化手势映射器。

        从配置加载映射表，配置缺失时使用默认映射。

        Args:
            config_manager: 配置管理器。
        """
        self._config_manager = config_manager

        # 从配置加载映射
        config_mappings = config_manager.get_gesture_mappings()
        if config_mappings:
            self._gesture_map = build_mappings_from_config(config_mappings)
        else:
            self._gesture_map = list(DEFAULT_GESTURE_MAPPINGS)

        _logger.info("Gesture mapper initialized: %d mappings", len(self._gesture_map))

    def get_action(
        self, gesture: GestureType, hand_side: HandSide
    ) -> Optional[GestureMapping]:
        """获取手势对应的动作映射。

        Args:
            gesture: 手势类型。
            hand_side: 手部侧别。

        Returns:
            GestureMapping 对象，未找到返回 None。
        """
        mapping = get_mapping_by_gesture_and_side(
            self._gesture_map, gesture, hand_side
        )
        if mapping is None:
            _logger.debug(
                "Mapping not found: gesture=%s, hand_side=%s",
                gesture.value,
                hand_side.value,
            )
        return mapping

    def get_key_sequence(
        self, gesture: GestureType, hand_side: HandSide
    ) -> list:
        """获取手势对应的键盘按键序列。

        Args:
            gesture: 手势类型。
            hand_side: 手部侧别。

        Returns:
            按键序列列表，未找到返回空列表。
        """
        mapping = self.get_action(gesture, hand_side)
        if mapping is None:
            return []
        return mapping.key_sequence

    def get_emoji(self, gesture: GestureType) -> str:
        """获取手势对应的emoji。

        Args:
            gesture: 手势类型。

        Returns:
            emoji字符串。
        """
        return GESTURE_EMOJI.get(gesture, "")

    def get_action_color(self, gesture: GestureType) -> str:
        """获取手势对应的动作触发色。

        Args:
            gesture: 手势类型。

        Returns:
            十六进制色值字符串。
        """
        return GESTURE_ACTION_COLOR.get(gesture, "#FFFFFF")

    def update_mapping(
        self,
        gesture: GestureType,
        hand_side: HandSide,
        keys: list,
    ) -> None:
        """更新手势映射的键盘按键序列。

        Args:
            gesture: 手势类型。
            hand_side: 手部侧别。
            keys: 新的按键序列。
        """
        mapping = get_mapping_by_gesture_and_side(
            self._gesture_map, gesture, hand_side
        )
        if mapping is not None:
            mapping.key_sequence = list(keys)
            _logger.info(
                "Mapping updated: %s/%s → %s",
                gesture.value,
                hand_side.value,
                "+".join(keys) if keys else "(no keys)",
            )
        else:
            # 创建新映射
            new_mapping = GestureMapping(
                gesture=gesture,
                hand_side=hand_side,
                action_name="自定义",
                key_sequence=list(keys),
                emoji=GESTURE_EMOJI.get(gesture, ""),
                action_color=GESTURE_ACTION_COLOR.get(gesture, "#FFFFFF"),
            )
            self._gesture_map.append(new_mapping)
            _logger.info(
                "New mapping created: %s/%s → %s",
                gesture.value,
                hand_side.value,
                "+".join(keys) if keys else "(no keys)",
            )

    def get_all_mappings(self) -> list:
        """获取所有手势映射。

        Returns:
            GestureMapping 对象列表。
        """
        return list(self._gesture_map)

    def reload_from_config(self) -> None:
        """从配置管理器重新加载映射表。"""
        config_mappings = self._config_manager.get_gesture_mappings()
        if config_mappings:
            self._gesture_map = build_mappings_from_config(config_mappings)
        else:
            self._gesture_map = list(DEFAULT_GESTURE_MAPPINGS)
        _logger.info("Gesture mapping table reloaded: %d mappings", len(self._gesture_map))
