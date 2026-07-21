@echo off
chcp 65001 >nul
echo ===== M3U8 Video Tool 打包脚本 =====
echo.

echo [1/3] 安装依赖...
pip install -r requirements.txt
if errorlevel 1 (
    echo 依赖安装失败！
    exit /b 1
)

echo.
echo [2/3] 清理旧的构建文件...
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist

echo.
echo [3/3] 开始打包...
pyinstaller m3u8_tool.spec --noconfirm
if errorlevel 1 (
    echo 打包失败！
    exit /b 1
)

echo.
echo ===== 打包完成 =====
echo 可执行文件位于: dist\M3U8VideoTool.exe
pause
