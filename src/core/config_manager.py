"""配置管理模块。

提供线程安全的配置加载、合并、保存和持久化功能。
默认配置从 config/default_config.yaml 加载，
用户配置持久化到 %APPDATA%/AirCoding/user_config.yaml，
用户配置覆盖默认配置中的同名键。
"""

import copy
import os
import threading
from pathlib import Path
from typing import Any, Optional

import yaml

from src.utils.logger import get_logger

_logger = get_logger("ConfigManager")


def _get_appdata_dir() -> Path:
    """获取应用数据目录路径（%APPDATA%/AirCoding/）。

    Returns:
        应用数据目录 Path 对象。
    """
    appdata = os.environ.get("APPDATA")
    if appdata:
        return Path(appdata) / "AirCoding"
    # 非Windows环境回退
    return Path.home() / ".aircoding"


def _deep_merge(base: dict, override: dict) -> dict:
    """深度合并两个字典，override 中的值覆盖 base 中的同名键。

    Args:
        base: 基础字典。
        override: 覆盖字典。

    Returns:
        合并后的新字典（不修改输入）。
    """
    result = copy.deepcopy(base)
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = copy.deepcopy(value)
    return result


class ConfigManager:
    """线程安全的配置管理器。

    加载默认配置并与用户配置合并，提供线程安全的 get/set 接口。
    配置变更时自动持久化用户配置。

    Attributes:
        _default_config: 默认配置字典。
        _user_config: 用户配置字典（仅包含覆盖项）。
        _merged_config: 合并后的完整配置。
        _config_path: 用户配置文件路径。
        _lock: 线程锁。
    """

    def __init__(
        self,
        default_config_path: Optional[str] = None,
        user_config_dir: Optional[str] = None,
    ) -> None:
        """初始化配置管理器。

        Args:
            default_config_path: 默认配置文件路径。None则使用项目内 config/default_config.yaml。
            user_config_dir: 用户配置目录。None则使用 %APPDATA%/AirCoding/。
        """
        self._lock = threading.Lock()

        # 默认配置路径
        if default_config_path is None:
            project_root = Path(__file__).resolve().parent.parent.parent
            default_config_path = str(project_root / "config" / "default_config.yaml")
        self._default_config_path = default_config_path

        # 用户配置路径
        if user_config_dir is None:
            user_config_dir = str(_get_appdata_dir())
        self._config_dir = Path(user_config_dir)
        self._config_dir.mkdir(parents=True, exist_ok=True)
        self._config_path = self._config_dir / "user_config.yaml"

        self._default_config: dict = {}
        self._user_config: dict = {}
        self._merged_config: dict = {}

        self.load_config()

    def load_config(self) -> dict:
        """加载配置：读取默认配置，合并用户配置。

        Returns:
            合并后的完整配置字典。
        """
        with self._lock:
            # 加载默认配置
            try:
                with open(self._default_config_path, "r", encoding="utf-8") as f:
                    self._default_config = yaml.safe_load(f) or {}
                _logger.info("Default config loaded: %s", self._default_config_path)
            except FileNotFoundError:
                _logger.error("Default config file not found: %s", self._default_config_path)
                self._default_config = {}
            except yaml.YAMLError as e:
                _logger.error("Failed to parse default config file: %s", e)
                self._default_config = {}

            # 加载用户配置
            try:
                if self._config_path.exists():
                    with open(self._config_path, "r", encoding="utf-8") as f:
                        self._user_config = yaml.safe_load(f) or {}
                    _logger.info("User config loaded: %s", self._config_path)
                else:
                    self._user_config = {}
                    _logger.info("User config not found, using default config")
            except yaml.YAMLError as e:
                _logger.warning("User config file corrupted, falling back to default config: %s", e)
                self._user_config = {}

            # 合并配置
            self._merged_config = _deep_merge(self._default_config, self._user_config)
            return copy.deepcopy(self._merged_config)

    def save_config(self) -> None:
        """持久化用户配置到磁盘。"""
        with self._lock:
            try:
                with open(self._config_path, "w", encoding="utf-8") as f:
                    yaml.safe_dump(
                        self._user_config,
                        f,
                        default_flow_style=False,
                        allow_unicode=True,
                        sort_keys=False,
                    )
                _logger.info("User config saved: %s", self._config_path)
            except Exception as e:
                _logger.error("Failed to save user config: %s", e)

    def get(self, key: str, default: Any = None) -> Any:
        """按点分路径获取配置值。

        Args:
            key: 点分路径键，如 "recognition.thresholds.confidence"。
            default: 键不存在时的默认返回值。

        Returns:
            配置值，或 default。
        """
        with self._lock:
            keys = key.split(".")
            value = self._merged_config
            for k in keys:
                if isinstance(value, dict) and k in value:
                    value = value[k]
                else:
                    return default
            return copy.deepcopy(value)

    def set(self, key: str, value: Any) -> None:
        """按点分路径设置配置值并持久化。

        Args:
            key: 点分路径键。
            value: 要设置的值。
        """
        with self._lock:
            keys = key.split(".")
            # 更新用户配置
            user_target = self._user_config
            for k in keys[:-1]:
                if k not in user_target or not isinstance(user_target[k], dict):
                    user_target[k] = {}
                user_target = user_target[k]
            user_target[keys[-1]] = copy.deepcopy(value)

            # 更新合并配置
            merged_target = self._merged_config
            for k in keys[:-1]:
                if k not in merged_target or not isinstance(merged_target[k], dict):
                    merged_target[k] = {}
                merged_target = merged_target[k]
            merged_target[keys[-1]] = copy.deepcopy(value)

        # 锁外持久化
        self.save_config()

    def reset_to_default(self) -> None:
        """重置用户配置为默认配置（清空用户配置文件）。"""
        with self._lock:
            self._user_config = {}
            self._merged_config = copy.deepcopy(self._default_config)
        self.save_config()
        _logger.info("Config reset to defaults")

    def get_all(self) -> dict:
        """返回完整配置字典的深拷贝。"""
        with self._lock:
            return copy.deepcopy(self._merged_config)

    def get_thresholds(self) -> dict:
        """获取识别阈值配置。"""
        return self.get("recognition.thresholds", {})

    def get_light_effects(self) -> dict:
        """获取灯效配置。"""
        return self.get("light_effects", {})

    def get_ai_software_registry(self) -> dict:
        """获取AI软件注册表。"""
        return self.get("ai_software", {})

    def get_gesture_mappings(self) -> list:
        """获取手势映射列表。"""
        return self.get("gesture_mappings", [])

    def get_validation_config(self) -> dict:
        """获取防误触配置。"""
        return self.get("validation", {})

    def get_ui_config(self) -> dict:
        """获取UI配置。"""
        return self.get("ui", {})

    def is_onboarding_completed(self) -> bool:
        """检查是否已完成新手引导。"""
        return self.get("onboarding.completed", False)

    def set_onboarding_completed(self, completed: bool = True) -> None:
        """标记新手引导完成状态。"""
        self.set("onboarding.completed", completed)

    @property
    def config_path(self) -> str:
        """返回用户配置文件路径。"""
        return str(self._config_path)
