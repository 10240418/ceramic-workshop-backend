@echo off
chcp 65001 >nul
setlocal

echo ========================================
echo  WorkshopBackend - PyInstaller 打包脚本
echo ========================================
echo.

REM 1. 检查 PyInstaller
python -c "import PyInstaller" 2>nul
if errorlevel 1 (
    echo [1/5] PyInstaller 未安装，开始安装...
    pip install pyinstaller
    if errorlevel 1 (
        echo [ERROR] PyInstaller 安装失败
        pause
        exit /b 1
    )
) else (
    echo [1/5] PyInstaller 已安装
)

echo [2/5] 清理旧构建目录...
if exist build rmdir /s /q build
if exist dist\WorkshopBackend rmdir /s /q dist\WorkshopBackend

echo [3/5] 开始打包...
pyinstaller build_exe.spec --clean --noconfirm
if errorlevel 1 (
    echo [ERROR] 打包失败，请检查输出日志
    pause
    exit /b 1
)

echo [4/5] 准备 dist 运行目录...
if not exist dist\WorkshopBackend\configs mkdir dist\WorkshopBackend\configs
if not exist dist\WorkshopBackend\data mkdir dist\WorkshopBackend\data
if not exist dist\WorkshopBackend\logs mkdir dist\WorkshopBackend\logs

xcopy /E /I /Y configs dist\WorkshopBackend\configs >nul
if exist .env copy /Y .env dist\WorkshopBackend\.env >nul

echo [5/5] 打包完成

echo.
echo 目录结构：
echo   dist\WorkshopBackend\
echo     ├── WorkshopBackend.exe
echo     ├── .env
echo     ├── configs\
echo     ├── data\
echo     ├── logs\
echo     └── _internal\
echo.
echo 可执行文件: dist\WorkshopBackend\WorkshopBackend.exe

echo.
endlocal
pause
