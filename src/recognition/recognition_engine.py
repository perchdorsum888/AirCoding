"""识别引擎模块。

编排 MediaPipe Hands + FaceMesh 并行推理，调用各子识别器完成完整识别流程。
在独立线程中运行，通过 Qt Signal 通知 UI 层。

识别流程（每帧）：
    1. 从摄像头队列取帧
    2. ImageProcessor 预处理
    3. MediaPipe Hands 推理 → 手部landmark
    4. MediaPipe FaceMesh 推理 → 面部landmark
    5. HandClassifier 手势分类
    6. FaceExpressionRecognizer 挑眉检测
    7. PhoneCallDetector 打电话手势检测
    8. GestureValidator 防误触验证
    9. 通过验证 → 发射 gesture_detected 信号
    10. 每帧发射 landmarks_updated 信号（用于预览）
"""

import threading
import time
from dataclasses import dataclass, field
from typing import Optional

import numpy as np

from src.core.enums import (
    GestureType,
    HandSide,
    LightCondition,
    LightState,
)
from src.core.config_manager import ConfigManager
from src.camera.image_processor import ImageProcessor
from src.recognition.hand_classifier import HandClassifier
from src.recognition.face_expression import FaceExpressionRecognizer
from src.recognition.phone_call_detector import PhoneCallDetector
from src.recognition.gesture_validator import GestureValidator
from src.utils.logger import get_logger

_logger = get_logger("RecognitionEngine")

# 尝试导入 PySide6
try:
    from PySide6.QtCore import QObject, Signal

    _HAS_QT = True
except ImportError:
    _HAS_QT = False

    class _SignalStub:
        def __init__(self, *args, **kwargs):
            self._handlers = []

        def connect(self, handler):
            self._handlers.append(handler)

        def emit(self, *args, **kwargs):
            for h in self._handlers:
                try:
                    h(*args, **kwargs)
                except Exception:
                    pass

    class QObject:  # type: ignore[no-redef]
        pass

    def Signal(*args, **kwargs):  # type: ignore[no-redef]
        return _SignalStub()


# 尝试导入 MediaPipe
try:
    import mediapipe as mp
    from mediapipe.python.solutions import hands as _mp_hands_mod
    from mediapipe.python.solutions import face_mesh as _mp_face_mesh_mod
    from mediapipe.python.solutions import drawing_utils as _mp_drawing_mod
    _mp_hands = _mp_hands_mod
    _mp_face_mesh = _mp_face_mesh_mod
    _mp_drawing = _mp_drawing_mod
    _HAS_MEDIAPIPE = True
except (ImportError, ModuleNotFoundError) as e:
    _HAS_MEDIAPIPE = False
    _logger.warning("MediaPipe not installed or initialization failed: %s", e)


@dataclass
class RecognitionResult:
    """识别结果数据结构。

    RecognitionEngine 每帧处理后的完整识别结果。

    Attributes:
        gesture: 识别到的手势类型。
        hand_side: 手部侧别（左/右）。
        confidence: 置信度 0.0~1.0。
        hand_landmarks: 21点手部landmark坐标（未检测到为None）。
        face_landmarks: 468点面部landmark坐标（未检测到为None）。
        hand_detected: 是否检测到手。
        face_detected: 是否检测到面部。
        phone_call_detected: 打电话手势是否检测到（手脸联合）。
        eyebrow_raised: 挑眉是否检测到。
        light_condition: 当前光照条件。
        timestamp: 帧时间戳。
    """
    gesture: GestureType = GestureType.NONE
    hand_side: HandSide = HandSide.RIGHT
    confidence: float = 0.0
    hand_landmarks: Optional[list] = None
    face_landmarks: Optional[list] = None
    hand_detected: bool = False
    face_detected: bool = False
    phone_call_detected: bool = False
    eyebrow_raised: bool = False
    light_condition: LightCondition = LightCondition.NORMAL
    timestamp: float = 0.0


