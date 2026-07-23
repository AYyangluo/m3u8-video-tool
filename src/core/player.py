import os
import threading
import time

from src.utils.config import Config
from src.utils.logger import get_logger

logger = get_logger()

# ffpyplayer 是可选依赖，未安装时给出友好提示而非直接崩溃
try:
    from ffpyplayer.player import MediaPlayer
    from ffpyplayer.tools import set_log_callback
    FFPYPLAYER_AVAILABLE = True
    FFPYPLAYER_IMPORT_ERROR = None
except ImportError as e:  # pragma: no cover - 依赖环境相关
    FFPYPLAYER_AVAILABLE = False
    FFPYPLAYER_IMPORT_ERROR = str(e)
    MediaPlayer = None
    set_log_callback = None


def _ff_log_callback(level, msg):
    """ffpyplayer/ffmpeg 内部日志回调，转发到统一日志系统。

    Args:
        level: 日志级别字符串，如 'error'、'warning'、'info'、'debug'
        msg: 日志内容
    """
    msg = (msg or "").rstrip()
    if not msg:
        return
    level = (level or "").lower()
    if level == "error":
        logger.error(f"[ffpyplayer] {msg}")
    elif level == "warning":
        logger.warning(f"[ffpyplayer] {msg}")
    else:
        logger.debug(f"[ffpyplayer:{level}] {msg}")


# 注册 ffpyplayer 内部日志回调，捕获 ffmpeg 层错误（如解码失败、网络断开）
if FFPYPLAYER_AVAILABLE and set_log_callback is not None:
    try:
        set_log_callback(_ff_log_callback)
    except Exception:  # pragma: no cover - 回调注册失败不影响主流程
        logger.exception("设置 ffpyplayer 日志回调失败")


