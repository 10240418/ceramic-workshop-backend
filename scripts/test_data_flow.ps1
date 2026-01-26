# 数据流完整性测试脚本 (PowerShell版本)
# 测试从PLC到导出API的完整数据流

$baseUrl = "http://localhost:8080"
$testResults = @{
    total = 0
    passed = 0
    failed = 0
    warnings = 0
}

function Write-TestResult {
    param(
        [string]$Name,
        [string]$Status,
        [string]$Message = ""
    )
    
    $testResults.total++
    
    $icon = switch ($Status) {
        "PASS" { "✅"; $testResults.passed++ }
        "FAIL" { "❌"; $testResults.failed++ }
        "WARN" { "⚠️"; $testResults.warnings++ }
        default { "ℹ️" }
    }
    
    Write-Host "$icon $Name`: $Status"
    if ($Message) {
        Write-Host "   $Message"
    }
}

function Write-TestHeader {
    param([string]$Title)
    Write-Host "`n============================================================"
    Write-Host "  $Title"
    Write-Host "============================================================"
}

# 测试1: 系统健康检查
Write-TestHeader "测试1: 系统健康检查"

try {
    $response = Invoke-RestMethod -Uri "$baseUrl/api/health" -Method Get -TimeoutSec 5
    if ($response.success) {
        Write-TestResult "系统健康检查" "PASS" "状态: $($response.data.status)"
    } else {
        Write-TestResult "系统健康检查" "FAIL" $response.error
    }
} catch {
    Write-TestResult "系统健康检查" "FAIL" "请求失败: $_"
}

# 测试2: 实时数据缓存
Write-TestHeader "测试2: 实时数据缓存"

# 测试料仓数据
try {
    $response = Invoke-RestMethod -Uri "$baseUrl/api/hopper/realtime/batch" -Method Get -TimeoutSec 5
    if ($response.success) {
        $deviceCount = $response.data.devices.Count
        Write-TestResult "料仓实时数据" "PASS" "获取到 $deviceCount 个设备"
        
        if ($deviceCount -gt 0) {
            $sample = $response.data.devices[0]
            $hasTemp = $null -ne $sample.temperature
            $hasPower = $null -ne $sample.power
            
            if ($hasTemp -and $hasPower) {
                Write-TestResult "  └─ $($sample.device_id) 数据完整性" "PASS" "包含温度和功率数据"
            } else {
                Write-TestResult "  └─ $($sample.device_id) 数据完整性" "WARN" "数据可能不完整"
            }
        }
    } else {
        Write-TestResult "料仓实时数据" "FAIL" $response.error
    }
} catch {
    Write-TestResult "料仓实时数据" "FAIL" "请求失败: $_"
}

# 测试辊道窑数据
try {
    $response = Invoke-RestMethod -Uri "$baseUrl/api/roller/realtime/formatted" -Method Get -TimeoutSec 5
    if ($response.success) {
        $zoneCount = $response.data.zones.Count
        Write-TestResult "辊道窑实时数据" "PASS" "获取到 $zoneCount 个温区"
        
        if ($response.data.total) {
            $totalPower = $response.data.total.power
            Write-TestResult "  └─ 辊道窑总表" "PASS" "总功率: $totalPower kW"
        } else {
            Write-TestResult "  └─ 辊道窑总表" "WARN" "总表数据为空"
        }
    } else {
        Write-TestResult "辊道窑实时数据" "FAIL" $response.error
    }
} catch {
    Write-TestResult "辊道窑实时数据" "FAIL" "请求失败: $_"
}

# 测试SCR/风机数据
try {
    $response = Invoke-RestMethod -Uri "$baseUrl/api/scr-fan/realtime/batch" -Method Get -TimeoutSec 5
    if ($response.success) {
        $deviceCount = $response.data.devices.Count
        Write-TestResult "SCR/风机实时数据" "PASS" "获取到 $deviceCount 个设备"
    } else {
        Write-TestResult "SCR/风机实时数据" "FAIL" $response.error
    }
} catch {
    Write-TestResult "SCR/风机实时数据" "FAIL" "请求失败: $_"
}

# 测试3: 导出API
Write-TestHeader "测试3: 数据导出API"

$days = 1

# 1. 测试燃气消耗统计
try {
    $response = Invoke-RestMethod -Uri "$baseUrl/api/export/gas-consumption?days=$days" -Method Get -TimeoutSec 10
    if ($response.success) {
        $deviceCount = $response.data.PSObject.Properties.Count
        
        if ($deviceCount -eq 2) {
            Write-TestResult "燃气消耗统计" "PASS" "获取到 $deviceCount 个设备的数据"
            
            foreach ($device in $response.data.PSObject.Properties) {
                $deviceId = $device.Name
                $dailyRecords = $device.Value.daily_records
                if ($dailyRecords.Count -gt 0) {
                    $consumption = $dailyRecords[0].consumption
                    Write-TestResult "  └─ $deviceId" "PASS" "消耗: $consumption m³"
                } else {
                    Write-TestResult "  └─ $deviceId" "WARN" "无数据"
                }
            }
        } else {
            Write-TestResult "燃气消耗统计" "WARN" "设备数量不正确: $deviceCount (期望2个)"
        }
    } else {
        Write-TestResult "燃气消耗统计" "FAIL" $response.error
    }
} catch {
    Write-TestResult "燃气消耗统计" "FAIL" "请求失败: $_"
}

