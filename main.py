import sys
import os
import traceback
import tempfile
import atexit

# ===== SDL 环境变量设置（必须在任何 ffpyplayer/SDL2 库加载之前设置）=====
# ffpyplayer 内置 SDL2，在打包成 exe 后，SDL2 找不到合适的音频/视频驱动
# 会导致进程崩溃（C 层段错误，Python 无法捕获，生成 .dmp 文件）。
# 使用 dummy 驱动可避免 SDL 硬件初始化崩溃。
# 这是最早期设置点，确保后续任何模块 import ffpyplayer 时 SDL 已配置好。
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_NO_SIGNAL_HANDLERS", "1")


def _get_crash_log_paths():
    """按优先级返回候选崩溃日志目录列表。"""
    paths = []
    if getattr(sys, "frozen", False):
        paths.append(os.path.dirname(sys.executable))
        paths.append(os.path.dirname(os.path.abspath(sys.argv[0])))
    else:
        paths.append(os.path.dirname(os.path.abspath(__file__)))
    paths.append(tempfile.gettempdir())
    return paths


def _open_crash_log():
    """在第一个可写目录中创建崩溃日志文件，返回 (文件路径, 文件对象) 或 (None, None)。"""
    for d in _get_crash_log_paths():
        try:
            os.makedirs(d, exist_ok=True)
            log_path = os.path.join(d, "m3u8_tool_crash.log")
            # 二进制模式 + 无缓冲，确保 C 级别的 dup2 重定向也能正确写入
            fh = open(log_path, "ab", buffering=0)
            # 测试写入
            fh.write(b"")
            fh.flush()
            return log_path, fh
        except Exception:
            continue
    return None, None


# ===== 最早期：系统级 stderr/stdout 重定向 =====
# 使用 os.dup2() 重定向文件描述符 1(stdout) 和 2(stderr)，
# 这样 C 扩展库（ffpyplayer/SDL/ffmpeg）直接写 fd 1/2 的输出
# 也会被捕获到文件。这是 Python 层 sys.stderr 重定向做不到的。
_crash_log_path = None
_crash_fh = None
_orig_stdout_fd = None
_orig_stderr_fd = None

try:
    _crash_log_path, _crash_fh = _open_crash_log()
    if _crash_fh is not None:
        # 写入启动标记（二进制模式，手动编码）
        import datetime
        _ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        _header = (
            "\n" + "=" * 60 + "\n"
            + f"[{_ts}] 进程启动 PID={os.getpid()}\n"
            + f"[{_ts}] frozen={getattr(sys, 'frozen', False)}\n"
            + f"[{_ts}] executable={sys.executable}\n"
            + f"[{_ts}] argv={sys.argv}\n"
            + f"[{_ts}] crash log -> {_crash_log_path}\n"
            + "=" * 60 + "\n"
        )
        _crash_fh.write(_header.encode("utf-8", errors="replace"))
        _crash_fh.flush()

        # 保存原始 stdout/stderr 文件描述符
        _orig_stdout_fd = os.dup(1)
        _orig_stderr_fd = os.dup(2)

        # 系统级重定向：把 fd 1 和 2 都指向崩溃日志文件
        os.dup2(_crash_fh.fileno(), 1)
        os.dup2(_crash_fh.fileno(), 2)

        # 同时更新 Python 层的 sys.stdout/sys.stderr
        sys.stdout = _crash_fh
        sys.stderr = _crash_fh

        print(f"[{_ts}] stderr/stdout 重定向完成 -> {_crash_log_path}", flush=True)
except Exception as _e:
    # 如果重定向失败，尽量保留原始状态
    try:
        if _orig_stdout_fd is not None:
            os.dup2(_orig_stdout_fd, 1)
        if _orig_stderr_fd is not None:
            os.dup2(_orig_stderr_fd, 2)
    except Exception:
        pass
    _crash_log_path = None
    if _crash_fh is not None:
        try:
            _crash_fh.close()
        except Exception:
            pass
        _crash_fh = None


