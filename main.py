"""AirCoding应用入口。

创建 QApplication，初始化各模块，启动线程，处理退出清理。

模块初始化顺序：
    ConfigManager → Logger → CameraManager → ImageProcessor →
    RecognitionEngine → StateMachine → GestureMapper → KeyboardInjector →
    AISoftwareDetector → AutoApprovalController → MainWindow

线程模型：
    - 主线程：PySide6 事件循环（UI渲染/动画/用户交互）
    - 摄像头线程：CameraManager 10fps帧采集
    - 识别线程：RecognitionEngine MediaPipe推理
"""

import sys
sys.dont_write_bytecode = True  # 禁用 .pyc 缓存，确保使用最新源码
import signal
from pathlib import Path
from typing import Optional

from src.utils.logger import setup_logger, get_logger
from src.core.config_manager import ConfigManager
from src.core.enums import SystemMode, LightState, GestureType, HandSide
from src.core.i18n import t
from PySide6.QtCore import QObject

_logger = get_logger("Main")


class GestureActionController(QObject):
    """手势动作执行控制器。

    监听识别引擎的手势检测信号，根据手势类型执行对应的键盘注入或模式切换。
    继承QObject以确保跨线程信号能正确投递（识别线程→主线程）。
    """

    def __init__(
        self,
        gesture_mapper,
        keyboard_injector,
        ai_detector,
        state_machine,
        auto_approval,
    ) -> None:
        super().__init__()  # QObject初始化，确保跨线程信号能正确投递
        self._gesture_mapper = gesture_mapper
        self._keyboard_injector = keyboard_injector
        self._ai_detector = ai_detector
        self._state_machine = state_machine
        self._auto_approval = auto_approval

    def handle_gesture(self, result) -> None:
        """处理已确认的手势，执行对应动作。

        Args:
            result: RecognitionResult 对象。
        """
        gesture = result.gesture
        hand_side = result.hand_side

        _logger.info("Executing gesture action: %s, hand side: %s", gesture.value, hand_side.value)

        if gesture == GestureType.PHONE_CALL:
            self._handle_phone_call()
        elif gesture == GestureType.PINCH:
            self._handle_mode_switch()
        else:
            self._handle_keyboard_action(gesture, hand_side)

    def _handle_phone_call(self) -> None:
        """处理打电话手势上升沿：检测AI软件 → 获取热键 → 注入 → 开始录音。"""
        software_name = self._ai_detector.detect_foreground_ai()
        if software_name is None:
            _logger.warning("No AI software detected, cannot activate voice input")
            return

        hotkey = self._ai_detector.get_hotkey(software_name)
        if not hotkey:
            _logger.warning("AI software %s has no hotkey configured", software_name)
            return

        display_name = self._ai_detector.get_display_name(software_name)
        success = self._keyboard_injector.inject_hotkey(*hotkey)
        if success:
            _logger.info("Voice input started: %s → %s", display_name, "+".join(hotkey))
            self._state_machine.start_recording()
        else:
            _logger.error("Hotkey injection failed: %s", "+".join(hotkey))

    def _handle_phone_call_end(self) -> None:
        """处理打电话手势下降沿：再次注入热键 → 停止录音。

        AI软件的语音输入是点按切换模式：按一次开始，再按一次结束。
        手势消失时需要再注入一次热键来停止录音。
        """
        software_name = self._ai_detector.detect_foreground_ai()
        if software_name is None:
            _logger.info("Stopping recording: no AI software detected (window may have switched)")
            self._state_machine.stop_recording()
            return

        hotkey = self._ai_detector.get_hotkey(software_name)
        if not hotkey:
            _logger.warning("AI software %s has no hotkey configured, cannot stop recording", software_name)
            self._state_machine.stop_recording()
            return

        display_name = self._ai_detector.get_display_name(software_name)
        success = self._keyboard_injector.inject_hotkey(*hotkey)
        if success:
            _logger.info("Voice input stopped: %s → %s", display_name, "+".join(hotkey))
        else:
            _logger.error("Stop hotkey injection failed: %s", "+".join(hotkey))

        self._state_machine.stop_recording()

    def _handle_mode_switch(self) -> None:
        """处理模式切换手势：toggle 自动批准/手动确认。"""
        new_mode = self._state_machine.toggle_mode()
        _logger.info("Mode switched: %s", new_mode.value)

        # 自动批准模式启用时，启动自动批准控制器
        if new_mode == SystemMode.AUTO_APPROVE:
            self._auto_approval.enable()
        else:
            self._auto_approval.disable()

    def _handle_keyboard_action(self, gesture: GestureType, hand_side: HandSide) -> None:
        """处理键盘快捷操作手势：查映射表 → 注入按键。"""
        key_sequence = self._gesture_mapper.get_key_sequence(gesture, hand_side)
        if not key_sequence:
            _logger.warning("Gesture %s has no keyboard mapping (empty key_sequence)", gesture.value)
            return

        _logger.info("Preparing key injection: %s → %s", gesture.value, "+".join(key_sequence))
        if len(key_sequence) == 1:
            success = self._keyboard_injector.inject_key(key_sequence[0])
        else:
            success = self._keyboard_injector.inject_hotkey(*key_sequence)

        if success:
            _logger.info("Keyboard injection succeeded: %s", "+".join(key_sequence))
        else:
            _logger.error("Keyboard injection failed: %s", "+".join(key_sequence))


