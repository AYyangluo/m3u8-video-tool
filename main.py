import sys
import os
import traceback
import tempfile


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
