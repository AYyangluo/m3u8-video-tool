import threading

from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLineEdit, QPushButton,
    QSlider, QComboBox, QLabel, QSplitter
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QAction

from src.ui.player_widget import PlayerWidget
from src.ui.download_widget import DownloadWidget
from src.ui.settings_dialog import SettingsDialog
from src.core.downloader import Downloader
from src.utils.config import Config


class MainWindow(QMainWindow):
    """主窗口类，承载播放器组件和下载组件。

    界面布局：
    - 顶部工具栏：m3u8链接输入、播放按钮、下载按钮
    - 中央区域（QSplitter水平分割）：
      - 左侧：播放器区域 + 底部控制栏
      - 右侧：下载管理面板
    - 菜单栏：设置菜单
    """

    # 下载进度信号（行索引、进度百分比、速度字符串）
    # 通过信号实现从下载线程到主线程的安全UI更新
    _download_progress_sig = pyqtSignal(int, int, str)
    # 下载状态信号（行索引、状态字符串）
    _download_status_sig = pyqtSignal(int, str)

    def __init__(self, parent=None):
        """初始化主窗口，设置窗口标题和大小，构建界面。"""
        super().__init__(parent)
        # 设置窗口标题
        self.setWindowTitle("M3U8视频工具")
        # 设置窗口初始大小为 1000x700
        self.resize(1000, 700)

        # 当前播放/下载的m3u8链接
        self.current_url = ""
        # 活动下载任务映射：行索引 -> {'downloader': Downloader, 'thread': Thread}
        self._downloads = {}
        # 已取消的任务行索引集合（用于区分取消与失败状态）
        self._cancelled_rows = set()

        self._init_ui()
        self._init_menu()
        self._connect_signals()

    def _init_ui(self):
        """构建主界面布局。"""
        # 中央容器
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(4, 4, 4, 4)
        main_layout.setSpacing(4)

        # ===== 顶部工具栏区域 =====
        toolbar_layout = QHBoxLayout()
        toolbar_layout.setSpacing(4)
        # m3u8链接输入框
        self.url_edit = QLineEdit()
        self.url_edit.setPlaceholderText("请输入m3u8链接...")
        toolbar_layout.addWidget(self.url_edit, 1)
        # 播放按钮（加载并播放m3u8链接）
        self.play_button = QPushButton("播放")
        self.play_button.clicked.connect(self._on_play_clicked)
        toolbar_layout.addWidget(self.play_button)
        # 下载按钮（触发下载）
        self.download_button = QPushButton("下载")
        self.download_button.clicked.connect(self._on_download_clicked)
        toolbar_layout.addWidget(self.download_button)
        main_layout.addLayout(toolbar_layout)

        # ===== 中央播放区域 + 右侧下载面板（QSplitter水平分割） =====
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # 左侧：播放区域 + 底部控制栏
        player_container = QWidget()
        player_layout = QVBoxLayout(player_container)
        player_layout.setContentsMargins(0, 0, 0, 0)
        player_layout.setSpacing(4)
        # 播放器组件（视频播放区域）
        self.player_widget = PlayerWidget()
        player_layout.addWidget(self.player_widget, 1)
        # 底部控制栏
        player_layout.addLayout(self._build_control_bar())
        splitter.addWidget(player_container)

        # 右侧：下载管理面板
        self.download_widget = DownloadWidget()
        splitter.addWidget(self.download_widget)

        # 设置分割比例（播放区域占大部分，下载面板占小部分）
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([700, 300])
        main_layout.addWidget(splitter, 1)

        # ===== 状态栏 =====
        self.statusBar().showMessage("就绪")

    def _build_control_bar(self):
        """构建底部控制栏布局。

        Returns:
            QHBoxLayout: 包含播放/暂停、进度条、时间显示、速度选择、音量控制的布局
        """
        control_layout = QHBoxLayout()
        control_layout.setContentsMargins(0, 0, 0, 0)
        control_layout.setSpacing(6)

        # 播放/暂停按钮
        self.play_pause_button = QPushButton("播放")
        self.play_pause_button.setFixedWidth(60)
        self.play_pause_button.clicked.connect(self._on_play_pause_clicked)
        control_layout.addWidget(self.play_pause_button)

        # 当前时间显示
        self.current_time_label = QLabel("00:00")
        self.current_time_label.setFixedWidth(55)
        self.current_time_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        control_layout.addWidget(self.current_time_label)

        # 进度条（QSlider，可拖动）
        self.progress_slider = QSlider(Qt.Orientation.Horizontal)
        self.progress_slider.setRange(0, 1000)
        self.progress_slider.setValue(0)
        control_layout.addWidget(self.progress_slider, 1)

        # 总时间显示
        self.total_time_label = QLabel("00:00")
        self.total_time_label.setFixedWidth(55)
        self.total_time_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        control_layout.addWidget(self.total_time_label)

        # 速度选择下拉框（0.5x, 0.75x, 1x, 1.25x, 1.5x, 2x）
        self.speed_combo = QComboBox()
        self.speed_combo.addItems(["0.5x", "0.75x", "1x", "1.25x", "1.5x", "2x"])
        self.speed_combo.setCurrentText("1x")
        self.speed_combo.setFixedWidth(70)
        control_layout.addWidget(self.speed_combo)

        # 音量控制（QSlider）
        volume_label = QLabel("音量")
        control_layout.addWidget(volume_label)
        self.volume_slider = QSlider(Qt.Orientation.Horizontal)
        self.volume_slider.setRange(0, 100)
        self.volume_slider.setValue(80)
        self.volume_slider.setFixedWidth(100)
        control_layout.addWidget(self.volume_slider)

        return control_layout

    def _init_menu(self):
        """构建菜单栏，包含设置菜单。"""
        menubar = self.menuBar()
        # 设置菜单
        settings_menu = menubar.addMenu("设置")
        # 偏好设置动作（打开设置对话框，包含缓存大小、缓存位置、下载路径）
        settings_action = QAction("偏好设置...", self)
        settings_action.triggered.connect(self._on_settings_triggered)
        settings_menu.addAction(settings_action)

    def _connect_signals(self):
        """连接信号与槽。"""
        # 进度条拖动信号
        self.progress_slider.sliderMoved.connect(self._on_slider_moved)
        # 进度条值变化信号（用于点击进度条）
        self.progress_slider.valueChanged.connect(self._on_slider_value_changed)
        # 速度变化信号
        self.speed_combo.currentTextChanged.connect(self._on_speed_changed)
        # 音量变化信号
        self.volume_slider.valueChanged.connect(self._on_volume_changed)
        # 播放器组件信号
        self.player_widget.position_changed.connect(self._on_position_changed)
        self.player_widget.duration_changed.connect(self._on_duration_changed)
        self.player_widget.state_changed.connect(self._on_state_changed)
        self.player_widget.error_occurred.connect(self._on_error_occurred)
        # 下载面板信号
        self.download_widget.download_requested.connect(self._on_download_requested)
        # 下载面板任务控制信号
        self.download_widget.task_pause_toggled.connect(self._on_task_pause_toggled)
        self.download_widget.task_cancel_requested.connect(self._on_task_cancel)
        # 下载线程UI更新信号（跨线程安全更新下载面板）
        self._download_progress_sig.connect(self._on_download_progress_ui)
        self._download_status_sig.connect(self._on_download_status_ui)

    # ===== 顶部工具栏槽函数 =====
    def _on_play_clicked(self):
        """点击播放按钮：加载并播放m3u8链接。"""
        url = self.url_edit.text().strip()
        if not url:
            self.statusBar().showMessage("请输入m3u8链接")
            return
        self.current_url = url
        self.statusBar().showMessage(f"正在加载: {url}")
        # 调用PlayerWidget播放m3u8链接（内部会集成M3U8Player）
        self.player_widget.play(url)

    def _on_download_clicked(self):
        """点击下载按钮：从输入框获取URL并启动下载任务。"""
        url = self.url_edit.text().strip()
        if not url:
            self.statusBar().showMessage("请输入m3u8链接")
            return
        self._start_download(url)

    def _start_download(self, url):
        """启动下载任务，添加到下载面板并启动后台下载线程。

        Args:
            url: m3u8链接
        """
        self.current_url = url
        # 根据URL生成文件名
        filename = url.split("/")[-1] or "m3u8_video"
        if not filename.endswith(".mp4"):
            base = filename.rsplit(".", 1)[0] if "." in filename else filename
            filename = base + ".mp4"
        # 添加下载任务到下载面板，获取行索引
        row = self.download_widget.add_task(filename, url)
        self.statusBar().showMessage(f"已添加下载任务: {filename}")
        # 启动后台下载线程
        self._launch_download(row, url)

    def _launch_download(self, row, url):
        """启动后台线程执行下载任务。

        通过Downloader在独立线程中下载m3u8，进度与状态通过信号
        跨线程回传到主线程更新下载面板。

        Args:
            row: 下载任务在面板中的行索引
            url: m3u8链接
        """
        # 确保下载目录存在
        output_dir = Config.DEFAULT_DOWNLOAD_DIR
        Config.ensure_download_dir()

        downloader = Downloader()

        # 进度回调：由下载线程触发，通过信号转发到主线程
        def on_progress(downloaded, total, speed):
            progress = int(downloaded / total * 100) if total > 0 else 0
            speed_str = f"{speed:.1f} seg/s"
            self._download_progress_sig.emit(row, progress, speed_str)

        # 状态回调：由下载线程触发，通过信号转发到主线程
        def on_status(status):
            self._download_status_sig.emit(row, status)

        downloader.on_progress = on_progress
        downloader.on_status = on_status

        # 下载线程入口
        def run_download():
            try:
                downloader.download(url, output_dir)
            except Exception:
                self._download_status_sig.emit(row, "error")

        thread = threading.Thread(target=run_download, daemon=True)
        thread.start()

        # 记录活动下载任务，便于后续管理
        self._downloads[row] = {
            "downloader": downloader,
            "thread": thread,
            "paused": False,
        }

    def _on_download_progress_ui(self, row, progress, speed):
        """主线程槽：更新下载面板进度与速度。"""
        self.download_widget.update_task_progress(row, progress, speed)

    def _on_download_status_ui(self, row, status):
        """主线程槽：更新下载面板状态。

        将Downloader内部状态字符串映射为中文显示。
        """
        # 已取消的任务：忽略下载线程后续上报的error状态，保持"已取消"显示
        if status == "error" and row in self._cancelled_rows:
            self._cancelled_rows.discard(row)
            return
        # 状态中英文映射
        status_map = {
            "downloading": "下载中",
            "paused": "已暂停",
            "completed": "已完成",
            "error": "失败",
        }
        display = status_map.get(status, status)
        self.download_widget.update_task_status(row, display)
        # 完成或失败时清理活动任务记录
        if status in ("completed", "error"):
            self._downloads.pop(row, None)
            if status == "completed":
                self.statusBar().showMessage(f"下载完成: 行 {row + 1}")
            else:
                self.statusBar().showMessage(f"下载失败: 行 {row + 1}")

    def _on_task_pause_toggled(self, row):
        """暂停/继续切换：根据当前状态调用pause()或resume()。

        Args:
            row: 任务所在行索引
        """
        info = self._downloads.get(row)
        if not info:
            return
        downloader = info["downloader"]
        if info.get("paused", False):
            # 当前已暂停，执行继续
            downloader.resume()
            info["paused"] = False
            self.download_widget.set_task_paused(row, False)
        else:
            # 当前下载中，执行暂停
            downloader.pause()
            info["paused"] = True
            self.download_widget.set_task_paused(row, True)

    def _on_task_cancel(self, row):
        """取消下载任务。

        Args:
            row: 任务所在行索引
        """
        info = self._downloads.pop(row, None)
        if not info:
            return
        downloader = info["downloader"]
        downloader.cancel()
        # 标记为已取消，避免下载线程的error状态覆盖显示
        self._cancelled_rows.add(row)
        self.download_widget.update_task_status(row, "已取消")
        self.statusBar().showMessage(f"已取消下载: 行 {row + 1}")

    # ===== 底部控制栏槽函数 =====
    def _on_play_pause_clicked(self):
        """点击播放/暂停按钮：切换播放状态。

        根据当前播放状态执行不同操作：
        - playing：暂停
        - paused：继续
        - stopped/ended：若有当前URL则重新播放
        """
        state = self.player_widget.get_state()
        if state == "playing":
            self.player_widget.pause()
        elif state == "paused":
            self.player_widget.resume()
        else:
            # 停止或结束状态：若有URL则重新播放
            if self.current_url:
                self.player_widget.play(self.current_url)

    def _on_slider_moved(self, position):
        """进度条拖动：跳转到指定播放位置。

        Args:
            position: 进度条值（0-1000，对应0%-100%）
        """
        # 根据进度条值与总时长计算目标秒数
        duration = self.player_widget.get_duration()
        if duration > 0:
            seconds = position / 1000.0 * duration / 1000.0
            self.player_widget.seek(seconds)
        self._update_current_time_by_slider(position)

    def _on_slider_value_changed(self, position):
        """进度条值变化（点击进度条）。"""
        # 仅在非拖动状态下更新时间显示，避免重复
        if not self.progress_slider.isSliderDown():
            self._update_current_time_by_slider(position)

    def _on_speed_changed(self, speed_text):
        """速度选择变化：设置播放速度。

        Args:
            speed_text: 速度下拉框文本，如 "1.5x"
        """
        # 去掉"x"后缀转为浮点数
        try:
            speed = float(speed_text.rstrip("x"))
        except ValueError:
            speed = 1.0
        # 调用PlayerWidget设置播放速度
        self.player_widget.set_rate(speed)
        self.statusBar().showMessage(f"播放速度: {speed}x")

    def _on_volume_changed(self, value):
        """音量变化：设置播放器音量。

        Args:
            value: 音量滑块值（0-100）
        """
        # 0-100 转换为 0.0-1.0
        volume = value / 100.0
        self.player_widget.set_volume(volume)
        self.statusBar().showMessage(f"音量: {value}")

    # ===== 播放器信号槽函数 =====
    def _on_position_changed(self, position):
        """播放位置变化：更新进度条和时间显示。"""
        # 拖动进度条时不反向更新，避免冲突
        if not self.progress_slider.isSliderDown():
            duration = self.player_widget.get_duration()
            if duration > 0:
                self.progress_slider.setValue(int(position / duration * 1000))
            else:
                self.progress_slider.setValue(0)
        self.current_time_label.setText(self._format_time(position))

    def _on_duration_changed(self, duration):
        """总时长变化：缓存时长并更新总时间显示。"""
        self.player_widget.set_duration(duration)
        self.total_time_label.setText(self._format_time(duration))

    def _on_state_changed(self, state):
        """播放状态变化：更新播放/暂停按钮文本和状态栏。

        Args:
            state: 播放状态字符串，如 'playing'/'paused'/'stopped'/'ended'/'loading'
        """
        if state == "playing":
            self.play_pause_button.setText("暂停")
        elif state in ("paused", "stopped", "ended", "loading"):
            self.play_pause_button.setText("播放")
        self.statusBar().showMessage(f"状态: {state}")

    def _on_error_occurred(self, error_msg):
        """播放器错误：显示错误信息并恢复占位提示。"""
        self.statusBar().showMessage(f"错误: {error_msg}")
        self.play_pause_button.setText("播放")
        self.player_widget.set_placeholder_visible(True)

    # ===== 下载面板信号槽函数 =====
    def _on_download_requested(self, url):
        """下载面板请求下载：将URL填入输入框并启动下载。"""
        self.url_edit.setText(url)
        self._start_download(url)

    # ===== 设置菜单槽函数 =====
    def _on_settings_triggered(self):
        """打开设置对话框。

        设置确认后，将新的缓存配置同步到PlayerWidget的播放器，
        缓存配置会在下次播放时生效。
        """
        dialog = SettingsDialog(self)
        if dialog.exec() == SettingsDialog.DialogCode.Accepted:
            # 将更新后的缓存配置同步到播放器
            self.player_widget.update_cache_config(
                Config.DEFAULT_CACHE_SIZE, Config.DEFAULT_CACHE_DIR
            )
            self.statusBar().showMessage("设置已保存")

    # ===== 时间显示辅助方法 =====
    def _format_time(self, ms):
        """将毫秒格式化为 mm:ss 或 hh:mm:ss。

        Args:
            ms: 时间（毫秒）

        Returns:
            str: 格式化后的时间字符串
        """
        total_seconds = int(ms) // 1000
        hours = total_seconds // 3600
        minutes = (total_seconds % 3600) // 60
        seconds = total_seconds % 60
        if hours > 0:
            return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
        return f"{minutes:02d}:{seconds:02d}"

    def _update_current_time_by_slider(self, slider_value):
        """根据进度条值更新当前时间显示。

        Args:
            slider_value: 进度条值（0-1000）
        """
        duration = self.player_widget.get_duration()
        if duration > 0:
            current_ms = int(slider_value / 1000 * duration)
        else:
            current_ms = 0
        self.current_time_label.setText(self._format_time(current_ms))

    def closeEvent(self, event):
        """窗口关闭时清理资源：停止播放器并取消所有活动下载。"""
        # 停止播放器
        try:
            self.player_widget.stop()
        except Exception:
            pass
        # 取消所有活动下载任务
        for info in self._downloads.values():
            try:
                info["downloader"].cancel()
            except Exception:
                pass
        self._downloads.clear()
        super().closeEvent(event)
