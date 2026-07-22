#!/usr/bin/env bash
# M3U8 Video Tool Linux 打包脚本
# 用法: ./build.sh

set -e

# 获取脚本所在目录，确保工作目录正确
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo "===== M3U8 Video Tool 打包脚本 (Linux) ====="
echo ""

# ===== 检查 spec 文件 =====
SPEC_FILE="$SCRIPT_DIR/m3u8_tool.spec"
if [ ! -f "$SPEC_FILE" ]; then
    echo -e "${RED}错误: 找不到 spec 文件: $SPEC_FILE${NC}"
    exit 1
fi

# ===== [1/3] 安装依赖 =====
echo -e "${YELLOW}[1/3] 安装依赖...${NC}"

# 优先使用 python3，其次 python
if command -v python3 &> /dev/null; then
    PYTHON=python3
elif command -v python &> /dev/null; then
    PYTHON=python
else
    echo -e "${RED}错误: 未找到 Python 解释器${NC}"
    exit 1
fi

echo "使用 Python: $($PYTHON --version)"

# 创建虚拟环境（可选，默认关闭，如需启用取消注释）
# if [ ! -d "venv" ]; then
#     echo "创建虚拟环境..."
#     $PYTHON -m venv venv
# fi
# source venv/bin/activate

$PYTHON -m pip install -r requirements.txt
if [ $? -ne 0 ]; then
    echo -e "${RED}依赖安装失败！${NC}"
    exit 1
fi

# ===== [2/3] 清理旧的构建文件 =====
echo ""
echo -e "${YELLOW}[2/3] 清理旧的构建文件...${NC}"
if [ -d "build" ]; then
    rm -rf build
    echo "已清理 build 目录"
fi
if [ -d "dist" ]; then
    rm -rf dist
    echo "已清理 dist 目录"
fi

# ===== [3/3] 开始打包 =====
echo ""
echo -e "${YELLOW}[3/3] 开始打包...${NC}"

# 优先使用 python -m PyInstaller，避免 pip --user 安装导致的路径问题
$PYTHON -m PyInstaller "$SPEC_FILE" --noconfirm
if [ $? -ne 0 ]; then
    echo -e "${RED}打包失败！${NC}"
    exit 1
fi

# ===== 完成 =====
echo ""
echo -e "${GREEN}===== 打包完成 =====${NC}"
echo "可执行文件位于: dist/M3U8VideoTool"
echo ""
echo "运行方式:"
echo "  ./dist/M3U8VideoTool"
