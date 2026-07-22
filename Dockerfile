# M3U8 Video Tool Dockerfile
# 用于在Docker容器中构建Linux可执行文件
#
# 使用方式:
#   # 构建镜像
#   docker build -t m3u8-video-tool-builder .
#
#   # 运行构建，将产物挂载到本地dist目录
#   docker run --rm -v "$(pwd)/dist:/app/dist" m3u8-video-tool-builder
#
#   # 构建并运行（需挂载X11显示）
#   docker run --rm -e DISPLAY=$DISPLAY -v /tmp/.X11-unix:/tmp/.X11-unix m3u8-video-tool-builder python main.py

# ===== 第一阶段：构建环境 =====
FROM python:3.11-slim-bookworm AS builder

LABEL maintainer="m3u8-tool"
LABEL description="M3U8视频浏览加速下载工具 - Docker构建环境"

# 设置工作目录
WORKDIR /app

# 安装系统依赖
# - libgl1-mesa-glx: OpenGL支持（ffpyplayer需要）
# - libglib2.0-0: GLib依赖
# - libsm6 libxext6 libxrender1: X11显示支持
# - ffmpeg: 视频合并工具
# - build-essential: 编译依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1-mesa-glx \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender1 \
    ffmpeg \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# 复制依赖文件
COPY requirements.txt .

# 安装Python依赖
RUN pip install --no-cache-dir -r requirements.txt

# 复制项目文件
COPY . .

# 运行PyInstaller打包
# --noconfirm: 不确认覆盖
# --distpath: 指定输出目录
RUN python -m PyInstaller m3u8_tool.spec --noconfirm --distpath /app/dist

# ===== 第二阶段：运行环境（可选，用于分发） =====
FROM debian:bookworm-slim AS runtime

LABEL maintainer="m3u8-tool"
LABEL description="M3U8视频浏览加速下载工具 - 运行环境"

# 安装运行时依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1-mesa-glx \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender1 \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# 设置工作目录
WORKDIR /app

# 从构建阶段复制可执行文件
COPY --from=builder /app/dist/M3U8VideoTool /app/M3U8VideoTool

# 设置可执行权限
RUN chmod +x /app/M3U8VideoTool

# 默认启动命令（仅展示信息，GUI应用需要挂载X11）
CMD ["/app/M3U8VideoTool"]
