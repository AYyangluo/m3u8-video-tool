from PyQt6.QtWidgets import QWidget, QVBoxLayout, QLabel
from PyQt6.QtCore import pyqtSignal, Qt, QTimer
from PyQt6.QtGui import QImage, QPixmap, QPainter

from src.core.player import M3U8Player


class _VideoCanvas(QWidget):
    """视频画布：通过paintEvent绘制当前视频帧。

    该控件用于在主线程中接收来自帧线程的视频帧数据（已通过信号跨线程传递）
    并按等比例缩放后居中绘制。
    """

    def __init__(self, parent=None):
        """初始化视频画布，背景设为黑色。"""
        super().__init__(parent)
        self.setStyleSheet("background-color: black;")
        # 当前帧对应的QPixmap
        self._pixmap = None

    def set_pixmap(self, pixmap):
        """设置当前帧并触发重绘。

        Args:
            pixmap: QPixmap实例，传入None则清空画面
        """
        self._pixmap = pixmap
        self.update()

    def clear(self):
        """清空画面。"""
        self._pixmap = None
        self.update()

    def paintEvent(self, event):
        """绘制视频帧：黑色背景 + 等比例缩放居中的当前帧。"""
        painter = QPainter(self)
        # 先填充黑色背景
        painter.fillRect(self.rect(), Qt.GlobalColor.black)
        # 有帧时等比例缩放并居中绘制
        if self._pixmap is not None and not self._pixmap.isNull():
            scaled = self._pixmap.scaled(
                self.size(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            x = (self.width() - scaled.width()) // 2
            y = (self.height() - scaled.height()) // 2
            painter.drawPixmap(x, y, scaled)
        painter.end()


class PlayerWidget(QWidget):
    """播放器组件类，用于ffpyplayer渲染视频帧。

    本类提供ffpyplayer渲染所需的QWidget容器、占位提示以及与主窗口通信的信号，
    并封装M3U8Player核心类，对外暴露播放/暂停/继续/停止/跳转/速度/音量等控制接口。
    """

    # 播放位置变化信号（参数：当前播放位置，单位毫秒）
    position_changed = pyqtSignal(int)
    # 总时长变化信号（参数：总时长，单位毫秒）
    duration_changed = pyqtSignal(int)
    # 播放状态变化信号（参数：状态字符串，如 "playing"、"paused"、"stopped"、"ended"、"loading"）
    state_changed = pyqtSignal(str)
    # 错误信号（参数：错误信息字符串）
    error_occurred = pyqtSignal(str)
    # 视频帧就绪信号（参数：bytes数据、宽度、高度）
    # 通过信号机制实现从帧线程到主线程的跨线程安全传递
    _frame_ready = pyqtSignal(object, int, int)

    def __init__(self, parent=None):
        """初始化播放器组件，构建渲染容器、占位提示并集成M3U8Player。"""
        super().__init__(parent)

        # 总时长缓存（毫秒），供外部查询
        self._duration = 0
        # 当前播放URL，便于在停止/结束后重新播放
        self._current_url = ""

        # 主布局：无边距，让渲染容器填满整个组件
        self._main_layout = QVBoxLayout(self)
        self._main_layout.setContentsMargins(0, 0, 0, 0)
        self._main_layout.setSpacing(0)

        # 用于ffpyplayer渲染的容器QWidget（视频画布）
        # 通过winId()获取原生窗口句柄供M3U8Player使用
        self.render_widget = _VideoCanvas(self)
        self._main_layout.addWidget(self.render_widget)

        # 渲染容器内部布局，用于居中显示占位提示
        self._render_layout = QVBoxLayout(self.render_widget)
        self._render_layout.setContentsMargins(0, 0, 0, 0)

        # 占位提示标签（未播放视频时显示）
        self.placeholder_label = QLabel("请输入m3u8链接并点击播放")
        self.placeholder_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.placeholder_label.setStyleSheet(
            "color: white; font-size: 16px; background-color: transparent;"
        )
        self._render_layout.addWidget(self.placeholder_label)

        # ===== 集成M3U8Player核心类 =====
        # 创建播放器实例（即使ffpyplayer未安装也能创建对象，play时会报错）
        self._player = M3U8Player(self.get_wid())
        # 注册回调：帧线程通过这些回调触发Qt信号，实现跨线程安全通信
        self._player.on_frame = self._on_frame_from_thread
        self._player.on_state_changed = self._on_state_from_thread
        self._player.on_error = self._on_error_from_thread
        self._player.on_eof = self._on_eof_from_thread

        # 连接帧就绪信号到主线程处理函数
        self._frame_ready.connect(self._on_frame_ready)

        # ===== 定时器：定时获取播放位置与总时长 =====
        self._poll_timer = QTimer(self)
        self._poll_timer.setInterval(100)  # 100ms轮询一次
        self._poll_timer.timeout.connect(self._on_poll_timeout)

    # ===== 播放器控制接口 =====
    def play(self, url):
        """播放指定m3u8链接。

        Args:
            url: m3u8播放链接
        """
        if not url:
            self.error_occurred.emit("链接不能为空")
            return

        self._current_url = url
        # 发射loading状态，主窗口据此更新UI
        self.state_changed.emit("loading")
        # 隐藏占位提示，准备显示视频画面
        self.set_placeholder_visible(False)
        # 启动轮询定时器获取位置和时长
        self._poll_timer.start()
        # 调用核心播放器播放
        self._player.play(url)

    def pause(self):
        """暂停播放。"""
        self._player.pause()

    def resume(self):
        """继续播放。"""
        self._player.resume()

    def stop(self):
        """停止播放。"""
        self._player.stop()

    def seek(self, position):
        """跳转到指定播放位置。

        Args:
            position: 目标位置（秒）
        """
        self._player.seek(position)

    def set_rate(self, rate):
        """设置播放速度。

        Args:
            rate: 播放速度倍率（0.5-2.0）
        """
        self._player.set_rate(rate)

    def set_volume(self, volume):
        """设置音量。

        Args:
            volume: 音量，范围0.0到1.0
        """
        self._player.set_volume(volume)

    def get_state(self):
        """获取当前播放状态。

        Returns:
            str: 播放状态
        """
        return self._player.get_state()

    def update_cache_config(self, cache_size, cache_dir):
        """更新播放器缓存配置。

        注意：配置更新后需要重新播放才生效。

        Args:
            cache_size: 缓存大小（字节）
            cache_dir: 缓存目录
        """
        self._player.update_cache_config(cache_size, cache_dir)

    # ===== 来自帧线程的回调（通过信号转发到主线程） =====
    def _on_frame_from_thread(self, data, width, height):
        """帧线程回调：将帧数据通过信号转发到主线程渲染。"""
        # 信号在跨线程时会自动使用队列连接，保证主线程安全处理
        self._frame_ready.emit(data, width, height)

    def _on_state_from_thread(self, state):
        """帧线程回调：转发状态变化信号。"""
        self.state_changed.emit(state)
        # 停止或结束时显示占位提示并停止轮询
        if state in ("stopped", "ended"):
            self._poll_timer.stop()
            self.set_placeholder_visible(True)
            self.render_widget.clear()

    def _on_error_from_thread(self, msg):
        """帧线程回调：转发错误信号。"""
        self.error_occurred.emit(msg)

    def _on_eof_from_thread(self):
        """帧线程回调：播放结束处理。"""
        self._poll_timer.stop()

    # ===== 主线程槽函数 =====
    def _on_frame_ready(self, data, width, height):
        """主线程处理帧数据：构造QPixmap并设置到画布。

        Args:
            data: RGB字节数据
            width: 帧宽度
            height: 帧高度
        """
        if not data or width <= 0 or height <= 0:
            return
        try:
            # 构造QImage（必须copy以避免数据被回收）
            qimg = QImage(
                data, width, height, width * 3, QImage.Format.Format_RGB888
            ).copy()
            pixmap = QPixmap.fromImage(qimg)
            self.render_widget.set_pixmap(pixmap)
        except Exception:
            pass

    def _on_poll_timeout(self):
        """定时轮询：获取播放位置与总时长并发射信号。"""
        if self._player is None:
            return

        # 获取播放位置（秒）并转换为毫秒发射
        position = self._player.get_position()
        if position >= 0:
            self.position_changed.emit(int(position * 1000))

        # 获取总时长（秒），变化时更新缓存并发射信号
        duration = self._player.get_duration()
        if duration > 0:
            duration_ms = int(duration * 1000)
            if duration_ms != self._duration:
                self._duration = duration_ms
                self.duration_changed.emit(duration_ms)

    # ===== 既有辅助方法 =====
    def get_wid(self):
        """获取渲染窗口的原生ID，供ffpyplayer使用。

        ffpyplayer在创建播放器时需要传入一个窗口ID用于视频帧渲染，
        此方法返回render_widget的原生窗口句柄。

        Returns:
            int: 渲染容器的原生窗口ID
        """
        return int(self.render_widget.winId())

    def set_placeholder_visible(self, visible):
        """设置占位提示是否可见。

        当开始播放视频时应隐藏占位提示，停止播放或加载失败时显示。

        Args:
            visible: True显示占位提示，False隐藏
        """
        self.placeholder_label.setVisible(visible)

    def set_duration(self, duration):
        """设置总时长并缓存。

        Args:
            duration: 总时长（毫秒）
        """
        self._duration = duration

    def get_duration(self):
        """获取总时长。

        Returns:
            int: 总时长（毫秒）
        """
        return self._duration

    def closeEvent(self, event):
        """窗口关闭时停止播放器，释放资源。"""
        try:
            self._poll_timer.stop()
            self._player.stop()
        except Exception:
            pass
        super().closeEvent(event)