class RecognitionEngine(QObject if _HAS_QT else object):
    """MediaPipe 识别编排引擎。

    在独立线程中运行，从摄像头帧队列取帧，
    执行完整的识别流程，通过 Qt Signal 通知 UI 层。

    Signals:
        gesture_detected: 手势确认触发（通过防误触验证）。
        landmarks_updated: 每帧landmark更新（用于隐私预览）。
        state_change_requested: 请求状态机变更灯效状态。
    """

    # Qt Signals
    gesture_detected = Signal(object)  # RecognitionResult
    landmarks_updated = Signal(object, object, object, object)  # hand_lm, face_lm, gesture, frame
    state_change_requested = Signal(LightState)
    recording_stop_requested = Signal()  # 请求停止录音（手部丢失）

    def __init__(
        self,
        config_manager: ConfigManager,
        image_processor: ImageProcessor,
    ) -> None:
        """初始化识别引擎。

        Args:
            config_manager: 配置管理器。
            image_processor: 图像预处理器。
        """
        if _HAS_QT:
            super().__init__()

        self._config_manager = config_manager
        self._image_processor = image_processor

        # 初始化子识别器
        thresholds = config_manager.get_thresholds()
        self._hand_classifier = HandClassifier(thresholds=thresholds)

        eyebrow_threshold = config_manager.get(
            "face_expression.eyebrow_raise_threshold", 1.5
        )
        update_interval = config_manager.get(
            "face_expression.baseline_update_interval_s", 300
        )
        self._face_recognizer = FaceExpressionRecognizer(
            eyebrow_threshold=eyebrow_threshold,
            update_interval=update_interval,
        )

        self._phone_call_detector = PhoneCallDetector()

        validation_config = config_manager.get_validation_config()
        self._validator = GestureValidator(
            confirm_frames=validation_config.get("confirm_frames", 3),
            hold_durations=self._parse_hold_durations(
                validation_config.get("hold_durations", {})
            ),
            cooldown_ms=validation_config.get("cooldown_ms", 500),
            confidence_threshold=validation_config.get("confidence_threshold", 0.7),
        )

        # MediaPipe 模型
        self._hands_model = None
        self._face_model = None
        self._single_hand_mode = config_manager.get(
            "recognition.single_hand_mode", True
        )

        # 线程控制
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._camera_manager = None

        # 错误计数
        self._consecutive_errors = 0
        self._max_consecutive_errors = 10

        # 录音状态跟踪
        self._is_recording = False

        # 打电话手势状态跟踪（上升沿/下降沿 + 滞回 + 冷却）
        self._phone_call_active = False
        self._phone_call_consecutive = 0     # 连续检测帧数（进入确认用）
        self._phone_call_none_consecutive = 0  # 连续消失帧数（退出滞回用）
        self._phone_call_end_time = 0.0      # 上次结束时间（冷却用）
        self._phone_call_min_gap_s = 1.5     # 两次触发最小间隔（秒）
        self._phone_call_exit_frames = 5     # 连续5帧未检测才算退出（滞回）

        # 上次触发的手势（同一手势持续保持时只触发一次，手势变化后才允许下一次）
        self._last_triggered_gesture = GestureType.NONE

        # 人脸门控：最后看到人脸的时间
        self._face_last_seen = 0.0

        # 校准模式：屏蔽手势触发
        self._calibration_mode = False

        _logger.info("Recognition engine initialized")

    def _parse_hold_durations(self, hold_config: dict) -> dict:
        """解析保持时间配置。

        Args:
            hold_config: 保持时间配置字典 {gesture_name: ms}。

        Returns:
            {GestureType: ms} 字典。
        """
        result = {}
        for gesture_name, duration in hold_config.items():
            try:
                gesture = GestureType(gesture_name)
                result[gesture] = int(duration)
            except (ValueError, TypeError):
                pass
        return result

    def _init_mediapipe_models(self) -> bool:
        """初始化 MediaPipe Hands 和 FaceMesh 模型。

        Returns:
            True 如果初始化成功。
        """
        if not _HAS_MEDIAPIPE:
            _logger.error("MediaPipe not installed, cannot initialize models")
            return False

        try:
            self._hands_model = _mp_hands.Hands(
                static_image_mode=False,
                max_num_hands=1 if self._single_hand_mode else 2,
                min_detection_confidence=0.4,  # 降低阈值以支持低光照环境
                min_tracking_confidence=0.3,  # 降低跟踪阈值
                model_complexity=1,  # 使用高精度模型提高检测率
            )
            self._face_model = _mp_face_mesh.FaceMesh(
                static_image_mode=False,
                max_num_faces=1,
                refine_landmarks=False,
                min_detection_confidence=0.5,
                min_tracking_confidence=0.5,
            )
            _logger.info("MediaPipe models initialized")
            return True
        except Exception as e:
            _logger.error("MediaPipe model initialization failed: %s", e)
            return False

    def start(self, camera_manager) -> bool:
        """启动识别线程。

        Args:
            camera_manager: 摄像头管理器实例。

        Returns:
            True 如果启动成功。
        """
        if self._running:
            _logger.warning("Recognition thread already running")
            return True

        if not self._init_mediapipe_models():
            return False

        self._camera_manager = camera_manager
        self._running = True
        self._consecutive_errors = 0

        self._thread = threading.Thread(
            target=self._recognition_loop,
            name="RecognitionThread",
            daemon=True,
        )
        self._thread.start()
        _logger.info("Recognition thread started")
        return True

    def stop(self) -> None:
        """停止识别线程并释放资源。"""
        self._running = False
        if self._thread is not None and self._thread.is_alive():
            self._thread.join(timeout=3.0)
        self._thread = None

        if self._hands_model is not None:
            self._hands_model.close()
            self._hands_model = None

        if self._face_model is not None:
            self._face_model.close()
            self._face_model = None

        _logger.info("Recognition thread stopped, models released")

    def get_latest_result(self):
        """获取最新识别结果（供校准使用）。

        Returns:
            最新的 RecognitionResult，或 None。
        """
        return getattr(self, '_latest_result', None)

    def _recognition_loop(self) -> None:
        """识别主循环（在独立线程中运行）。

        从摄像头队列取帧 → 预处理 → MediaPipe推理 → 分类 → 验证 → 发射信号
        """
        _logger.debug("Recognition loop started")
        while self._running:
            if self._camera_manager is None:
                time.sleep(0.1)
                continue

            frame = self._camera_manager.get_frame_blocking(timeout=1.0)
            if frame is None:
                continue

            try:
                result = self.process_frame(frame)
                self._consecutive_errors = 0
                self._latest_result = result  # 保存最新结果供校准使用
                self._latest_frame = frame  # 保存最新帧供预览使用

                # 周期性日志（每30帧≈3秒，INFO级别，含门控和校准状态）
                self._frame_count = getattr(self, '_frame_count', 0) + 1
                if self._frame_count % 30 == 0:
                    face_gate_remaining = max(0, 2.0 - (time.monotonic() - self._face_last_seen))
                    _logger.info(
                        "Frame#%d: hand=%s face=%s gate=%s(%.1fs) gesture=%s conf=%.2f light=%s calib=%s",
                        self._frame_count,
                        result.hand_detected,
                        result.face_detected,
                        "on" if face_gate_remaining > 0 else "off",
                        face_gate_remaining,
                        result.gesture.value,
                        result.confidence,
                        result.light_condition.value,
                        "on" if getattr(self, '_calibration_mode', False) else "off",
                    )

                # 发射预览更新信号（含原始帧供预览显示）
                self.landmarks_updated.emit(
                    result.hand_landmarks,
                    result.face_landmarks,
                    result.gesture,
                    frame,
                )

                # 手势处理：打电话手势用上升沿/下降沿+滞回+冷却，其他手势用变化检测
                if result.gesture == GestureType.PHONE_CALL:
                    self._phone_call_none_consecutive = 0  # 重置消失计数

                    if not self._phone_call_active:
                        self._phone_call_consecutive += 1
                        # 进入确认：连续3帧检测到才触发上升沿
                        if self._phone_call_consecutive >= 3:
                            # 冷却检查：上次结束后1.5秒内不重复触发
                            gap = time.monotonic() - self._phone_call_end_time
                            if gap >= self._phone_call_min_gap_s:
                                self._phone_call_active = True
                                self._last_triggered_gesture = GestureType.PHONE_CALL
                                self._handle_confirmed_gesture(result)
                                _logger.info("Phone call gesture rising edge (%d consecutive frames, gap %.1fs)",
                                            self._phone_call_consecutive, gap)
                            else:
                                _logger.debug("Phone call gesture trigger blocked by cooldown (gap %.1fs < %.1fs)",
                                            gap, self._phone_call_min_gap_s)
                            self._phone_call_consecutive = 0
                else:
                    self._phone_call_consecutive = 0  # 重置进入计数

                    if self._phone_call_active:
                        # 退出滞回：连续N帧未检测才触发下降沿（防止检测抖动）
                        self._phone_call_none_consecutive += 1
                        if self._phone_call_none_consecutive >= self._phone_call_exit_frames:
                            self._phone_call_active = False
                            self._is_recording = False
                            self._last_triggered_gesture = GestureType.NONE
                            self._phone_call_end_time = time.monotonic()
                            self._phone_call_none_consecutive = 0
                            self.recording_stop_requested.emit()
                            _logger.info("Phone call gesture falling edge (absent for %d consecutive frames)", self._phone_call_exit_frames)
                    elif result.gesture != GestureType.NONE:
                        # 其他手势：仅在手势类型变化时触发（同一手势持续保持不重复）
                        if result.gesture != self._last_triggered_gesture:
                            self._last_triggered_gesture = result.gesture
                            self._handle_confirmed_gesture(result)
                    # 手真正离开画面时才重置
                    if not result.hand_detected:
                        self._last_triggered_gesture = GestureType.NONE
                        # 手离开时也重置打电话滞回计数
                        if not self._phone_call_active:
                            self._phone_call_none_consecutive = 0

            except Exception as e:
                self._consecutive_errors += 1
                import traceback
                if self._consecutive_errors <= 2:
                    _logger.error("Recognition processing exception (%d): %s\n%s", self._consecutive_errors, e, traceback.format_exc())
                else:
                    _logger.error("Recognition processing exception (%d): %s", self._consecutive_errors, e)
                if self._consecutive_errors >= self._max_consecutive_errors:
                    _logger.error("Consecutive error limit reached, pausing recognition")
                    self.state_change_requested.emit(LightState.ERROR)
                    time.sleep(2.0)
                    self._consecutive_errors = 0

        _logger.debug("Recognition loop ended")

    def process_frame(self, frame: np.ndarray) -> RecognitionResult:
        """处理单帧图像，返回识别结果。

        识别流程：
        1. 图像预处理
        2. 面部识别（优先，用于人脸门控）
        3. 手部识别（仅在人脸2s内可见时才进行手势分类）
        4. 打电话手势检测（需手+脸联合）
        5. 手势黑名单检查（防止相似手势误触发）
        6. 防误触验证

        人脸门控：检测到人脸后2s内允许手势触发，人脸消失2s后停止手势检测。
        校准模式：屏蔽手势触发，但仍采集landmark供校准UI使用。

        Args:
            frame: BGR格式的原始帧。

        Returns:
            RecognitionResult 识别结果。
        """
        timestamp = time.time()

        # 1. 图像预处理
        processed_frame, light_condition = self._image_processor.preprocess(frame)

        # 2. 面部识别（优先）
        face_landmarks, face_detected, face_count = self._process_face(processed_frame)

        # 人脸门控：更新最后看到人脸的时间
        if face_detected:
            self._face_last_seen = time.monotonic()

        # 检查人脸是否在2s内可见
        face_gating_active = (time.monotonic() - self._face_last_seen) <= 2.0

        # 多人检测：画面中出现第二个人时暂停手势识别
        multi_person_detected = face_count > 1

        # 计算人脸有效区域（以人脸为中心的圆形区域）
        self._valid_area = None  # (center_x, center_y, radius) 归一化坐标
        if face_detected and face_landmarks is not None and len(face_landmarks) > 454:
            import math
            nose = face_landmarks[1]
            left_ear = face_landmarks[234]
            right_ear = face_landmarks[454]
            face_center_x = float(nose[0])
            face_center_y = float(nose[1])
            face_width = math.sqrt(
                (float(right_ear[0]) - float(left_ear[0])) ** 2 +
                (float(right_ear[1]) - float(left_ear[1])) ** 2
            )
            valid_radius = face_width * 1.625  # 人脸宽度的1.625倍（原1.25+30%）
            self._valid_area = (face_center_x, face_center_y, valid_radius)

        # 3. 手部识别
        hand_landmarks, handedness, hand_confidence = self._process_hands(
            processed_frame
        )

        # 检测状态变化日志
        if hand_landmarks is not None and not getattr(self, '_prev_hand', False):
            _logger.info("Hand detected! handedness=%s, confidence=%.2f", handedness, hand_confidence)
        if face_detected and not getattr(self, '_prev_face', False):
            _logger.info("Face detected!")
        self._prev_hand = hand_landmarks is not None
        self._prev_face = face_detected

        # 4. 手势分类（仅人脸门控开启时）
        gesture = GestureType.NONE
        confidence = 0.0
        hand_side = HandSide.RIGHT
        phone_call_detected = False

        # 校准模式：屏蔽手势触发，直接返回landmark
        if getattr(self, '_calibration_mode', False):
            result = RecognitionResult(
                gesture=GestureType.NONE,
                hand_side=hand_side,
                confidence=0.0,
                hand_landmarks=hand_landmarks,
                face_landmarks=face_landmarks,
                hand_detected=hand_landmarks is not None,
                face_detected=face_detected,
                phone_call_detected=False,
                eyebrow_raised=False,
                light_condition=light_condition,
                timestamp=timestamp,
            )
            return result

        # 多人检测：画面中出现第二个人时暂停手势识别
        if multi_person_detected:
            # 如果正在打电话录音，停止录音
            if self._phone_call_active:
                self._phone_call_active = False
                self._is_recording = False
                self._last_triggered_gesture = GestureType.NONE
                self.recording_stop_requested.emit()
                _logger.info("Multiple people detected: second person entered frame, stopping voice input")
            _logger.debug("Multiple people detected: %d people in frame, gesture recognition paused", face_count)
            result = RecognitionResult(
                gesture=GestureType.NONE,
                hand_side=hand_side,
                confidence=0.0,
                hand_landmarks=hand_landmarks,
                face_landmarks=face_landmarks,
                hand_detected=hand_landmarks is not None,
                face_detected=face_detected,
                phone_call_detected=False,
                eyebrow_raised=False,
                light_condition=light_condition,
                timestamp=timestamp,
            )
            return result

        # 人脸门控 + 有效区域检查
        hand_in_valid_area = False
        if hand_landmarks is not None and face_gating_active:
            # 检查手部是否在人脸有效圆形区域内
            if self._valid_area is not None:
                import math
                cx, cy, radius = self._valid_area
                wrist_x = float(hand_landmarks[0][0])
                wrist_y = float(hand_landmarks[0][1])
                palm_x = float(hand_landmarks[9][0])  # 手掌中心
                palm_y = float(hand_landmarks[9][1])
                # 取手腕和手掌中心距离的最小值
                dist_wrist = math.sqrt((wrist_x - cx) ** 2 + (wrist_y - cy) ** 2)
                dist_palm = math.sqrt((palm_x - cx) ** 2 + (palm_y - cy) ** 2)
                hand_in_valid_area = min(dist_wrist, dist_palm) <= radius
            else:
                hand_in_valid_area = True  # 无面部数据时不限制

        if hand_landmarks is not None and face_gating_active and hand_in_valid_area:
            try:
                gesture, confidence = self._hand_classifier.classify(
                    hand_landmarks, handedness
                )
                hand_side = HandSide.RIGHT  # 单手模式，不区分左右
            except Exception as e:
                _logger.debug("Gesture classification exception: %s", e)

            # 5. 手势黑名单检查（防止相似手势误触发）
            if gesture != GestureType.NONE:
                gesture, confidence = self._check_gesture_blacklist(
                    gesture, confidence, hand_landmarks
                )

        # 6. 打电话手势检测（纯手形识别，不需要面部）
        if hand_landmarks is not None:
            try:
                phone_call_detected, phone_confidence = self._phone_call_detector.detect(
                    hand_landmarks, face_landmarks, handedness
                )
                if phone_call_detected:
                    gesture = GestureType.PHONE_CALL
                    confidence = phone_confidence
            except Exception as e:
                import traceback
                _logger.error("Phone call detection exception: %s\n%s", e, traceback.format_exc())

        # 7. 防误触验证
        # 打电话手势跳过验证器（验证器的冷却机制会导致PHONE_CALL/NONE闪烁，
        # 与上升沿/下降沿逻辑冲突）。打电话手势用独立的上升沿/下降沿控制。
        if gesture == GestureType.PHONE_CALL:
            confirmed = True
        else:
            confirmed = self._validator.validate(gesture, confidence)

        result = RecognitionResult(
            gesture=gesture if confirmed else GestureType.NONE,
            hand_side=hand_side,
            confidence=confidence,
            hand_landmarks=hand_landmarks,
            face_landmarks=face_landmarks,
            hand_detected=hand_landmarks is not None,
            face_detected=face_detected,
            phone_call_detected=phone_call_detected,
            eyebrow_raised=False,
            light_condition=light_condition,
            timestamp=timestamp,
        )

        return result

    def _check_gesture_blacklist(
        self, gesture: GestureType, confidence: float, hand_landmarks: list
    ) -> tuple:
        """手势黑名单检查：防止相似手势互相误触发。

        对每个识别到的手势，检查其关键特征是否与容易混淆的手势重叠。
        如果特征差异不足以区分，降低置信度或拒绝识别。

        容易混淆的手势对：
        - PINCH ↔ OK（两者拇指+食指成圈，靠其余手指伸直/弯曲区分）
        - SCISSOR ↔ OPEN_PALM（剪刀手有2指伸直）

        Args:
            gesture: 识别到的手势。
            confidence: 原始置信度。
            hand_landmarks: 21点landmark。

        Returns:
            (可能修正后的手势, 可能修正后的置信度)
        """
        try:
            def get_xy(idx):
                lm = hand_landmarks[idx]
                if isinstance(lm, dict):
                    return float(lm["x"]), float(lm["y"])
                return float(lm[0]), float(lm[1])

            import math
            wrist_x, wrist_y = get_xy(0)

            # 计算各指尖到手腕距离
            tip_dists = {}
            for name, idx in [("thumb", 4), ("index", 8), ("middle", 12), ("ring", 16), ("pinky", 20)]:
                tx, ty = get_xy(idx)
                tip_dists[name] = math.sqrt((tx - wrist_x) ** 2 + (ty - wrist_y) ** 2)

            # 拇指尖与食指尖距离
            thumb_x, thumb_y = get_xy(4)
            index_x, index_y = get_xy(8)
            thumb_index_dist = math.sqrt((thumb_x - index_x) ** 2 + (thumb_y - index_y) ** 2)

            # 黑名单规则：不符合关键特征的手势直接拒绝（confidence=0）
            if gesture == GestureType.PINCH:
                # 捏合时拇指和食指尖必须很近
                if thumb_index_dist > 0.08:
                    _logger.debug("Blacklist: PINCH rejected (thumb-index distance=%.3f>0.08)", thumb_index_dist)
                    return GestureType.NONE, 0.0

            elif gesture == GestureType.OK:
                # OK手势：中指必须明确伸直（与PINCH区分的关键特征）
                middle_tip_dist = tip_dists.get("middle", 0)
                middle_mcp_x, middle_mcp_y = get_xy(9)
                middle_mcp_dist = math.sqrt((middle_mcp_x - wrist_x) ** 2 + (middle_mcp_y - wrist_y) ** 2)
                middle_ratio = middle_tip_dist / max(middle_mcp_dist, 0.001)
                if middle_ratio < 1.3:  # 中指伸直时指尖距离应明显大于MCP距离
                    _logger.debug("Blacklist: OK rejected (middle finger not extended, ratio=%.2f)", middle_ratio)
                    return GestureType.NONE, 0.0

            elif gesture == GestureType.SCISSOR:
                # 剪刀手时无名指和小指必须弯曲
                ring_dist = tip_dists["ring"]
                pinky_dist = tip_dists["pinky"]
                index_dist = tip_dists["index"]
                middle_dist = tip_dists["middle"]
                avg_extended = (index_dist + middle_dist) / 2
                avg_curled = (ring_dist + pinky_dist) / 2
                if avg_extended < avg_curled * 1.3:
                    _logger.debug("Blacklist: SCISSOR rejected (index/middle fingers not extended enough)")
                    return GestureType.NONE, 0.0

            elif gesture == GestureType.OPEN_PALM:
                # 张开手掌时所有五指必须伸直
                for name in ["thumb", "index", "middle", "ring", "pinky"]:
                    if tip_dists[name] < 0.15:
                        _logger.debug("Blacklist: OPEN_PALM rejected (%s not extended)", name)
                        return GestureType.NONE, 0.0

            return gesture, confidence

        except Exception as e:
            _logger.debug("Blacklist check exception: %s", e)
            return gesture, confidence

    def set_calibration_mode(self, enabled: bool) -> None:
        """设置校准模式。

        校准模式下，识别引擎仍采集landmark并发射预览信号，
        但不会进行手势验证和触发（屏蔽识别输入）。

        Args:
            enabled: True 启用校准模式，False 恢复正常识别。
        """
        self._calibration_mode = enabled
        if enabled:
            # 重置验证器状态，避免校准期间残留的帧历史影响
            self._validator.reset()
        _logger.info("Calibration mode: %s", "enabled (recognition suppressed)" if enabled else "disabled (recognition restored)")

    def _process_hands(self, frame: np.ndarray):
        """处理手部识别。

        Args:
            frame: BGR格式的预处理帧。

        Returns:
            元组 (landmarks列表, handedness字符串, confidence浮点数)。
            未检测到手时返回 (None, "Right", 0.0)。
        """
        if self._hands_model is None:
            return None, "Right", 0.0

        rgb_frame = _np_bgr_to_rgb(frame)
        results = self._hands_model.process(rgb_frame)

        if results.multi_hand_landmarks is None or len(results.multi_hand_landmarks) == 0:
            return None, "Right", 0.0

        # 单手模式：仅取第一只手
        hand_landmarks = results.multi_hand_landmarks[0]
        landmarks = [
            (lm.x, lm.y, lm.z)
            for lm in hand_landmarks.landmark
        ]

        # 获取手部侧别
        handedness = "Right"
        if results.multi_handedness and len(results.multi_handedness) > 0:
            handedness = results.multi_handedness[0].classification[0].label

        confidence = 0.9
        if results.multi_handedness and len(results.multi_handedness) > 0:
            confidence = results.multi_handedness[0].classification[0].score

        return landmarks, handedness, confidence

    def _process_face(self, frame: np.ndarray):
        """处理面部识别。

        Args:
            frame: BGR格式的预处理帧。

        Returns:
            元组 (landmarks列表, 是否检测到面部, 人脸数量)。
        """
        if self._face_model is None:
            return None, False, 0

        rgb_frame = _np_bgr_to_rgb(frame)
        results = self._face_model.process(rgb_frame)

        if results.multi_face_landmarks is None or len(results.multi_face_landmarks) == 0:
            return None, False, 0

        face_count = len(results.multi_face_landmarks)
        face_landmarks = results.multi_face_landmarks[0]
        landmarks = [
            (lm.x, lm.y, lm.z)
            for lm in face_landmarks.landmark
        ]

        return landmarks, True, face_count

    def _handle_confirmed_gesture(self, result: RecognitionResult) -> None:
        """处理已确认的手势。"""
        _logger.info("Gesture confirmed, emitting gesture_detected signal: %s (conf=%.2f)", result.gesture.value, result.confidence)
        self.gesture_detected.emit(result)

        # 持续适配：记录成功识别的landmark数据
        if result.hand_landmarks is not None and result.gesture != GestureType.NONE:
            calibrator = getattr(self, '_calibrator', None)
            if calibrator is not None:
                try:
                    calibrator.record_success(result.gesture, result.hand_landmarks)
                except Exception as e:
                    _logger.debug("Failed to record continuous adaptation: %s", e)

        # 请求状态变更
        if result.gesture == GestureType.PHONE_CALL:
            self._is_recording = True
            self.state_change_requested.emit(LightState.RECORDING)
        elif result.gesture in (GestureType.PINCH, GestureType.RAISE_EYEBROW):
            # 模式切换手势 → 状态由状态机处理
            pass
        else:
            self.state_change_requested.emit(LightState.TRIGGERED)

    def set_calibrator(self, calibrator) -> None:
        """设置校准器实例（用于持续适配）。

        Args:
            calibrator: Calibrator 实例。
        """
        self._calibrator = calibrator

        # D2修复：注册适配回调，适配完成后自动更新分类器阈值
        def on_thresholds_adapted(new_thresholds):
            if hasattr(self, '_hand_classifier') and self._hand_classifier:
                self._hand_classifier.update_thresholds(new_thresholds)

        calibrator._adapt_callback = on_thresholds_adapted
        _logger.info("Calibrator set, continuous adaptation enabled (with auto-push)")

    def update_config(self, config: dict) -> None:
        """热更新配置。

        Args:
            config: 新的配置字典。
        """
        # 更新阈值
        thresholds = config.get("recognition", {}).get("thresholds", {})
        if thresholds:
            self._hand_classifier.update_thresholds(thresholds)

        # 更新防误触配置
        validation = config.get("validation", {})
        if validation:
            self._validator.update_config(validation)

        # 更新单手模式
        self._single_hand_mode = config.get("recognition", {}).get(
            "single_hand_mode", True
        )

        _logger.info("Recognition engine config hot-updated")

    def update_thresholds(self, thresholds: dict) -> None:
        """更新手势分类器阈值（供校准器调用）。

        Args:
            thresholds: 新的阈值字典。
        """
        self._hand_classifier.update_thresholds(thresholds)

    def get_hand_classifier(self) -> HandClassifier:
        """返回手势分类器实例（供新手引导使用）。"""
        return self._hand_classifier

    def get_validator(self) -> GestureValidator:
        """返回防误触验证器实例。"""
        return self._validator


def _np_bgr_to_rgb(frame: np.ndarray) -> np.ndarray:
    """将BGR帧转换为RGB格式。

    Args:
        frame: BGR格式的帧。

    Returns:
        RGB格式的帧。
    """
    import cv2
    return cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
