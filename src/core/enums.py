"""枚举类型定义模块。

定义AirCoding全部枚举类型，供跨模块共享。
包括：手势类型、灯效状态、系统模式、手部侧别、光照条件。
"""

from enum import Enum


class GestureType(Enum):
    """手势/表情类型枚举。

    共9种（含NONE），涵盖8种可识别手势/表情。
    """
    NONE = "none"                    # 未检测到
    PHONE_CALL = "phone_call"        # 🤙 打电话（语音输入激活）
    OK = "ok"                        # 👌 OK手势（确认/Enter）
    THUMBS_UP = "thumbs_up"          # 👍 竖拇指（已删除，保留枚举兼容）
    THUMBS_DOWN = "thumbs_down"      # 👎 拇指朝下（拒绝）
    PINCH = "pinch"                  # 🤏 捏合（模式切换）
    FIST = "fist"                    # ✊ 握拳（已删除，保留枚举兼容）
    OPEN_PALM = "open_palm"          # ✋ 张开（Escape）
    SCISSOR = "scissor"              # ✌️ 剪刀手（Ctrl+Z）
    RAISE_EYEBROW = "raise_eyebrow"  # 🤨 挑眉（模式切换）


class LightState(Enum):
    """灯效状态枚举（7种核心状态）。

    每种状态对应一种动画效果和颜色。
    """
    STANDBY = "standby"                # 待机：柔和蓝呼吸灯
    RECOGNIZING = "recognizing"        # 识别中：青色脉动扫描
    RECORDING = "recording"            # 录音中：紫红色波形脉动
    TRIGGERED = "triggered"            # 已触发：白色闪光→动作色
    ERROR = "error"                    # 错误：红色快速闪烁
    AUTO_APPROVE = "auto_approve"      # 自动批准待机：绿色常亮微脉动
    MANUAL_CONFIRM = "manual_confirm"  # 手动确认待机：橙色常亮微脉动


class SystemMode(Enum):
    """系统模式枚举。"""
    AUTO_APPROVE = "auto_approve"       # 自动批准模式
    MANUAL_CONFIRM = "manual_confirm"   # 手动确认模式


class HandSide(Enum):
    """手部侧别枚举。"""
    LEFT = "left"
    RIGHT = "right"


class LightCondition(Enum):
    """光照条件枚举。"""
    LOW = "low"          # 低光照（<100 lux）
    NORMAL = "normal"    # 正常光照（100-1000 lux）
    HIGH = "high"        # 强光照（>1000 lux）
    BACKLIT = "backlit"  # 逆光
