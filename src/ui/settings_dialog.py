import os

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QFormLayout, QHBoxLayout, QSpinBox,
    QLineEdit, QPushButton, QFileDialog, QDialogButtonBox,
    QGroupBox
)

from src.utils.config import Config


class SettingsDialog(QDialog):
    """设置对话框类，用于配置缓存大小、缓存位置和下载路径。

    读取Config中的默认值填充控件，确认时将配置保存回Config。
    """

    def __init__(self, parent=None):
        """初始化设置对话框，构建界面并加载当前配置。"""
        super().__init__(parent)
        self.setWindowTitle("设置")
        self.setModal(True)
        self.setMinimumWidth(450)

        self._init_ui()
        self._load_config()

    def _init_ui(self):
        """构建设置对话框界面。"""
        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        # ===== 播放缓存设置组 =====
        cache_group = QGroupBox("播放缓存设置")
        cache_form = QFormLayout(cache_group)

        # 缓存大小（QSpinBox，单位MB，范围1-1024，默认10MB）
        self.cache_size_spin = QSpinBox()
        self.cache_size_spin.setRange(1, 1024)
        self.cache_size_spin.setSuffix(" MB")
        self.cache_size_spin.setSingleStep(1)
        cache_form.addRow("缓存大小：", self.cache_size_spin)

        # 缓存位置（QLineEdit + 浏览按钮）
        cache_dir_layout = QHBoxLayout()
        self.cache_dir_edit = QLineEdit()
        self.cache_dir_edit.setPlaceholderText("选择缓存目录...")
        self.cache_dir_browse = QPushButton("浏览...")
        self.cache_dir_browse.clicked.connect(self._on_browse_cache_dir)
        cache_dir_layout.addWidget(self.cache_dir_edit)
        cache_dir_layout.addWidget(self.cache_dir_browse)
        cache_form.addRow("缓存位置：", cache_dir_layout)

        layout.addWidget(cache_group)

        # ===== 下载设置组 =====
        download_group = QGroupBox("下载设置")
        download_form = QFormLayout(download_group)

        # 下载路径（QLineEdit + 浏览按钮）
        download_dir_layout = QHBoxLayout()
        self.download_dir_edit = QLineEdit()
        self.download_dir_edit.setPlaceholderText("选择下载保存目录...")
        self.download_dir_browse = QPushButton("浏览...")
        self.download_dir_browse.clicked.connect(self._on_browse_download_dir)
        download_dir_layout.addWidget(self.download_dir_edit)
        download_dir_layout.addWidget(self.download_dir_browse)
        download_form.addRow("下载路径：", download_dir_layout)

        layout.addWidget(download_group)

        # ===== 确认/取消按钮 =====
        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

    def _load_config(self):
        """从Config读取默认值填充到控件。"""
        # 缓存大小（Config中以字节存储，这里转换为MB显示）
        cache_size_mb = Config.DEFAULT_CACHE_SIZE // (1024 * 1024)
        # 限制在有效范围内
        cache_size_mb = max(1, min(1024, cache_size_mb))
        self.cache_size_spin.setValue(cache_size_mb)
        # 缓存位置
        self.cache_dir_edit.setText(Config.DEFAULT_CACHE_DIR)
        # 下载路径
        self.download_dir_edit.setText(Config.DEFAULT_DOWNLOAD_DIR)

    def _on_browse_cache_dir(self):
        """点击浏览缓存目录按钮：弹出目录选择对话框。"""
        current = self.cache_dir_edit.text().strip()
        start_dir = current if current and os.path.isdir(current) else os.path.expanduser("~")
        dir_path = QFileDialog.getExistingDirectory(
            self, "选择缓存目录", start_dir
        )
        if dir_path:
            self.cache_dir_edit.setText(dir_path)

    def _on_browse_download_dir(self):
        """点击浏览下载目录按钮：弹出目录选择对话框。"""
        current = self.download_dir_edit.text().strip()
        start_dir = current if current and os.path.isdir(current) else os.path.expanduser("~")
        dir_path = QFileDialog.getExistingDirectory(
            self, "选择下载目录", start_dir
        )
        if dir_path:
            self.download_dir_edit.setText(dir_path)

    def get_settings(self):
        """获取当前对话框中的设置值。

        Returns:
            dict: 包含缓存大小（字节）、缓存位置、下载路径
        """
        return {
            # QSpinBox值（MB）转换为字节
            "cache_size": self.cache_size_spin.value() * 1024 * 1024,
            "cache_dir": self.cache_dir_edit.text().strip(),
            "download_dir": self.download_dir_edit.text().strip(),
        }

    def accept(self):
        """点击确认按钮：将配置保存到Config并关闭对话框。"""
        settings = self.get_settings()
        # 更新Config中的配置项
        Config.DEFAULT_CACHE_SIZE = settings["cache_size"]
        Config.DEFAULT_CACHE_DIR = settings["cache_dir"]
        Config.DEFAULT_DOWNLOAD_DIR = settings["download_dir"]
        # 确保目录存在
        if settings["cache_dir"]:
            os.makedirs(settings["cache_dir"], exist_ok=True)
        if settings["download_dir"]:
            os.makedirs(settings["download_dir"], exist_ok=True)
        super().accept()
