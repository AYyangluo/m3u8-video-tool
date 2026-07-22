# M3U8视频浏览加速下载工具

Windows平台专用的m3u8视频工具，支持在线播放、倍速调节和下载。

## 环境要求
- Windows 10及以上
- Python 3.9+
- ffmpeg（用于视频合并，需在系统PATH中或手动指定路径）

## 安装依赖
```bash
pip install -r requirements.txt
```

## 运行
```bash
python main.py
```

## 打包

### Windows
双击运行 `build.bat` 或执行：
```bash
pyinstaller m3u8_tool.spec --noconfirm
```
打包后的可执行文件位于 `dist/M3U8VideoTool.exe`

### Linux
运行 `./build.sh` 或执行：
```bash
chmod +x build.sh
./build.sh
```
打包后的可执行文件位于 `dist/M3U8VideoTool`

## 功能
- m3u8视频在线播放
- 播放速度调节（0.5x - 2x）
- 视频下载与合并
- 下载进度显示
- 暂停/继续/取消下载
- 自定义播放缓存大小及缓存位置
