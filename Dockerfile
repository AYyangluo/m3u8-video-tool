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

FROM python:3.11-slim-bookworm

LABEL maintainer="m3u8-tool"
LABEL description="M3U8视频浏览加速下载工具 - Docker构建环境"

WORKDIR /app

# 清除新格式文件，直接写入传统阿里云源
RUN rm -f /etc/apt/sources.list.d/debian.sources && \
    echo "deb https://mirrors.aliyun.com/debian bookworm main non-free non-free-firmware" > /etc/apt/sources.list && \
    echo "deb https://mirrors.aliyun.com/debian-security bookworm-security main non-free non-free-firmware" >> /etc/apt/sources.list && \
    echo "deb https://mirrors.aliyun.com/debian bookworm-updates main non-free non-free-firmware" >> /etc/apt/sources.list && \
    apt-get update && apt-get install -y gcc

# 安装系统依赖
# - libgl1-mesa-glx: OpenGL支持（ffpyplayer需要）
# - libglib2.0-0: GLib依赖
# - libsm6 libxext6 libxrender1: X11显示支持（PyQt6打包需要）
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
# 使用阿里云PyPI镜像源，增加超时时间和重试次数，应对网络不稳定
RUN pip install --no-cache-dir \
    --timeout 120 \
    --retries 5 \
    -i https://mirrors.aliyun.com/pypi/simple/ \
    --trusted-host mirrors.aliyun.com \
    -r requirements.txt

# 复制项目文件
COPY . .

# 容器启动时执行打包（产物输出到 /app/dist，通过 volume 挂载到宿主机）
ENTRYPOINT ["python", "-m", "PyInstaller", "m3u8_tool.spec", "--noconfirm", "--distpath", "/app/dist"]