def _on_exit():
    """进程退出回调：在崩溃日志中写入退出标记。"""
    if _crash_fh is None:
        return
    try:
        import datetime
        _ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        _msg = f"[{_ts}] 进程正常退出 PID={os.getpid()}\n"
        _crash_fh.write(_msg.encode("utf-8", errors="replace"))
        _crash_fh.flush()
    except Exception:
        pass


try:
    atexit.register(_on_exit)
except Exception:
    pass


def _emergency_log(msg):
    """紧急日志：在日志系统初始化前可用，直接写到临时目录文件。

    用于捕获那些发生在 import 阶段、连 logging 都还没初始化的崩溃。
    """
    try:
        log_path = os.path.join(tempfile.gettempdir(), "m3u8_tool_crash.log")
        with open(log_path, "a", encoding="utf-8") as f:
            import datetime
            ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            f.write(f"[{ts}] {msg}\n")
    except Exception:
        # 紧急日志也失败就没办法了，忽略
        pass


def _bootstrap_logging():
    """最早阶段初始化日志系统。

    必须在任何业务模块 import 之前调用，以确保 import 阶段的异常
    也能被捕获到日志里。
    """
    # 把 src 目录加到 sys.path，保证 src.utils.logger 可以被导入
    _here = os.path.dirname(os.path.abspath(__file__))
    if _here not in sys.path:
        sys.path.insert(0, _here)

    try:
        from src.utils.logger import setup_logging, get_log_file_path
        logger, log_path = setup_logging()
        return logger, log_path
    except Exception as e:
        # 日志模块本身都 import 失败了，用紧急日志记录
        _emergency_log(f"日志系统初始化失败: {e}\n{traceback.format_exc()}")
        return None, None


# ===== 最早时机：初始化日志 =====
_logger, _log_path = _bootstrap_logging()


def _excepthook(exc_type, exc_value, exc_tb):
    """全局未捕获异常钩子：记录到日志文件。"""
    tb_str = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
    if _logger is not None:
        _logger.critical("===== 未捕获的异常，程序即将崩溃 =====")
        _logger.critical(tb_str)
    else:
        _emergency_log(f"未捕获异常（日志系统不可用）:\n{tb_str}")


# 安装全局异常钩子
sys.excepthook = _excepthook


def main():
    """应用入口函数。"""
    if _logger is not None:
        _logger.info("===== 应用启动 =====")
        _logger.info(f"Python版本: {sys.version}")
        _logger.info(f"平台: {sys.platform}")
        _logger.info(f"frozen: {getattr(sys, 'frozen', False)}")
        if _log_path:
            _logger.info(f"日志文件路径: {_log_path}")

    # 业务模块 import 放在 main() 内部，确保异常能被 excepthook 捕获
    try:
        from PyQt6.QtWidgets import QApplication
    except Exception as e:
        tb_str = traceback.format_exc()
        if _logger is not None:
            _logger.critical(f"PyQt6 导入失败: {e}\n{tb_str}")
        else:
            _emergency_log(f"PyQt6 导入失败: {e}\n{tb_str}")
        sys.exit(1)

    try:
        from src.ui.main_window import MainWindow
    except Exception as e:
        tb_str = traceback.format_exc()
        if _logger is not None:
            _logger.critical(f"主窗口模块导入失败: {e}\n{tb_str}")
        else:
            _emergency_log(f"主窗口模块导入失败: {e}\n{tb_str}")
        sys.exit(1)

    try:
        app = QApplication(sys.argv)
        window = MainWindow()
        # 把日志路径传给主窗口，便于状态栏显示
        if hasattr(window, "set_log_file_path") and _log_path:
            window.set_log_file_path(_log_path)
        window.show()
        exit_code = app.exec()
        if _logger is not None:
            _logger.info(f"应用正常退出，exit_code={exit_code}")
        sys.exit(exit_code)
    except Exception:
        tb_str = traceback.format_exc()
        if _logger is not None:
            _logger.critical(f"应用启动失败:\n{tb_str}")
        else:
            _emergency_log(f"应用启动失败:\n{tb_str}")
        sys.exit(1)


if __name__ == "__main__":
    main()
