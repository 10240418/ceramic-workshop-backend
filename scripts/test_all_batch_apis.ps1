# API Batch Test Script
# Usage: Ensure backend is running (python main.py)

Write-Host "`n======================================================================" -ForegroundColor Green
Write-Host "  Batch API Test - Ceramic Workshop Backend" -ForegroundColor Green
Write-Host "======================================================================`n" -ForegroundColor Green

# Check service health
try {
  Write-Host "[1/5] Health Check..." -ForegroundColor Cyan
  $health = Invoke-WebRequest -Uri "http://localhost:8080/api/health" -UseBasicParsing -ErrorAction Stop | ConvertFrom-Json
  Write-Host "  OK - Service: $($health.data.message)" -ForegroundColor Green
  Write-Host ""
}
catch {
  Write-Host "  ERROR - Backend not running! Please start: python main.py" -ForegroundColor Red
  exit 1
}

# Test 1: Hopper Batch API
Write-Host "[2/5] Test Hopper Batch API (/api/hopper/realtime/batch)..." -ForegroundColor Cyan
try {
  $hoppers = Invoke-WebRequest -Uri "http://localhost:8080/api/hopper/realtime/batch" -UseBasicParsing | ConvertFrom-Json
  Write-Host "  OK - Success: $($hoppers.success)" -ForegroundColor Green
  Write-Host "  Total Hoppers: $($hoppers.data.total)" -ForegroundColor Yellow
  Write-Host "  First Hopper ($($hoppers.data.devices[0].device_id)):" -ForegroundColor Magenta
  Write-Host "     - Timestamp: $($hoppers.data.devices[0].timestamp)" -ForegroundColor White
  Write-Host "     - Modules: $($hoppers.data.devices[0].modules.Count)" -ForegroundColor White
  if ($hoppers.data.devices[0].modules.elec) {
    Write-Host "       + Electricity - Power: $($hoppers.data.devices[0].modules.elec.fields.Pt) kW" -ForegroundColor White
  }
  if ($hoppers.data.devices[0].modules.temp) {
    Write-Host "       + Temperature: $($hoppers.data.devices[0].modules.temp.fields.temperature) C" -ForegroundColor White
  }
  if ($hoppers.data.devices[0].modules.weight) {
    Write-Host "       + Weight: $($hoppers.data.devices[0].modules.weight.fields.weight) kg" -ForegroundColor White
  }
  Write-Host ""
}
catch {
  Write-Host "  ERROR - Test Failed: $($_.Exception.Message)" -ForegroundColor Red
  Write-Host ""
}

# Test 2: Roller Kiln Formatted API
Write-Host "[3/5] Test Roller Kiln Formatted API (/api/roller/realtime/formatted)..." -ForegroundColor Cyan
try {
  $roller = Invoke-WebRequest -Uri "http://localhost:8080/api/roller/realtime/formatted" -UseBasicParsing | ConvertFrom-Json
  Write-Host "  OK - Success: $($roller.success)" -ForegroundColor Green
  Write-Host "  Roller Kiln: $($roller.data.device_id)" -ForegroundColor Yellow
  Write-Host "  Total Zones: $($roller.data.zones.Count)" -ForegroundColor Yellow
  Write-Host "  Zone1 Data:" -ForegroundColor Magenta
  Write-Host "     - Temperature: $($roller.data.zones[0].temperature) C" -ForegroundColor White
  Write-Host "     - Power: $($roller.data.zones[0].power) kW" -ForegroundColor White
  Write-Host ""
}
catch {
  Write-Host "  ERROR - Test Failed: $($_.Exception.Message)" -ForegroundColor Red
  Write-Host ""
}