# 2. 测试投料量统计
try {
    $response = Invoke-RestMethod -Uri "$baseUrl/api/export/feeding-amount?days=$days" -Method Get -TimeoutSec 10
    if ($response.success) {
        $hopperCount = $response.data.hoppers.Count
        
        if ($hopperCount -eq 7) {
            Write-TestResult "投料量统计" "PASS" "获取到 $hopperCount 个料仓的数据"
            
            $totalFeeding = 0
            foreach ($hopper in $response.data.hoppers) {
                $deviceId = $hopper.device_id
                $dailyRecords = $hopper.daily_records
                if ($dailyRecords.Count -gt 0) {
                    $feeding = ($dailyRecords | Measure-Object -Property feeding_amount -Sum).Sum
                    $totalFeeding += $feeding
                    if ($feeding -gt 0) {
                        Write-TestResult "  └─ $deviceId" "PASS" "投料: $([math]::Round($feeding, 1)) kg"
                    }
                }
            }
            
            if ($totalFeeding -gt 0) {
                Write-TestResult "  └─ 投料记录检测" "PASS" "总投料量: $([math]::Round($totalFeeding, 1)) kg"
            } else {
                Write-TestResult "  └─ 投料记录检测" "WARN" "未检测到投料事件（可能是正常情况）"
            }
        } else {
            Write-TestResult "投料量统计" "WARN" "料仓数量不正确: $hopperCount (期望7个)"
        }
    } else {
        Write-TestResult "投料量统计" "FAIL" $response.error
    }
} catch {
    Write-TestResult "投料量统计" "FAIL" "请求失败: $_"
}

# 3. 测试电量统计（单个设备）
try {
    $deviceId = "short_hopper_1"
    $response = Invoke-RestMethod -Uri "$baseUrl/api/export/electricity?device_id=$deviceId&days=$days" -Method Get -TimeoutSec 10
    if ($response.success) {
        $dailyRecords = $response.data.daily_records
        if ($dailyRecords.Count -gt 0) {
            $consumption = $dailyRecords[0].consumption
            $runtime = [math]::Round($dailyRecords[0].runtime_hours, 1)
            Write-TestResult "电量统计 ($deviceId)" "PASS" "消耗: $consumption kWh, 运行: ${runtime}h"
        } else {
            Write-TestResult "电量统计 ($deviceId)" "WARN" "无数据"
        }
    } else {
        Write-TestResult "电量统计 ($deviceId)" "FAIL" $response.error
    }
} catch {
    Write-TestResult "电量统计 ($deviceId)" "FAIL" "请求失败: $_"
}

# 4. 测试辊道窑总表电量统计
try {
    $deviceId = "roller_kiln_total"
    $response = Invoke-RestMethod -Uri "$baseUrl/api/export/electricity?device_id=$deviceId&days=$days" -Method Get -TimeoutSec 10
    if ($response.success) {
        $dailyRecords = $response.data.daily_records
        if ($dailyRecords.Count -gt 0) {
            $consumption = $dailyRecords[0].consumption
            $runtime = [math]::Round($dailyRecords[0].runtime_hours, 1)
            Write-TestResult "电量统计 (辊道窑总表)" "PASS" "消耗: $consumption kWh, 运行: ${runtime}h"
        } else {
            Write-TestResult "电量统计 (辊道窑总表)" "WARN" "无数据"
        }
    } else {
        Write-TestResult "电量统计 (辊道窑总表)" "FAIL" $response.error
    }
} catch {
    Write-TestResult "电量统计 (辊道窑总表)" "FAIL" "请求失败: $_"
}

# 5. 测试运行时长统计
try {
    $response = Invoke-RestMethod -Uri "$baseUrl/api/export/runtime?days=$days" -Method Get -TimeoutSec 15
    if ($response.success) {
        $deviceCount = $response.data.devices.Count
        
        if ($deviceCount -ge 20) {
            Write-TestResult "运行时长统计" "PASS" "获取到 $deviceCount 个设备的数据"
            
            # 检查辊道窑总表
            $rollerTotal = $response.data.devices | Where-Object { $_.device_id -eq "roller_kiln_total" }
            if ($rollerTotal) {
                $runtime = [math]::Round($rollerTotal.daily_records[0].runtime_hours, 1)
                Write-TestResult "  └─ 辊道窑总表运行时长" "PASS" "${runtime}h"
            } else {
                Write-TestResult "  └─ 辊道窑总表运行时长" "WARN" "未找到总表数据"
            }
        } else {
            Write-TestResult "运行时长统计" "WARN" "设备数量不足: $deviceCount (期望≥20个)"
        }
    } else {
        Write-TestResult "运行时长统计" "FAIL" $response.error
    }
} catch {
    Write-TestResult "运行时长统计" "FAIL" "请求失败: $_"
}

# 打印测试摘要
Write-TestHeader "测试摘要"

$total = $testResults.total
$passed = $testResults.passed
$failed = $testResults.failed
$warnings = $testResults.warnings

if ($total -gt 0) {
    $passRate = [math]::Round(($passed / $total) * 100, 1)
} else {
    $passRate = 0
}

Write-Host "总测试数: $total"
Write-Host "✅ 通过: $passed ($passRate%)"
Write-Host "❌ 失败: $failed"
Write-Host "⚠️  警告: $warnings"

if ($failed -eq 0) {
    Write-Host "`n🎉 所有测试通过！数据流完整性验证成功！"
    exit 0
} else {
    Write-Host "`n⚠️  有 $failed 个测试失败，请检查日志"
    exit 1
}