class M3U8Player:
    """基于ffpyplayer的m3u8播放器核心类。

    封装ffpyplayer的MediaPlayer，提供m3u8链接的播放、暂停、继续、停止、
    跳转、速度/音量控制等功能。视频帧通过独立线程读取并以回调方式
    交给上层（PlayerWidget）渲染到QWidget。

    缓存大小与缓存目录通过构造参数传入，用于在播放时控制ffpyplayer的
    缓存行为。调用 update_cache_config() 可更新配置，但需重新创建
    播放器（重新调用play）才生效。
    """

    def __init__(self, wid, cache_size=None, cache_dir=None):
        """初始化播放器核心。

        Args:
            wid: PyQt渲染窗口的原生窗口ID（保留备用，当前采用手动帧渲染）。
            cache_size: 缓存大小（字节），默认使用Config.DEFAULT_CACHE_SIZE。
            cache_dir: 缓存目录，默认使用Config.DEFAULT_CACHE_DIR。
        """
        self._wid = wid
        # 缓存配置：显式传入则使用传入值，否则回退到Config默认值
        self._cache_size = (
            cache_size if cache_size is not None else Config.DEFAULT_CACHE_SIZE
        )
        self._cache_dir = cache_dir if cache_dir is not None else Config.DEFAULT_CACHE_DIR

        # ffpyplayer 播放器实例
        self._player = None
        # 当前播放状态
        self._state = "stopped"
        # 帧读取线程
        self._frame_thread = None
        # 帧读取线程运行标志
        self._running = False

        # ===== 回调接口（由外部赋值，在帧线程中被调用） =====
        # on_frame(data: bytes, width: int, height: int)
        self.on_frame = None
        # on_state_changed(state: str)
        self.on_state_changed = None
        # on_error(msg: str)
        self.on_error = None
        # on_eof()
        self.on_eof = None

    @staticmethod
    def is_available():
        """判断ffpyplayer是否可用。"""
        return FFPYPLAYER_AVAILABLE

    @staticmethod
    def get_import_error():
        """获取ffpyplayer导入失败的错误信息。"""
        return FFPYPLAYER_IMPORT_ERROR

    def play(self, url):
        """播放指定m3u8链接。

        使用ffpyplayer的MediaPlayer加载url，传递缓存配置与fflags参数，
        并启动独立线程读取视频帧。

        Args:
            url: m3u8播放链接
        """
        logger.info(
            f"开始播放: url={url}, cache_size={self._cache_size}, "
            f"cache_dir={self._cache_dir}"
        )
        # ffpyplayer未安装时直接报错，避免后续崩溃
        if not FFPYPLAYER_AVAILABLE:
            msg = f"ffpyplayer未安装: {FFPYPLAYER_IMPORT_ERROR or '未知错误'}"
            logger.error(msg)
            self._notify_error(msg)
            return

        # 停止当前播放，清理旧播放器实例
        self.stop()

        try:
            # 确保缓存目录存在
            if self._cache_dir:
                os.makedirs(self._cache_dir, exist_ok=True)

            # 构造ff_opts：缓存大小、缓存目录、低延迟标志
            ff_opts = {
                "cache_size": self._cache_size,
                "cache_dir": self._cache_dir,
                "fflags": "nobuffer",
            }

            logger.debug(f"创建 MediaPlayer: ff_opts={ff_opts}")
            self._player = MediaPlayer(
                url,
                loglevel="info",
                ff_opts=ff_opts,
            )
            logger.info("MediaPlayer 创建成功")
            self._state = "playing"
            self._notify_state()

            # 启动帧读取线程
            self._running = True
            self._frame_thread = threading.Thread(
                target=self._read_frames, daemon=True
            )
            self._frame_thread.start()
        except Exception as e:
            logger.exception(f"播放失败: url={url}")
            self._player = None
            self._notify_error(f"播放失败: {e}")

    def _read_frames(self):
        """独立线程：循环读取ffpyplayer的视频帧并通过回调返回。

        通过get_frame()获取帧：
        - val == 'eof'：播放结束
        - val is None：缓冲中，无可用帧
        - val 为 (img, pts)：有帧可渲染
        """
        logger.info("帧读取线程启动")
        while self._running and self._player is not None:
            try:
                frame, val = self._player.get_frame()
            except Exception as e:
                logger.exception("get_frame 抛出异常")
                self._notify_error(f"读取帧失败: {e}")
                break

            # 播放结束
            if val == "eof":
                logger.info("播放结束(eof)")
                self._state = "ended"
                self._notify_state()
                if self.on_eof:
                    try:
                        self.on_eof()
                    except Exception:
                        logger.exception("on_eof 回调异常")
                break

            # 缓冲中，短暂等待后重试
            if val is None:
                time.sleep(0.01)
                continue

            # val 为 (img, pts) 元组
            try:
                img, pts = val
            except (TypeError, ValueError):
                time.sleep(0.01)
                continue

            # 将帧转换为RGB字节数据并回调
            data, width, height = self._frame_to_bytes(img)
            if data is not None and self.on_frame is not None:
                try:
                    self.on_frame(data, width, height)
                except Exception:
                    logger.exception("on_frame 回调异常")
        logger.info("帧读取线程退出")

    def _frame_to_bytes(self, img):
        """将ffpyplayer返回的帧对象转换为RGB字节数据。

        ffpyplayer的get_frame()返回的img通常是PIL.Image对象，
        也可能是numpy数组，这里统一转换为RGB字节。

        Args:
            img: ffpyplayer帧对象

        Returns:
            tuple: (data, width, height)；转换失败返回 (None, 0, 0)
        """
        try:
            # PIL Image：转RGB后导出字节
            if hasattr(img, "convert") and hasattr(img, "tobytes"):
                rgb = img.convert("RGB")
                width, height = rgb.size
                return rgb.tobytes(), width, height
            # numpy数组：直接导出字节
            if hasattr(img, "shape") and hasattr(img, "tobytes"):
                height, width = img.shape[:2]
                return img.tobytes(), width, height
            return None, 0, 0
        except Exception:
            logger.exception("帧转换为字节失败")
            return None, 0, 0

    def pause(self):
        """暂停播放。"""
        if self._player is None:
            return
        try:
            self._player.set_pause(True)
            self._state = "paused"
            self._notify_state()
        except Exception as e:
            self._notify_error(f"暂停失败: {e}")

    def resume(self):
        """继续播放。"""
        if self._player is None:
            return
        try:
            self._player.set_pause(False)
            self._state = "playing"
            self._notify_state()
        except Exception as e:
            self._notify_error(f"继续播放失败: {e}")

    def stop(self):
        """停止播放并释放资源。"""
        # 先停止帧读取线程
        self._running = False
        if self._frame_thread is not None and self._frame_thread.is_alive():
            self._frame_thread.join(timeout=1.0)
        self._frame_thread = None

        # 关闭并释放播放器实例
        if self._player is not None:
            try:
                self._player.close()
            except Exception:
                logger.exception("关闭播放器实例失败")
            self._player = None

        # 更新状态
        if self._state != "stopped":
            self._state = "stopped"
            self._notify_state()

    def seek(self, position):
        """跳转到指定播放位置。

        Args:
            position: 目标位置（秒）
        """
        if self._player is None:
            return
        try:
            self._player.seek(float(position))
        except Exception as e:
            self._notify_error(f"跳转失败: {e}")

    def set_rate(self, rate):
        """设置播放速度（0.5-2.0）。

        Args:
            rate: 播放速度倍率
        """
        if self._player is None:
            return
        try:
            self._player.set_rate(float(rate))
        except Exception as e:
            self._notify_error(f"设置速度失败: {e}")

    def set_volume(self, volume):
        """设置音量（0.0-1.0）。

        Args:
            volume: 音量，范围0.0到1.0
        """
        if self._player is None:
            return
        try:
            self._player.set_volume(float(volume))
        except Exception as e:
            self._notify_error(f"设置音量失败: {e}")

    def get_position(self):
        """获取当前播放位置（秒）。

        Returns:
            float: 当前播放位置；无播放器时返回0.0
        """
        if self._player is None:
            return 0.0
        try:
            pts = self._player.get_pts()
            return float(pts) if pts is not None else 0.0
        except Exception:
            return 0.0

    def get_duration(self):
        """获取视频总时长（秒）。

        Returns:
            float: 视频总时长；无播放器或未获取到时返回0.0
        """
        if self._player is None:
            return 0.0
        try:
            meta = self._player.get_metadata() or {}
            dur = meta.get("duration")
            if dur is None:
                return 0.0
            return float(dur)
        except Exception:
            return 0.0

    def get_state(self):
        """获取播放状态。

        Returns:
            str: 播放状态，取值为 'playing'、'paused'、'stopped'、'ended'
        """
        return self._state

    def update_cache_config(self, cache_size, cache_dir):
        """更新缓存配置。

        注意：缓存配置需要重新创建播放器（重新调用play）才会生效。

        Args:
            cache_size: 新的缓存大小（字节），传入None则不修改
            cache_dir: 新的缓存目录，传入None则不修改
        """
        if cache_size is not None:
            self._cache_size = cache_size
        if cache_dir is not None:
            self._cache_dir = cache_dir

    def _notify_state(self):
        """触发状态变化回调。"""
        if self.on_state_changed is not None:
            try:
                self.on_state_changed(self._state)
            except Exception:
                logger.exception("on_state_changed 回调异常")

    def _notify_error(self, msg):
        """触发错误回调。"""
        if self.on_error is not None:
            try:
                self.on_error(msg)
            except Exception:
                logger.exception("on_error 回调异常")
