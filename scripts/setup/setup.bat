@echo off
chcp 65001 >nul
echo ========================================================
echo 初始化自媒体工作流依赖环境 (OpenClaw 初始化脚本)
echo ========================================================

REM 1. 检查并创建 Python 虚拟环境
if not exist ".venv" (
    echo [1/3] 正在创建 Python 虚拟环境 .venv ...
    python -m venv .venv
    if errorlevel 1 (
        echo ❌ 虚拟环境创建失败，请确保安装了 Python 3.10+
        exit /b 1
    )
) else (
    echo [1/3] 检测到已存在 .venv，跳过创建。
)

REM 2. 安装 Python 依赖
echo [2/3] 正在安装 Python 依赖库...
REM 尝试使用 uv (如果安装了的话速度更快)，否则使用 pip
where uv >nul 2>&1
if %ERRORLEVEL% equ 0 (
    echo ⚡ 检测到 uv，将使用 uv 安装依赖...
    uv pip install --python .venv -e .
) else (
    echo 📦 使用原生 pip 安装依赖...
    .venv\Scripts\python -m pip install --upgrade pip
    .venv\Scripts\python -m pip install -e .
)

echo 🌐 正在安装外部自动化库 (xhs, playwright)...
.venv\Scripts\python -m pip install xiaohongshu-cli
.venv\Scripts\playwright install chromium

REM 3. 安装 Node.js / Bun 依赖
echo [3/3] 正在检查和安装 Node.js(bun) 依赖...
where bun >nul 2>&1
if %ERRORLEVEL% equ 0 (
    echo ⚡ 使用 Bun 安装全局技能包...
    bun install -g baoyu-skills
) else (
    where npm >nul 2>&1
    if %ERRORLEVEL% equ 0 (
        echo 📦 使用 NPM 安装全局技能包...
        npm install -g baoyu-skills
    ) else (
        echo ⚠️ 未检测到 Bun 或 NPM，跳过 JS 包安装，后续由于 Node 工具链缺失部分功能可能无法使用。
    )
)

echo ========================================================
echo ✅ 环境初始化完成！OpenClaw 现可调用该工作流。
echo ========================================================