# Test 3: SCR Batch API
Write-Host "[4/5] Test SCR Batch API (/api/scr/realtime/batch)..." -ForegroundColor Cyan
try {
  $scr = Invoke-WebRequest -Uri "http://localhost:8080/api/scr/realtime/batch" -UseBasicParsing | ConvertFrom-Json
  Write-Host "  OK - Success: $($scr.success)" -ForegroundColor Green
  Write-Host "  Total SCR Devices: $($scr.data.total)" -ForegroundColor Yellow
  Write-Host "  SCR_1 Data:" -ForegroundColor Magenta
  Write-Host "     - Timestamp: $($scr.data.devices[0].timestamp)" -ForegroundColor White
  Write-Host "     - Modules: $($scr.data.devices[0].modules.Count)" -ForegroundColor White
  if ($scr.data.devices[0].modules.elec) {
    Write-Host "       + Electricity - Power: $($scr.data.devices[0].modules.elec.fields.Pt) kW" -ForegroundColor White
  }
  if ($scr.data.devices[0].modules.gas) {
    Write-Host "       + Gas - Flow Rate: $($scr.data.devices[0].modules.gas.fields.flow_rate) m3/h" -ForegroundColor White
  }
  Write-Host ""
}
catch {
  Write-Host "  ERROR - Test Failed: $($_.Exception.Message)" -ForegroundColor Red
  Write-Host ""
}

# Test 4: Fan Batch API
Write-Host "[5/5] Test Fan Batch API (/api/fan/realtime/batch)..." -ForegroundColor Cyan
try {
  $fan = Invoke-WebRequest -Uri "http://localhost:8080/api/fan/realtime/batch" -UseBasicParsing | ConvertFrom-Json
  Write-Host "  OK - Success: $($fan.success)" -ForegroundColor Green
  Write-Host "  Total Fan Devices: $($fan.data.total)" -ForegroundColor Yellow
  Write-Host "  Fan_1 Data:" -ForegroundColor Magenta
  Write-Host "     - Timestamp: $($fan.data.devices[0].timestamp)" -ForegroundColor White
  Write-Host "     - Modules: $($fan.data.devices[0].modules.Count)" -ForegroundColor White
  if ($fan.data.devices[0].modules.elec) {
    Write-Host "       + Electricity - Power: $($fan.data.devices[0].modules.elec.fields.Pt) kW" -ForegroundColor White
  }
  Write-Host ""
}
catch {
  Write-Host "  ERROR - Test Failed: $($_.Exception.Message)" -ForegroundColor Red
  Write-Host ""
}

# Test 5: SCR+Fan Unified Batch API (Recommended)
Write-Host "======================================================================" -ForegroundColor Yellow
Write-Host "  RECOMMENDED: SCR+Fan Unified Batch Query" -ForegroundColor Yellow
Write-Host "======================================================================" -ForegroundColor Yellow
Write-Host ""
Write-Host "Test SCR+Fan Unified API (/api/scr-fan/realtime/batch)..." -ForegroundColor Cyan
try {
  $all = Invoke-WebRequest -Uri "http://localhost:8080/api/scr-fan/realtime/batch" -UseBasicParsing | ConvertFrom-Json
  Write-Host "  OK - Success: $($all.success)" -ForegroundColor Green
  Write-Host "  Total Devices: $($all.data.total)" -ForegroundColor Yellow
  Write-Host "     - SCR: $($all.data.scr.total) devices" -ForegroundColor Cyan
  Write-Host "     - Fan: $($all.data.fan.total) devices" -ForegroundColor Cyan
  Write-Host ""
    
  Write-Host "  SCR_1 Detail:" -ForegroundColor Magenta
  $all.data.scr.devices[0] | ConvertTo-Json -Depth 6
  Write-Host ""
    
  Write-Host "  Fan_1 Detail:" -ForegroundColor Magenta
  $all.data.fan.devices[0] | ConvertTo-Json -Depth 6
  Write-Host ""
}
catch {
  Write-Host "  ERROR - Test Failed: $($_.Exception.Message)" -ForegroundColor Red
  Write-Host ""
}

# Summary
Write-Host "======================================================================" -ForegroundColor Green
Write-Host "  Test Complete!" -ForegroundColor Green
Write-Host "======================================================================" -ForegroundColor Green
Write-Host ""
Write-Host "Frontend Integration Recommendations:" -ForegroundColor Yellow
Write-Host "  1. Hoppers: GET /api/hopper/realtime/batch (9 devices -> 1 request)" -ForegroundColor White
Write-Host "  2. Roller: GET /api/roller/realtime/formatted (6 zones -> frontend-friendly)" -ForegroundColor White
Write-Host "  3. SCR+Fan: GET /api/scr-fan/realtime/batch (4 devices -> 1 request)" -ForegroundColor White
Write-Host ""
Write-Host "Performance: 14 API calls -> 3 calls (78% reduction)" -ForegroundColor Green
Write-Host ""
