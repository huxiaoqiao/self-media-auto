# 养虾计划环境与依赖安装 (Windows PowerShell)

$ErrorActionPreference = "Stop"

Write-Host "============= 启动养虾计划环境与依赖安装 (OpenClaw 初始化) =============" -ForegroundColor Cyan

# 1. 检查并创建 Python 虚拟环境
if (-not (Test-Path ".venv")) {
    Write-Host "[1/3] 正在创建 Python 虚拟环境 .venv ..." -ForegroundColor Yellow
    python -m venv .venv
    
    if (-not $?) {
        Write-Host "❌ 虚拟环境创建失败，请确保安装了 Python 3.10+" -ForegroundColor Red
        exit 1
    }
} else {
    Write-Host "[1/3] 检测到已存在 .venv，跳过创建。" -ForegroundColor Green
}

# 1.1 检查关键外部依赖 (FFmpeg)
if (-not (Get-Command ffmpeg -ErrorAction SilentlyContinue)) {
    Write-Host "⚠️ 警告：系统未检测到 ffmpeg。这可能会导致 ASR (语音转文字) 功能失效。" -ForegroundColor Yellow
    Write-Host "👉 建议安装：scoop install ffmpeg 或从官翻下载并添加到 PATH。" -ForegroundColor Gray
}

# 2. 安装 Python 依赖
Write-Host "[2/3] 正在安装 Python 依赖库..." -ForegroundColor Yellow
if (Get-Command uv -ErrorAction SilentlyContinue) {
    Write-Host "⚡ 检测到 uv，将使用 uv 极速同步依赖..." -ForegroundColor DarkYellow
    uv pip install --python .venv -e .
} else {
    Write-Host "📦 使用原生 pip 安装依赖..." -ForegroundColor DarkYellow
    & .\.venv\Scripts\python -m pip install --upgrade pip
    & .\.venv\Scripts\python -m pip install -e .
}

Write-Host "🌐 正在安装外部自动化组件 (xhs, playwright)..." -ForegroundColor Yellow
& .\.venv\Scripts\python -m pip install xiaohongshu-cli
& .\.venv\Scripts\playwright install chromium


# 3. 安装 Node.js / Bun 依赖
Write-Host "[3/3] 初始化全局 Node.js 组件..." -ForegroundColor Yellow
if (Get-Command bun -ErrorAction SilentlyContinue) {
    bun install -g baoyu-skills
} elseif (Get-Command npm -ErrorAction SilentlyContinue) {
    npm install -g baoyu-skills
} else {
    Write-Host "⚠️ 检测不到 npm 或 bun，将无法执行前端 JavaScript / TS 脚本。" -ForegroundColor DarkRed
}

# 4. 拷贝配置文件范例
if (-not (Test-Path "$HOME\.baoyu-skills")) {
    New-Item -ItemType Directory -Force -Path "$HOME\.baoyu-skills" | Out-Null
}

if (-not (Test-Path "$HOME\.baoyu-skills\.env")) {
    if (Test-Path ".env.example") {
        Copy-Item ".env.example" "$HOME\.baoyu-skills\.env"
        Write-Host "✅ .env 模板已复制到全局配置目录，请填入密钥。" -ForegroundColor Green
    }
}

Write-Host "`n全部自动化框架的依赖骨架处理完成！" -ForegroundColor Cyan
Write-Host "👉 现在您可以直接让 OpenClaw 调用了。"
