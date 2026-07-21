import os
import time
import threading
import concurrent.futures

import requests

from src.utils.config import Config
from src.core.m3u8_parser import M3U8Parser
from src.core.merger import Merger


class Downloader:
    """下载器，用于并发下载m3u8的ts片段。"""

    def __init__(self, max_workers=None):
        """初始化下载器。

        Args:
            max_workers: 最大并发下载数，默认使用Config.DEFAULT_MAX_WORKERS
        """
        self.max_workers = max_workers or Config.DEFAULT_MAX_WORKERS
        self.timeout = Config.DEFAULT_TIMEOUT
        self.retries = Config.DEFAULT_RETRIES
        self.headers = Config.DEFAULT_HEADERS.copy()

        # m3u8 解析器与合并器
        self.parser = M3U8Parser()
        self.merger = Merger()

        # 复用连接的请求会话
        self.session = requests.Session()
        self.session.headers.update(self.headers)

        # 控制事件：_pause_event 为 set 时表示可继续下载，clear 时为暂停
        self._pause_event = threading.Event()
        self._pause_event.set()
        # _cancel_event 为 set 时表示请求取消下载
        self._cancel_event = threading.Event()

        # 信号回调接口（由外部赋值）
        self.on_progress = None   # on_progress(downloaded: int, total: int, speed: float)
        self.on_status = None     # on_status(status: str)

        # 下载统计（受 _lock 保护）
        self._lock = threading.Lock()
        self._downloaded_count = 0
        self._total_count = 0
        self._start_time = 0.0

    def download(self, m3u8_url, output_dir, progress_callback=None):
        """下载m3u8视频：解析→并发下载ts片段→合并为mp4。

        Args:
            m3u8_url: m3u8 播放列表URL
            output_dir: 下载保存目录
            progress_callback: 进度回调 (downloaded, total, speed)

        Returns:
            str: 合并后的视频文件路径；失败返回空字符串
        """
        # 重置控制状态，开启新一轮下载
        self._pause_event.set()
        self._cancel_event.clear()
        self._emit_status("downloading")

        # 解析m3u8获取ts片段列表
        try:
            playlist = self.parser.parse(m3u8_url)
        except Exception:
            self._emit_status("error")
            return ""

        segments = playlist.get("segments", [])
        if not segments:
            self._emit_status("error")
            return ""

        # 准备输出目录
        os.makedirs(output_dir, exist_ok=True)

        self._total_count = len(segments)
        self._downloaded_count = 0
        self._start_time = time.time()

        # 构造每个片段的本地保存路径
        ts_files = [
            os.path.join(output_dir, f"segment_{idx:05d}.ts")
            for idx in range(len(segments))
        ]

        # 并发下载所有ts片段
        with concurrent.futures.ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            futures = [
                executor.submit(self._download_segment_task, url, path, progress_callback)
                for url, path in zip(segments, ts_files)
            ]
            try:
                for future in concurrent.futures.as_completed(futures):
                    if self._cancel_event.is_set():
                        # 取消：尽量取消尚未开始的任务
                        for fut in futures:
                            fut.cancel()
                        break
                    # 触发任务内可能抛出的异常
                    future.result()
            except KeyboardInterrupt:
                self._cancel_event.set()

        # 取消则终止流程
        if self._cancel_event.is_set():
            self._emit_status("error")
            return ""

        # 校验所有片段均已就位
        if any(not os.path.exists(path) for path in ts_files):
            self._emit_status("error")
            return ""

        # 调用Merger合并ts片段为mp4
        output_path = os.path.join(output_dir, "output.mp4")
        try:
            success = self.merger.merge(ts_files, output_path)
        except Exception:
            success = False

        if not success:
            self._emit_status("error")
            return ""

        self._emit_status("completed")
        return output_path

    def _download_segment_task(self, url, filepath, progress_callback):
        """线程池任务：等待暂停/检查取消，下载单个片段并汇报进度。"""
        # 暂停时阻塞，直到 resume() 唤醒
        self._pause_event.wait()
        if self._cancel_event.is_set():
            return False

        success = self.download_segment(url, filepath, retry=self.retries)

        # 更新统计并触发进度回调
        with self._lock:
            self._downloaded_count += 1
            downloaded = self._downloaded_count
            total = self._total_count
            elapsed = time.time() - self._start_time
        speed = downloaded / elapsed if elapsed > 0 else 0.0

        if progress_callback is not None:
            try:
                progress_callback(downloaded, total, speed)
            except Exception:
                pass
        if self.on_progress is not None:
            try:
                self.on_progress(downloaded, total, speed)
            except Exception:
                pass
        return success

    def download_segment(self, url, filepath, retry=3):
        """下载单个ts片段到指定路径，支持重试与断点续传。

        Args:
            url: ts 片段的URL
            filepath: 本地保存路径
            retry: 失败重试次数

        Returns:
            bool: 下载是否成功
        """
        # 断点续传：已存在的非空片段文件直接跳过
        if os.path.exists(filepath) and os.path.getsize(filepath) > 0:
            return True

        attempts = max(1, retry + 1)
        for attempt in range(attempts):
            if self._cancel_event.is_set():
                return False
            # 暂停时阻塞
            self._pause_event.wait()
            try:
                response = self.session.get(url, timeout=self.timeout, stream=True)
                response.raise_for_status()
                with open(filepath, "wb") as f:
                    for chunk in response.iter_content(chunk_size=64 * 1024):
                        if self._cancel_event.is_set():
                            return False
                        self._pause_event.wait()
                        if chunk:
                            f.write(chunk)
                return True
            except (requests.RequestException, OSError):
                # 失败后短暂退避并重试
                time.sleep(0.5)
                continue
        return False

    def pause(self):
        """暂停下载。"""
        self._pause_event.clear()
        self._emit_status("paused")

    def resume(self):
        """继续下载。"""
        self._pause_event.set()
        self._emit_status("downloading")

    def cancel(self):
        """取消下载。"""
        self._cancel_event.set()
        # 解除可能的暂停阻塞，让等待中的线程能检测到取消并退出
        self._pause_event.set()

    def _emit_status(self, status):
        """触发状态回调。"""
        if self.on_status is not None:
            try:
                self.on_status(status)
            except Exception:
                pass
