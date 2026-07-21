import os


class Config:
    """配置管理类，管理应用的默认配置项。"""

    # 默认下载保存路径（用户主目录下的 downloads 文件夹）
    DEFAULT_DOWNLOAD_DIR = os.path.join(os.path.expanduser("~"), "Downloads", "m3u8_downloads")

    # 默认并发下载数
    DEFAULT_MAX_WORKERS = 4

    # 默认下载超时时间（秒）
    DEFAULT_TIMEOUT = 30

    # 默认下载重试次数
    DEFAULT_RETRIES = 3

    # 默认ffmpeg可执行文件路径，调用系统ffmpeg
    DEFAULT_FFMPEG_PATH = "ffmpeg"

    # 默认请求头
    DEFAULT_HEADERS = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/110.0.0.0 Safari/537.36"
    }

    # ===== 播放器缓存配置 =====
    # 默认播放缓存大小（字节），默认10MB
    DEFAULT_CACHE_SIZE = 10 * 1024 * 1024

    # 默认播放缓存位置（系统临时目录下的 m3u8_cache 文件夹）
    DEFAULT_CACHE_DIR = os.path.join(os.path.expanduser("~"), ".m3u8_tool", "cache")

    @classmethod
    def ensure_download_dir(cls):
        """确保默认下载目录存在，若不存在则创建。"""
        os.makedirs(cls.DEFAULT_DOWNLOAD_DIR, exist_ok=True)
        return cls.DEFAULT_DOWNLOAD_DIR

    @classmethod
    def ensure_cache_dir(cls):
        """确保缓存目录存在，若不存在则创建。"""
        os.makedirs(cls.DEFAULT_CACHE_DIR, exist_ok=True)
        return cls.DEFAULT_CACHE_DIR
