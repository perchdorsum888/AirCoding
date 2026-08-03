"""自动批准模式模块。

使用 uiautomation 库监听目标AI软件窗口的UI元素变化，
检测到确认对话框/按钮时自动注入确认键。

轮询间隔500ms，搜索目标AI软件窗口下的 ButtonControl，
匹配"确认/允许/Execute/Run"等关键词。
"""

import threading
import time
from typing import Optional

from src.action.ai_software_detector import AISoftwareDetector
from src.action.keyboard_injector import KeyboardInjector
from src.utils.logger import get_logger

_logger = get_logger("AutoApproval")

# 尝试导入 uiautomation
try:
    import uiautomation as ua
    _HAS_UIA = True
except ImportError:
    _HAS_UIA = False
    _logger.warning("uiautomation not installed, auto-approval functionality limited")

# 确认按钮关键词（中英文）
CONFIRM_KEYWORDS = [
    "确认", "允许", "同意", "是", "确定", "执行", "继续", "应用", "保存",
    "Confirm", "Allow", "Yes", "OK", "Execute", "Run", "Continue", "Apply",
    "Save", "Accept", "Approve", "Proceed",
]

# 拒绝按钮关键词
REJECT_KEYWORDS = [
    "拒绝", "取消", "否", "停止", "中断",
    "Reject", "Cancel", "No", "Stop", "Abort", "Deny",
]

# 轮询间隔（毫秒）
POLL_INTERVAL_MS = 500


class AutoApprovalController:
    """自动批准控制器。

    在自动批准模式下，定期轮询目标AI软件窗口的UI元素，
    检测到确认请求时自动注入确认键。

    Attributes:
        _enabled: 是否启用自动批准。
        _detector: AI软件检测器。
        _injector: 键盘注入器。
        _target_window: 目标窗口标题。
        _thread: 轮询线程。
        _running: 线程运行标志。
    """

    def __init__(
        self,
        detector: AISoftwareDetector,
        injector: KeyboardInjector,
        config_manager=None,
    ) -> None:
        """初始化自动批准控制器。

        Args:
            detector: AI软件检测器。
            injector: 键盘注入器。
            config_manager: 配置管理器（可选）。
        """
        self._enabled = False
        self._detector = detector
        self._injector = injector
        self._config_manager = config_manager
        self._target_window: Optional[str] = None
        self._running = False
        self._thread: Optional[threading.Thread] = None

        # 回调
        self._on_approve_callback = None

    def enable(self) -> None:
        """启用自动批准模式。"""
        if self._enabled:
            return
        self._enabled = True
        self._running = True

        if _HAS_UIA:
            self._thread = threading.Thread(
                target=self._monitor_loop,
                name="AutoApprovalThread",
                daemon=True,
            )
            self._thread.start()
            _logger.info("Auto-approval mode enabled")
        else:
            _logger.warning("uiautomation unavailable, auto-approval degraded (key injection only)")

    def disable(self) -> None:
        """禁用自动批准模式。"""
        self._enabled = False
        self._running = False
        if self._thread is not None and self._thread.is_alive():
            self._thread.join(timeout=2.0)
        self._thread = None
        _logger.info("Auto-approval mode disabled")

    def is_enabled(self) -> bool:
        """返回是否启用自动批准。"""
        return self._enabled

    def check_for_ai_request(self) -> bool:
        """检查当前前台AI软件是否有确认请求。

        Returns:
            True 如果检测到确认请求。
        """
        if not _HAS_UIA:
            return False

        software_name = self._detector.detect_foreground_ai()
        if software_name is None:
            return False

        return self._monitor_ui_elements()

    def trigger_auto_approval(self) -> bool:
        """触发自动批准（注入确认键）。

        Returns:
            True 如果注入成功。
        """
        # 优先注入 Enter 键
        success = self._injector.inject_key("enter")
        if success:
            _logger.info("Auto-approval triggered: Enter")
        else:
            # 降级注入 Y 键
            success = self._injector.inject_key("y")
            _logger.info("Auto-approval triggered: Y (fallback after Enter failure)")

        if self._on_approve_callback is not None:
            try:
                self._on_approve_callback()
            except Exception:
                pass

        return success

    def set_approve_callback(self, callback) -> None:
        """设置批准回调函数。

        Args:
            callback: 回调函数，无参数。
        """
        self._on_approve_callback = callback

    def _monitor_loop(self) -> None:
        """自动批准轮询主循环。

        每500ms检查一次目标AI软件窗口是否有确认请求。
        """
        _logger.debug("Auto-approval polling loop started")
        while self._running:
            try:
                if self.check_for_ai_request():
                    self.trigger_auto_approval()
                    # 触发后等待一段时间避免重复
                    time.sleep(1.0)
            except Exception as e:
                _logger.error("Auto-approval polling exception: %s", e)

            time.sleep(POLL_INTERVAL_MS / 1000.0)

        _logger.debug("Auto-approval polling loop ended")

    def _monitor_ui_elements(self) -> bool:
        """监控目标AI软件窗口的UI元素，检测确认按钮。

        使用 uiautomation 搜索前台窗口下的 ButtonControl，
        匹配确认关键词。

        Returns:
            True 如果检测到确认请求。
        """
        if not _HAS_UIA:
            return False

        try:
            # 获取前台窗口
            foreground = ua.GetForegroundControl()
            if foreground is None:
                return False

            window = foreground.GetParentControl()
            if window is None:
                window = foreground

            # 搜索按钮控件
            buttons = window.GetChildren()
            found_confirm = self._search_buttons_recursive(window, depth=0, max_depth=4)

            return found_confirm

        except Exception as e:
            _logger.debug("UI element monitoring exception: %s", e)
            return False

    def _search_buttons_recursive(
        self, control, depth: int = 0, max_depth: int = 4
    ) -> bool:
        """递归搜索控件树中的确认按钮。

        Args:
            control: 当前控件。
            depth: 当前递归深度。
            max_depth: 最大递归深度。

        Returns:
            True 如果找到确认按钮。
        """
        if depth > max_depth:
            return False

        try:
            # 检查当前控件是否为按钮
            ctrl_type = control.ControlTypeName
            if ctrl_type == "ButtonControl":
                name = control.Name or ""
                if self._match_confirm_keyword(name):
                    _logger.info("Confirmation button detected: %s", name)
                    return True

            # 递归搜索子控件
            children = control.GetChildren()
            for child in children:
                if self._search_buttons_recursive(child, depth + 1, max_depth):
                    return True

        except Exception:
            pass

        return False

    @staticmethod
    def _match_confirm_keyword(text: str) -> bool:
        """检查文本是否匹配确认关键词。

        Args:
            text: 按钮文本。

        Returns:
            True 如果匹配确认关键词。
        """
        text_lower = text.lower().strip()
        for keyword in CONFIRM_KEYWORDS:
            if keyword.lower() in text_lower:
                return True
        return False

    @staticmethod
    def _match_reject_keyword(text: str) -> bool:
        """检查文本是否匹配拒绝关键词。

        Args:
            text: 按钮文本。

        Returns:
            True 如果匹配拒绝关键词。
        """
        text_lower = text.lower().strip()
        for keyword in REJECT_KEYWORDS:
            if keyword.lower() in text_lower:
                return True
        return False
