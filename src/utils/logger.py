"""日志工具模块。

提供全局 logger 实例，将日志同时输出到文件和控制台。
日志文件位置（按优先级尝试）：
1. 可执行文件所在目录（打包模式）或项目根目录（开发模式）
2. 用户临时目录（TEMP / tmp）
"""

import logging
import os
import sys
import tempfile


_log_file_path = None


def _get_log_dir():
    """获取日志文件存放目录（首选目录）。"""
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    # 开发模式：项目根目录（本文件位于 src/utils/logger.py）
    return os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _try_create_file_handler(log_dir, fmt):
    """尝试在指定目录创建日志文件 handler。

    Returns:
        (handler, log_file_path) 或 (None, None)
    """
    try:
        os.makedirs(log_dir, exist_ok=True)
        log_file = os.path.join(log_dir, "m3u8_tool.log")
        fh = logging.FileHandler(log_file, encoding="utf-8")
        fh.setLevel(logging.DEBUG)
        fh.setFormatter(fmt)
        # 测试写入（FileHandler 构造时不一定立即打开文件，这里主动试写）
        fh.stream.write("")
        fh.flush()
        return fh, log_file
    except Exception:
        return None, None


def setup_logging():
    """配置全局日志系统，输出到文件和控制台。

    多次调用安全：已配置 handler 时不会重复添加。

    Returns:
        tuple: (logger, log_file_path) —— 日志文件路径可能为 None（全部失败时）
    """
    global _log_file_path

    logger = logging.getLogger("m3u8")
    logger.setLevel(logging.DEBUG)
    if logger.handlers:
        return logger, _log_file_path

    fmt = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(threadName)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # 按优先级尝试写入目录
    candidates = [_get_log_dir(), tempfile.gettempdir()]

    fh = None
    log_file = None
    for d in candidates:
        fh, log_file = _try_create_file_handler(d, fmt)
        if fh is not None:
            break

    if fh is not None:
        logger.addHandler(fh)
        _log_file_path = log_file
    else:
        # 所有目录都失败了，仅控制台输出
        print("[logger] 警告: 所有候选目录都无法创建日志文件，仅输出到控制台", file=sys.stderr)
        _log_file_path = None

    # 控制台 handler
    sh = logging.StreamHandler()
    sh.setLevel(logging.INFO)
    sh.setFormatter(fmt)
    logger.addHandler(sh)

    if _log_file_path:
        logger.info(f"日志系统初始化完成，日志文件: {_log_file_path}")
    return logger, _log_file_path


def get_log_file_path():
    """获取当前日志文件路径，未初始化或失败时返回 None。"""
    return _log_file_path


def get_logger():
    """获取全局 logger 实例。

    在 setup_logging() 调用前也可安全调用，只是不会有 handler 输出。
    """
    return logging.getLogger("m3u8")
