#!/bin/bash

# 自媒体工作流环境与依赖安装 (Ubuntu / Linux / macOS)

echo "============= 启动自媒体工作流环境与依赖安装 (OpenClaw 初始化) ============="

# 1. 检查并创建 Python 虚拟环境
if [ ! -d ".venv" ]; then
    echo "[1/3] 正在创建 Python 虚拟环境 .venv ..."
    python3 -m venv .venv
    
    if [ $? -ne 0 ]; then
        echo "❌ 虚拟环境创建失败，请确保安装了 python3-venv 和 Python 3.10+"
        exit 1
    fi
else
    echo "[1/3] 检测到已存在 .venv，跳过创建。"
fi

# 1.1 检查关键外部依赖 (FFmpeg)
if ! command -v ffmpeg &> /dev/null; then
    echo "⚠️ 警告：系统未检测到 ffmpeg。这可能会导致 ASR (语音转文字) 功能失效。"
    echo "👉 建议安装：sudo apt install ffmpeg (Ubuntu) 或 brew install ffmpeg (macOS)"
fi

# 2. 安装 Python 依赖
echo "[2/3] 正在安装 Python 依赖库..."

if command -v uv &> /dev/null; then
    echo "⚡ 检测到 uv，将使用 uv 极速同步依赖..."
    uv pip install --python .venv -e .
else
    echo "📦 使用原生 pip 安装依赖..."
    ./.venv/bin/python -m pip install --upgrade pip
    ./.venv/bin/python -m pip install -e .
fi

echo "🌐 正在安装外部自动化组件 (xhs, playwright)..."
./.venv/bin/python -m pip install xiaohongshu-cli
./.venv/bin/playwright install chromium

# 3. 安装 Node.js / Bun 依赖
echo "[3/3] 初始化全局 Node.js 组件..."

if command -v bun &> /dev/null; then
    echo "⚡ 使用 Bun 安装全局技能包..."
    bun install -g baoyu-skills
elif command -v npm &> /dev/null; then
    echo "📦 使用 NPM 安装全局技能包..."
    npm install -g baoyu-skills
else
    echo "⚠️ 检测不到 npm 或 bun，将无法执行前端 JavaScript / TS 脚本。"
fi

# 4. 拷贝配置文件范例
if [ ! -d "$HOME/.baoyu-skills" ]; then
    mkdir -p "$HOME/.baoyu-skills"
fi

if [ ! -f "$HOME/.baoyu-skills/.env" ]; then
    if [ -f ".env.example" ]; then
        cp .env.example "$HOME/.baoyu-skills/.env"
        echo "✅ .env 模板已复制到全局配置目录 $HOME/.baoyu-skills/.env，请填入密钥。"
    fi
fi

echo ""
echo "全部自动化框架的依赖骨架处理完成！"
echo "👉 现在您可以直接让 OpenClaw 调用了。"
