from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QTableWidget,
    QTableWidgetItem, QHeaderView, QProgressBar, QAbstractItemView,
    QLabel, QInputDialog
)
from PyQt6.QtCore import pyqtSignal, Qt


class DownloadWidget(QWidget):
    """下载管理面板类，展示下载任务列表及进度。

    本类提供下载任务的添加、状态显示、进度展示和清空功能。
    实际的下载逻辑在Task 4完成，此处仅准备UI框架和信号定义。
    """

    # 请求下载信号（参数：m3u8链接字符串）
    download_requested = pyqtSignal(str)
    # 暂停/继续切换信号（参数：行索引）
    task_pause_toggled = pyqtSignal(int)
    # 取消任务信号（参数：行索引）
    task_cancel_requested = pyqtSignal(int)

    def __init__(self, parent=None):
        """初始化下载管理面板，构建任务列表和操作按钮。"""
        super().__init__(parent)
        # 任务信息映射：行索引 -> 任务控件字典
        self._tasks = {}

        self._init_ui()

    def _init_ui(self):
        """构建下载面板界面。"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(6)

        # 顶部标题
        title_label = QLabel("下载任务")
        title_label.setStyleSheet("font-weight: bold; font-size: 14px;")
        layout.addWidget(title_label)

        # 顶部按钮区域：添加下载、清空已完成
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(4)
        self.add_button = QPushButton("添加下载")
        self.add_button.clicked.connect(self._on_add_download)
        self.clear_button = QPushButton("清空已完成")
        self.clear_button.clicked.connect(self._on_clear_completed)
        btn_layout.addWidget(self.add_button)
        btn_layout.addWidget(self.clear_button)
        btn_layout.addStretch()
        layout.addLayout(btn_layout)

        # 下载任务列表（QTableWidget）
        # 列：文件名、进度、状态、速度、操作
        self.task_table = QTableWidget(0, 5)
        self.task_table.setHorizontalHeaderLabels(["文件名", "进度", "状态", "速度", "操作"])
        # 文件名列自适应拉伸，进度列固定宽度，状态和速度列按内容调整
        self.task_table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.Stretch
        )
        self.task_table.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.ResizeMode.Fixed
        )
        self.task_table.horizontalHeader().setSectionResizeMode(
            2, QHeaderView.ResizeMode.ResizeToContents
        )
        self.task_table.horizontalHeader().setSectionResizeMode(
            3, QHeaderView.ResizeMode.ResizeToContents
        )
        self.task_table.horizontalHeader().setSectionResizeMode(
            4, QHeaderView.ResizeMode.ResizeToContents
        )
        self.task_table.setColumnWidth(1, 150)
        # 隐藏垂直表头（行号）
        self.task_table.verticalHeader().setVisible(False)
        # 整行选中，禁止编辑
        self.task_table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        self.task_table.setEditTriggers(
            QAbstractItemView.EditTrigger.NoEditTriggers
        )
        layout.addWidget(self.task_table)

    def _on_add_download(self):
        """点击添加下载按钮：弹出输入框获取m3u8链接，发射下载请求信号。"""
        url, ok = QInputDialog.getText(
            self, "添加下载", "请输入m3u8链接:", text=""
        )
        if ok and url.strip():
            self.download_requested.emit(url.strip())

    def _on_clear_completed(self):
        """清空已完成的下载任务。"""
        rows_to_remove = []
        for row in range(self.task_table.rowCount()):
            status_item = self.task_table.item(row, 2)
            if status_item and status_item.text() == "已完成":
                rows_to_remove.append(row)
        # 从后往前删除避免索引错乱
        for row in sorted(rows_to_remove, reverse=True):
            # 清理操作列的按钮控件
            self.task_table.removeCellWidget(row, 4)
            self.task_table.removeRow(row)
            self._tasks.pop(row, None)

    def add_task(self, filename, url=""):
        """添加一个新的下载任务到列表。

        Args:
            filename: 任务显示的文件名
            url: m3u8链接（用于后续下载）

        Returns:
            int: 新任务所在的行索引
        """
        row = self.task_table.rowCount()
        self.task_table.insertRow(row)

        # 文件名列
        name_item = QTableWidgetItem(filename)
        self.task_table.setItem(row, 0, name_item)

        # 进度条列（嵌入QProgressBar）
        progress_bar = QProgressBar()
        progress_bar.setRange(0, 100)
        progress_bar.setValue(0)
        self.task_table.setCellWidget(row, 1, progress_bar)

        # 状态列
        status_item = QTableWidgetItem("等待中")
        status_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        self.task_table.setItem(row, 2, status_item)

        # 速度列
        speed_item = QTableWidgetItem("--")
        speed_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        self.task_table.setItem(row, 3, speed_item)

        # 操作列：暂停/继续按钮 + 取消按钮
        op_widget = QWidget()
        op_layout = QHBoxLayout(op_widget)
        op_layout.setContentsMargins(2, 2, 2, 2)
        op_layout.setSpacing(4)
        pause_button = QPushButton("暂停")
        cancel_button = QPushButton("取消")
        # 捕获行索引，点击时发射对应信号
        pause_button.clicked.connect(
            lambda _, r=row: self.task_pause_toggled.emit(r)
        )
        cancel_button.clicked.connect(
            lambda _, r=row: self.task_cancel_requested.emit(r)
        )
        op_layout.addWidget(pause_button)
        op_layout.addWidget(cancel_button)
        self.task_table.setCellWidget(row, 4, op_widget)

        # 缓存任务信息
        self._tasks[row] = {
            "filename": filename,
            "url": url,
            "progress_bar": progress_bar,
            "status_item": status_item,
            "speed_item": speed_item,
            "pause_button": pause_button,
            "cancel_button": cancel_button,
        }
        return row

    def set_task_paused(self, row, paused):
        """更新暂停/继续按钮文本。

        Args:
            row: 任务所在行索引
            paused: True表示已暂停（按钮显示"继续"），
                    False表示下载中（按钮显示"暂停"）
        """
        if 0 <= row < self.task_table.rowCount():
            task_info = self._tasks.get(row)
            if task_info:
                pause_button = task_info.get("pause_button")
                if pause_button:
                    pause_button.setText("继续" if paused else "暂停")

    def update_task_progress(self, row, progress, speed=""):
        """更新指定任务的进度和速度。

        Args:
            row: 任务所在行索引
            progress: 进度百分比（0-100）
            speed: 当前下载速度字符串，为空则显示"--"
        """
        if 0 <= row < self.task_table.rowCount():
            progress_bar = self.task_table.cellWidget(row, 1)
            if isinstance(progress_bar, QProgressBar):
                progress_bar.setValue(int(progress))
            speed_item = self.task_table.item(row, 3)
            if speed_item:
                speed_item.setText(speed if speed else "--")

    def update_task_status(self, row, status):
        """更新指定任务的状态。

        Args:
            row: 任务所在行索引
            status: 状态字符串（如 "下载中"、"已完成"、"失败"、"已暂停"）
        """
        if 0 <= row < self.task_table.rowCount():
            status_item = self.task_table.item(row, 2)
            if status_item:
                status_item.setText(status)
