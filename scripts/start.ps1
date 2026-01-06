# ============================================================
# 一键启动脚本 (PowerShell)
# ============================================================
# 使用方法: .\start.ps1
# ============================================================

Write-Host "=" -NoNewline -ForegroundColor Cyan
Write-Host ("=" * 59) -ForegroundColor Cyan
Write-Host "   陶瓷车间数字孪生系统 - 一键启动" -ForegroundColor Green
Write-Host "=" -NoNewline -ForegroundColor Cyan
Write-Host ("=" * 59) -ForegroundColor Cyan
Write-Host ""

# 检查Docker是否运行
Write-Host "🔍 检查Docker服务..." -ForegroundColor Yellow
try {
    docker info | Out-Null
    Write-Host "✅ Docker正在运行" -ForegroundColor Green
}
catch {
    Write-Host "❌ Docker未运行，请先启动Docker Desktop" -ForegroundColor Red
    exit 1
}

# 启动Docker Compose服务
Write-Host "`n📦 启动数据库服务 (InfluxDB)..." -ForegroundColor Yellow
docker-compose up -d

if ($LASTEXITCODE -eq 0) {
    Write-Host "✅ 数据库服务启动成功" -ForegroundColor Green
}
else {
    Write-Host "❌ 数据库服务启动失败" -ForegroundColor Red
    exit 1
}

# 等待数据库就绪
Write-Host "`n⏳ 等待数据库服务就绪 (10秒)..." -ForegroundColor Yellow
Start-Sleep -Seconds 10

# 检查Python环境
Write-Host "`n🐍 检查Python环境..." -ForegroundColor Yellow
try {
    python --version
    Write-Host "✅ Python环境正常" -ForegroundColor Green
}
catch {
    Write-Host "❌ 未找到Python，请先安装Python 3.11+" -ForegroundColor Red
    exit 1
}

# 安装依赖
Write-Host "`n📚 检查Python依赖..." -ForegroundColor Yellow
if (Test-Path "requirements.txt") {
    pip install -r requirements.txt --quiet
    Write-Host "✅ 依赖安装完成" -ForegroundColor Green
}
else {
    Write-Host "⚠️  未找到requirements.txt" -ForegroundColor Yellow
}

# 启动后端服务
Write-Host "`n🚀 启动FastAPI后端服务..." -ForegroundColor Yellow
Write-Host "=" -NoNewline -ForegroundColor Cyan
Write-Host ("=" * 59) -ForegroundColor Cyan
Write-Host "📍 API文档: " -NoNewline -ForegroundColor Cyan
Write-Host "http://localhost:8080/docs" -ForegroundColor White
Write-Host "📍 健康检查: " -NoNewline -ForegroundColor Cyan
Write-Host "http://localhost:8080/api/health" -ForegroundColor White
Write-Host "📍 运行模式: " -NoNewline -ForegroundColor Cyan
Write-Host "Mock模式 (无需PLC)" -ForegroundColor White
Write-Host "=" -NoNewline -ForegroundColor Cyan
Write-Host ("=" * 59) -ForegroundColor Cyan
Write-Host "`n按 Ctrl+C 停止服务`n" -ForegroundColor Yellow

python main.py