def main() -> int:
    """应用主入口函数。

    优化启动：UI先显示，MediaPipe导入和摄像头打开在后台并行。
    预计启动时间从8.5s降至2-3s。

    Returns:
        应用退出码（0正常退出，非0异常退出）。
    """
    _logger.info("=" * 50)
    _logger.info("AirCoding starting...")
    _logger.info("=" * 50)

    # 1. 初始化配置管理器（~150ms）
    config_manager = ConfigManager()
    _logger.info("Config manager initialized")

    # 1.5 加载 UI 语言设置（默认英文，可切换中文）
    from src.core.i18n import set_language
    lang = config_manager.get("ui.language", "en")
    set_language(lang)
    _logger.info("UI language set: %s", lang)

    # 2. 初始化 PySide6 应用（~200ms）
    try:
        from PySide6.QtWidgets import QApplication
        from PySide6.QtCore import Qt, QTimer
    except ImportError:
        _logger.error("PySide6 not installed, please run: pip install PySide6")
        return 1

    app = QApplication(sys.argv)
    app.setApplicationName("AirCoding")
    app.setQuitOnLastWindowClosed(False)

    # 3. 初始化核心模块（快，~100ms）
    from src.core.state_machine import StateMachine

    initial_mode_str = config_manager.get("system.mode", "manual_confirm")
    try:
        initial_mode = SystemMode(initial_mode_str)
    except ValueError:
        initial_mode = SystemMode.MANUAL_CONFIRM

    state_machine = StateMachine(initial_mode=initial_mode)

    from src.action.keyboard_injector import KeyboardInjector
    from src.action.gesture_mapper import GestureMapper
    from src.action.ai_software_detector import AISoftwareDetector
    from src.action.auto_approval import AutoApprovalController

    keyboard_injector = KeyboardInjector()
    gesture_mapper = GestureMapper(config_manager)
    ai_detector = AISoftwareDetector(config_manager)
    auto_approval = AutoApprovalController(ai_detector, keyboard_injector, config_manager)

    from src.utils.audio import AudioFeedback
    audio_feedback = AudioFeedback(
        enabled=config_manager.get("ui.sound_feedback_enabled", True)
    )

    # 4. 初始化UI层（快，~200ms）—— 立即显示
    from src.ui.main_window import MainWindow

    main_window = MainWindow(
        state_machine=state_machine,
        gesture_mapper=gesture_mapper,
        config_manager=config_manager,
        audio_feedback=audio_feedback,
    )
    main_window.show()
    main_window.show_toast(t("Initializing recognition engine..."), "⏳")
    _logger.info("UI layer shown (initializing)")

    # 5. 后台并行初始化：MediaPipe导入 和 摄像头打开 同时进行
    import threading

    init_result = {
        'recognition_engine': None,
        'camera_manager': None,
        'calibrator': None,
        'error_mp': None,
        'error_cam': None,
        'mp_done': False,
        'cam_done': False,
        'action_controller': None,  # 持久引用，防止GC
    }

    def init_mediapipe():
        """后台线程A：导入MediaPipe + 创建识别引擎（~3.7s）。"""
        try:
            from src.recognition.recognition_engine import RecognitionEngine
            from src.recognition.calibrator import Calibrator
            from src.camera.image_processor import ImageProcessor

            image_processor = ImageProcessor(config_manager)
            recognition_engine = RecognitionEngine(
                config_manager=config_manager,
                image_processor=image_processor,
            )
            calibrator = Calibrator()
            recognition_engine.set_calibrator(calibrator)
            cal_thresholds = calibrator.get_thresholds()
            if cal_thresholds:
                recognition_engine._hand_classifier.update_thresholds(cal_thresholds)
                _logger.info("Calibration thresholds loaded")

            init_result['recognition_engine'] = recognition_engine
            init_result['calibrator'] = calibrator
            _logger.info("MediaPipe initialization complete")
        except Exception as e:
            init_result['error_mp'] = str(e)
            _logger.error("MediaPipe initialization failed: %s", e)
        finally:
            init_result['mp_done'] = True

    def init_camera():
        """后台线程B：打开摄像头（~3.5s），与MediaPipe并行。"""
        try:
            from src.camera.camera_manager import CameraManager
            camera_manager = CameraManager(config_manager)

            # 设置暂停/恢复回调
            def on_camera_paused():
                main_window.show_toast(t("Camera occupied by another app, waiting to recover..."), "⚠️")

            def on_camera_resumed():
                main_window.show_toast(t("Camera recovered"), "✅")

            camera_manager.set_callbacks(
                pause_callback=on_camera_paused,
                resume_callback=on_camera_resumed,
            )

            # 在后台直接打开摄像头（不等MediaPipe）
            if camera_manager.start():
                init_result['camera_manager'] = camera_manager
                _logger.info("Camera initialization complete")
            else:
                init_result['error_cam'] = "Failed to open camera"
                _logger.error("Failed to open camera")
        except Exception as e:
            init_result['error_cam'] = str(e)
            _logger.error("Camera initialization failed: %s", e)
        finally:
            init_result['cam_done'] = True

    # 两个线程并行启动
    thread_mp = threading.Thread(target=init_mediapipe, name="InitMediaPipe", daemon=True)
    thread_cam = threading.Thread(target=init_camera, name="InitCamera", daemon=True)
    thread_mp.start()
    thread_cam.start()

    # 6. 主线程轮询等待两者都完成
    def check_init_done():
        """检查后台初始化是否完成。"""
        if not (init_result['mp_done'] and init_result['cam_done']):
            return

        timer_check.stop()
        _logger.info("Background initialization complete: mp=%s cam=%s", init_result['mp_done'], init_result['cam_done'])

        try:
            if init_result['error_mp']:
                _logger.error("MediaPipe initialization failed: %s", init_result['error_mp'])
                main_window.show_toast(t("Initialization failed"), "⚠️")
                state_machine.force_state(LightState.ERROR)
                return
            if init_result['error_cam']:
                _logger.error("Camera initialization failed: %s", init_result['error_cam'])
                # 摄像头失败仍继续，识别引擎可用供校准使用

            recognition_engine = init_result['recognition_engine']
            camera_manager = init_result['camera_manager']
            _logger.info("Recognition engine=%s, camera=%s",
                        recognition_engine is not None,
                        camera_manager is not None if camera_manager else False)

            # 连接信号
            action_controller = GestureActionController(
                gesture_mapper=gesture_mapper,
                keyboard_injector=keyboard_injector,
                ai_detector=ai_detector,
                state_machine=state_machine,
                auto_approval=auto_approval,
            )
            init_result['action_controller'] = action_controller
            _connect_signals(
                recognition_engine, main_window, state_machine, gesture_mapper,
                keyboard_injector, ai_detector, auto_approval, audio_feedback,
                action_controller,
            )
            main_window.set_recognition_engine(recognition_engine)
            _logger.info("Signal connections complete, gesture_detected→handle_gesture bound")

            # 摄像头已在后台线程B中启动，这里只需启动识别引擎
            if camera_manager and camera_manager.is_available():
                recognition_engine.start(camera_manager)
                _logger.info("Recognition engine started, recognition loop running")
                main_window.show_toast(t("Ready"), "✅")
            else:
                _logger.error("Camera unavailable, recognition engine not started! camera_manager=%s", camera_manager)
                state_machine.force_state(LightState.ERROR)
                main_window.show_toast(t("Camera unavailable"), "⚠️")

            # 新手引导检查
            if not config_manager.is_onboarding_completed():
                from src.ui.onboarding import OnboardingWidget
                onboarding = OnboardingWidget(recognition_engine, config_manager)
                onboarding.finished.connect(lambda: main_window.show())
                onboarding.show()
                _logger.info("First launch, showing onboarding")

            # 自动批准模式
            if state_machine.get_mode() == SystemMode.AUTO_APPROVE:
                auto_approval.enable()

        except Exception as e:
            _logger.error("check_init_done exception: %s", e)
            import traceback
            _logger.error(traceback.format_exc())
            main_window.show_toast(t("Initialization error: {}").format(str(e)), "⚠️")

    timer_check = QTimer()
    timer_check.timeout.connect(check_init_done)
    timer_check.start(200)  # 每200ms检查一次

    # 7. 注册全局热键
    global_hotkey_listener = _setup_global_hotkey(main_window)
    _logger.info("Global hotkey registered: Ctrl+Alt+K to toggle panel")

    # 12. 连接退出清理信号
    def _on_about_to_quit():
        _logger.info("Application exiting...")
        try:
            if global_hotkey_listener:
                global_hotkey_listener.stop()
            auto_approval.disable()
            recognition_engine.stop()
            camera_manager.stop()
            config_manager.save_config()
            _logger.info("Cleanup complete")
        except Exception as e:
            _logger.error("Exit cleanup exception: %s", e)

    app.aboutToQuit.connect(_on_about_to_quit)

    # 13. 注册信号处理
    signal.signal(signal.SIGINT, lambda *_: app.quit())

    # 14. 进入事件循环
    _logger.info("Entering main event loop")
    exit_code = app.exec()

    # 15. 确保清理（兜底）
    _on_about_to_quit()
    return exit_code


