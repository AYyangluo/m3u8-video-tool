# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller 打包配置文件。

用于将 M3U8 视频浏览加速下载工具打包为可执行程序。
支持 Windows 和 Linux 平台。
入口: main.py
Windows 输出: dist/M3U8VideoTool.exe
Linux 输出: dist/M3U8VideoTool
"""

import sys
from PyInstaller.utils.hooks import (
    collect_submodules,
    collect_data_files,
    collect_dynamic_libs,
)

block_cipher = None

# 平台判断
IS_WINDOWS = sys.platform == 'win32'

# ===== 收集 ffpyplayer 的子模块、数据文件与动态库（依赖的 dll 等） =====
ffpyplayer_hiddenimports = collect_submodules('ffpyplayer')
ffpyplayer_datas = collect_data_files('ffpyplayer')
ffpyplayer_binaries = collect_dynamic_libs('ffpyplayer')

# ===== 收集 PyQt6 的子模块与数据文件（插件、翻译等） =====
pyqt6_hiddenimports = collect_submodules('PyQt6')
pyqt6_datas = collect_data_files('PyQt6')

# ===== 收集本地 src 包的所有子模块，确保被正确包含 =====
src_hiddenimports = collect_submodules('src')

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=ffpyplayer_binaries,
    datas=ffpyplayer_datas + pyqt6_datas,
    hiddenimports=(
        # ffpyplayer 相关模块
        [
            'ffpyplayer',
            'ffpyplayer.player',
            'ffpyplayer.tools',
        ]
        + ffpyplayer_hiddenimports
        # PyQt6 相关模块
        + [
            'PyQt6.QtCore',
            'PyQt6.QtGui',
            'PyQt6.QtWidgets',
        ]
        + pyqt6_hiddenimports
        # 本地 src 包
        + src_hiddenimports
    ),
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='M3U8VideoTool',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=IS_WINDOWS,          # Linux下UPX压缩易破坏二进制，仅Windows启用
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,            # 调试期：Windows/Linux 均开启控制台，便于捕获崩溃输出
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
