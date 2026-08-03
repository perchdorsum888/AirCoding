"""摄像头采集管理模块。

独立线程运行 cv2.VideoCapture，按10fps节流采集帧，
帧队列 maxsize=2（满则丢弃最旧帧），支持摄像头异常检测与自动恢复。
支持摄像头被其他程序占用时自动释放，其他程序释放后自动恢复。
"""

import queue
import threading
import time
from typing import Optional, Callable

import cv2
import numpy as np

from src.utils.logger import get_logger

_logger = get_logger("CameraManager")

# 常量
DEFAULT_FPS = 10
MAX_FRAME_QUEUE_SIZE = 2
CAMERA_RETRY_INTERVAL_S = 2.0
MAX_CAMERA_RETRIES = 5
FRAME_TIMEOUT_S = 1.0
PAUSE_RETRY_INTERVAL_S = 3.0  # 摄像头被占用时的重试间隔
MAX_PAUSE_RETRIES = 100       # 摄像头被占用时的最大重试次数（~5分钟）


class CameraError(Exception):
    """摄像头异常。"""
    pass


class CameraManager:
    """摄像头采集管理器。

    在独立线程中运行 cv2.VideoCapture，按指定帧率采集视频帧。
    支持摄像头被其他程序占用时自动释放并持续重试，其他程序释放后自动恢复。

    Attributes:
        _device_index: 摄像头设备索引。
        _fps: 目标采集帧率。
        _frame_queue: 帧队列（线程安全）。
        _running: 采集线程运行标志。
        _cap: cv2.VideoCapture 实例。
        _paused: 摄像头是否被暂停（被其他程序占用）。
        _pause_callback: 摄像头被暂停时的回调函数。
        _resume_callback: 摄像头恢复时的回调函数。
    """

    def __init__(
        self,
        config_manager=None,
        device_index: int = 0,
        fps: int = DEFAULT_FPS,
    ) -> None:
        if config_manager is not None:
            device_index = config_manager.get("recognition.camera_index", device_index)
            fps = config_manager.get("recognition.fps", fps)
            self._width = config_manager.get("recognition.resolution.width", 640)
            self._height = config_manager.get("recognition.resolution.height", 480)
        else:
            self._width = 640
            self._height = 480

        self._device_index = device_index
        self._fps = fps
        self._frame_interval = 1.0 / fps
        self._frame_queue: queue.Queue = queue.Queue(maxsize=MAX_FRAME_QUEUE_SIZE)
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._cap: Optional[cv2.VideoCapture] = None
        self._retry_count = 0
        self._lock = threading.Lock()
        self._paused = False
        self._pause_count = 0
        self._pause_callback: Optional[Callable] = None
        self._resume_callback: Optional[Callable] = None

    def set_callbacks(self, pause_callback: Callable = None, resume_callback: Callable = None) -> None:
        """设置摄像头暂停/恢复的回调函数。

        Args:
            pause_callback: 摄像头被其他程序占用时的回调。
            resume_callback: 摄像头恢复时的回调。
        """
        self._pause_callback = pause_callback
        self._resume_callback = resume_callback

    def is_paused(self) -> bool:
        """检查摄像头是否被暂停（被其他程序占用）。"""
        return self._paused

    def start(self) -> bool:
        """启动摄像头采集线程。"""
        if self._running:
            _logger.warning("Camera capture thread already running")
            return True

        if not self._open_camera():
            _logger.error("Camera initialization failed")
            return False

        self._running = True
        self._retry_count = 0
        self._thread = threading.Thread(
            target=self._capture_loop,
            name="CameraThread",
            daemon=True,
        )
        self._thread.start()
        _logger.info(
            "Camera capture thread started: device=%d, fps=%dfps, resolution=%dx%d",
            self._device_index, self._fps, self._width, self._height,
        )
        return True

    def stop(self) -> None:
        """停止摄像头采集线程并释放资源。"""
        self._running = False
        if self._thread is not None and self._thread.is_alive():
            self._thread.join(timeout=3.0)
        self._thread = None

        with self._lock:
            if self._cap is not None:
                self._cap.release()
                self._cap = None

        while not self._frame_queue.empty():
            try:
                self._frame_queue.get_nowait()
            except queue.Empty:
                break

        _logger.info("Camera capture thread stopped")

    def get_frame(self) -> Optional[np.ndarray]:
        """从帧队列获取最新帧（非阻塞）。"""
        try:
            return self._frame_queue.get_nowait()
        except queue.Empty:
            return None

    def get_frame_blocking(self, timeout: float = FRAME_TIMEOUT_S) -> Optional[np.ndarray]:
        """从帧队列获取帧（阻塞，带超时）。"""
        try:
            return self._frame_queue.get(timeout=timeout)
        except queue.Empty:
            return None

    def is_available(self) -> bool:
        """检查摄像头是否可用。"""
        with self._lock:
            return self._cap is not None and self._cap.isOpened()

    def _open_camera(self) -> bool:
        """打开摄像头设备（优化启动速度）。

        优化点：
        1. 直接用MSMF（跳过DSHOW，此系统不支持且浪费625ms）
        2. 不设BUFFERSIZE（MSMF不支持，设置会导致重新协商媒体格式13s）
        3. 分辨率在open后只设一次，避免重复协商
        """
        try:
            # 直接用MSMF后端（DSHOW在此系统不可用，跳过避免浪费625ms）
            self._cap = cv2.VideoCapture(self._device_index, cv2.CAP_MSMF)
            if not self._cap.isOpened():
                # 回退到默认后端
                self._cap = cv2.VideoCapture(self._device_index)
                if not self._cap.isOpened():
                    _logger.error("Failed to open camera device %d", self._device_index)
                    return False

            # 只设分辨率（不设BUFFERSIZE，MSMF不支持且会导致13s重新协商）
            # 使用属性设置，某些摄像头会立即应用
            self._cap.set(cv2.CAP_PROP_FRAME_WIDTH, self._width)
            self._cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self._height)

            _logger.info("Camera opened: %dx%d",
                        int(self._cap.get(cv2.CAP_PROP_FRAME_WIDTH)),
                        int(self._cap.get(cv2.CAP_PROP_FRAME_HEIGHT)))
            return True
        except Exception as e:
            _logger.error("Camera open exception: %s", e)
            self._cap = None
            return False

    def _capture_loop(self) -> None:
        """摄像头采集主循环。

        当摄像头读取失败时，判断是被其他程序占用还是临时错误：
        - 临时错误：重试5次后放弃
        - 被其他程序占用：释放摄像头，持续重试直到恢复
        """
        _logger.debug("Capture loop started")
        while self._running:
            loop_start = time.monotonic()

            with self._lock:
                cap = self._cap

            if cap is None or not cap.isOpened():
                if not self._handle_camera_error():
                    break
                continue

            ret, frame = cap.read()
            if not ret or frame is None:
                _logger.warning("Frame read failed")
                # 帧读取失败可能是其他程序占用了摄像头
                if not self._handle_camera_error():
                    break
                continue

            self._retry_count = 0
            self._put_frame(frame)

            elapsed = time.monotonic() - loop_start
            sleep_time = self._frame_interval - elapsed
            if sleep_time > 0:
                time.sleep(sleep_time)

        _logger.debug("Capture loop ended")

    def _put_frame(self, frame: np.ndarray) -> None:
        """将帧放入队列，队列满时丢弃最旧帧。"""
        while True:
            try:
                self._frame_queue.put_nowait(frame)
                break
            except queue.Full:
                try:
                    discarded = self._frame_queue.get_nowait()
                    del discarded
                except queue.Empty:
                    break

    def _handle_camera_error(self) -> bool:
        """处理摄像头错误。

        区分两种情况：
        1. 临时错误（偶尔丢帧）：重试5次
        2. 摄像头被其他程序占用：释放摄像头，持续重试直到恢复

        Returns:
            True 如果恢复成功可继续采集，False 如果超过最大重试次数。
        """
        self._retry_count += 1

        if self._retry_count <= MAX_CAMERA_RETRIES:
            # 临时错误：快速重试
            _logger.warning("Camera error, retrying (%d/%d)", self._retry_count, MAX_CAMERA_RETRIES)
            with self._lock:
                if self._cap is not None:
                    self._cap.release()
                    self._cap = None
            time.sleep(CAMERA_RETRY_INTERVAL_S)
            if self._open_camera():
                _logger.info("Camera reconnected successfully")
                return True
            return self._retry_count < MAX_CAMERA_RETRIES

        # 超过快速重试次数 → 判定为被其他程序占用
        if not self._paused:
            self._paused = True
            self._pause_count = 0
            _logger.info("Camera may be in use by another program, releasing and waiting for recovery")
            if self._pause_callback:
                try:
                    self._pause_callback()
                except Exception:
                    pass

        # 释放摄像头
        with self._lock:
            if self._cap is not None:
                self._cap.release()
                self._cap = None

        # 持续重试直到恢复或超过最大暂停重试次数
        self._pause_count += 1
        if self._pause_count > MAX_PAUSE_RETRIES:
            _logger.error("Camera occupied after %d retries, giving up", MAX_PAUSE_RETRIES)
            self._running = False
            return False

        if self._pause_count % 10 == 1:  # 每10次重试记录一次日志
            _logger.info("Waiting for camera release... (retry #%d)", self._pause_count)

        time.sleep(PAUSE_RETRY_INTERVAL_S)

        if self._open_camera():
            # 摄像头恢复！
            self._paused = False
            self._retry_count = 0
            self._pause_count = 0
            _logger.info("Camera recovered (released by another program)")
            if self._resume_callback:
                try:
                    self._resume_callback()
                except Exception:
                    pass
            return True

        return True  # 继续循环重试

    @property
    def fps(self) -> int:
        return self._fps

    @property
    def frame_queue_size(self) -> int:
        return self._frame_queue.qsize()