def _setup_global_hotkey(main_window):
    """设置全局热键 Ctrl+Alt+K 切换面板可见性。

    使用 pynput 的 GlobalHotKeys 监听全局按键，
    类似输入法切换的方式快速显示/隐藏面板。

    Args:
        main_window: 主窗口实例。

    Returns:
        pynput GlobalHotKeys 监听器实例。
    """
    try:
        from pynput import keyboard

        def on_toggle():
            # 在主线程中执行 UI 操作
            from PySide6.QtCore import QTimer
            QTimer.singleShot(0, main_window.toggle_visibility)

        listener = keyboard.GlobalHotKeys({
            '<ctrl>+<alt>+k': on_toggle,
        })
        listener.daemon = True
        listener.start()
        return listener
    except Exception as e:
        _logger.warning("Global hotkey registration failed: %s", e)
        return None


def _connect_signals(
    recognition_engine,
    main_window,
    state_machine,
    gesture_mapper,
    keyboard_injector,
    ai_detector,
    auto_approval,
    audio_feedback,
    action_controller,
) -> None:
    """连接各模块间的 Qt Signal/Slot。

    Args:
        recognition_engine: 识别引擎。
        main_window: 主窗口。
        state_machine: 状态机。
        gesture_mapper: 手势映射器。
        keyboard_injector: 键盘注入器。
        ai_detector: AI软件检测器。
        auto_approval: 自动批准控制器。
        audio_feedback: 声音反馈。
        action_controller: 手势动作控制器。
    """
    # 识别引擎 → 主窗口（手势检测、预览更新）
    recognition_engine.gesture_detected.connect(main_window.on_gesture_detected)
    recognition_engine.landmarks_updated.connect(main_window.on_landmarks_updated)

    # 识别引擎 → 手势动作控制器（执行键盘注入/模式切换）
    recognition_engine.gesture_detected.connect(action_controller.handle_gesture)

    # 状态机 → 主窗口（灯效、模式、录音状态）
    state_machine.state_changed.connect(main_window.on_state_changed)
    state_machine.mode_changed.connect(main_window.on_mode_changed)
    state_machine.recording_state_changed.connect(main_window.on_recording_state_changed)

    # 识别引擎 → 状态机（状态变更请求）
    recognition_engine.state_change_requested.connect(state_machine.transition_to)

    # 识别引擎 → 状态机（录音停止请求：打电话手势消失时）
    recognition_engine.recording_stop_requested.connect(state_machine.stop_recording)
    recognition_engine.recording_stop_requested.connect(action_controller._handle_phone_call_end)


if __name__ == "__main__":
    # 确保项目根目录在 sys.path 中
    project_root = str(Path(__file__).resolve().parent)
    if project_root not in sys.path:
        sys.path.insert(0, project_root)

    sys.exit(main())
