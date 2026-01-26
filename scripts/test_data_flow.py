#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
数据流完整性测试脚本

测试从PLC到导出API的完整数据流：
1. 检查InfluxDB连接
2. 验证数据存储（sensor_data）
3. 验证投料记录（feeding_records）
4. 测试5个导出API
"""

import requests
import sys
from datetime import datetime, timedelta
from typing import Dict, Any

# 后端地址
BASE_URL = "http://localhost:8080"

# 测试结果统计
test_results = {
    "total": 0,
    "passed": 0,
    "failed": 0,
    "warnings": 0
}


def print_header(title: str):
    """打印测试标题"""
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")


def print_test(name: str, status: str, message: str = ""):
    """打印测试结果"""
    test_results["total"] += 1
    
    if status == "PASS":
        icon = "✅"
        test_results["passed"] += 1
    elif status == "FAIL":
        icon = "❌"
        test_results["failed"] += 1
    elif status == "WARN":
        icon = "⚠️"
        test_results["warnings"] += 1
    else:
        icon = "ℹ️"
    
    print(f"{icon} {name}: {status}")
    if message:
        print(f"   {message}")


def test_health_check():
    """测试1: 健康检查"""
    print_header("测试1: 系统健康检查")
    
    try:
        response = requests.get(f"{BASE_URL}/api/health", timeout=5)
        data = response.json()
        
        if data.get("success"):
            print_test("系统健康检查", "PASS", f"状态: {data.get('data', {}).get('status', 'unknown')}")
            
            # 检查PLC连接
            plc_status = data.get("data", {}).get("plc_connected", False)
            if plc_status:
                print_test("PLC连接", "PASS")
            else:
                print_test("PLC连接", "WARN", "PLC未连接（可能使用Mock模式）")
            
            # 检查InfluxDB连接
            influx_status = data.get("data", {}).get("influxdb_connected", False)
            if influx_status:
                print_test("InfluxDB连接", "PASS")
            else:
                print_test("InfluxDB连接", "FAIL", "InfluxDB未连接")
                return False
            
            return True
        else:
            print_test("系统健康检查", "FAIL", data.get("error", "未知错误"))
            return False
            
    except Exception as e:
        print_test("系统健康检查", "FAIL", f"请求失败: {str(e)}")
        return False


def test_realtime_data():
    """测试2: 实时数据缓存"""
    print_header("测试2: 实时数据缓存")
    
    # 测试料仓数据
    try:
        response = requests.get(f"{BASE_URL}/api/hopper/realtime/batch", timeout=5)
        data = response.json()
        
        if data.get("success"):
            devices = data.get("data", {}).get("devices", [])
            print_test("料仓实时数据", "PASS", f"获取到 {len(devices)} 个设备")
            
            # 检查是否有数据
            if len(devices) > 0:
                sample = devices[0]
                device_id = sample.get("device_id", "unknown")
                has_temp = "temperature" in sample
                has_power = "power" in sample
                
                if has_temp and has_power:
                    print_test(f"  └─ {device_id} 数据完整性", "PASS", "包含温度和功率数据")
                else:
                    print_test(f"  └─ {device_id} 数据完整性", "WARN", "数据可能不完整")
        else:
            print_test("料仓实时数据", "FAIL", data.get("error", "未知错误"))
            
    except Exception as e:
        print_test("料仓实时数据", "FAIL", f"请求失败: {str(e)}")
    
    # 测试辊道窑数据
    try:
        response = requests.get(f"{BASE_URL}/api/roller/realtime/formatted", timeout=5)
        data = response.json()
        
        if data.get("success"):
            zones = data.get("data", {}).get("zones", [])
            total = data.get("data", {}).get("total", {})
            
            print_test("辊道窑实时数据", "PASS", f"获取到 {len(zones)} 个温区")
            
            if total:
                print_test("  └─ 辊道窑总表", "PASS", f"总功率: {total.get('power', 0)} kW")
            else:
                print_test("  └─ 辊道窑总表", "WARN", "总表数据为空")
        else:
            print_test("辊道窑实时数据", "FAIL", data.get("error", "未知错误"))
            
    except Exception as e:
        print_test("辊道窑实时数据", "FAIL", f"请求失败: {str(e)}")
    
    # 测试SCR/风机数据
    try:
        response = requests.get(f"{BASE_URL}/api/scr-fan/realtime/batch", timeout=5)
        data = response.json()
        
        if data.get("success"):
            devices = data.get("data", {}).get("devices", [])
            print_test("SCR/风机实时数据", "PASS", f"获取到 {len(devices)} 个设备")
        else:
            print_test("SCR/风机实时数据", "FAIL", data.get("error", "未知错误"))
            
    except Exception as e:
        print_test("SCR/风机实时数据", "FAIL", f"请求失败: {str(e)}")


def test_export_apis():
    """测试3: 导出API"""
    print_header("测试3: 数据导出API")
    
    # 测试参数
    days = 1
    
    # 1. 测试燃气消耗统计
    try:
        response = requests.get(f"{BASE_URL}/api/export/gas-consumption?days={days}", timeout=10)
        data = response.json()
        
        if data.get("success"):
            devices = data.get("data", {})
            device_count = len(devices)
            
            if device_count == 2:  # 应该有2个SCR设备
                print_test("燃气消耗统计", "PASS", f"获取到 {device_count} 个设备的数据")
                
                # 检查数据完整性
                for device_id, device_data in devices.items():
                    daily_records = device_data.get("daily_records", [])
                    if daily_records:
                        sample = daily_records[0]
                        consumption = sample.get("consumption", 0)
                        print_test(f"  └─ {device_id}", "PASS", f"消耗: {consumption} m³")
                    else:
                        print_test(f"  └─ {device_id}", "WARN", "无数据")
            else:
                print_test("燃气消耗统计", "WARN", f"设备数量不正确: {device_count} (期望2个)")
        else:
            print_test("燃气消耗统计", "FAIL", data.get("error", "未知错误"))
            
    except Exception as e:
        print_test("燃气消耗统计", "FAIL", f"请求失败: {str(e)}")
    
    # 2. 测试投料量统计
    try:
        response = requests.get(f"{BASE_URL}/api/export/feeding-amount?days={days}", timeout=10)
        data = response.json()
        
        if data.get("success"):
            hoppers = data.get("data", {}).get("hoppers", [])
            
            if len(hoppers) == 7:  # 应该有7个料仓（排除no_hopper）
                print_test("投料量统计", "PASS", f"获取到 {len(hoppers)} 个料仓的数据")
                
                # 检查是否有投料记录
                total_feeding = 0
                for hopper in hoppers:
                    device_id = hopper.get("device_id", "unknown")
                    daily_records = hopper.get("daily_records", [])
                    if daily_records:
                        feeding = sum(r.get("feeding_amount", 0) for r in daily_records)
                        total_feeding += feeding
                        if feeding > 0:
                            print_test(f"  └─ {device_id}", "PASS", f"投料: {feeding:.1f} kg")
                
                if total_feeding > 0:
                    print_test("  └─ 投料记录检测", "PASS", f"总投料量: {total_feeding:.1f} kg")
                else:
                    print_test("  └─ 投料记录检测", "WARN", "未检测到投料事件（可能是正常情况）")
            else:
                print_test("投料量统计", "WARN", f"料仓数量不正确: {len(hoppers)} (期望7个)")
        else:
            print_test("投料量统计", "FAIL", data.get("error", "未知错误"))
            
    except Exception as e:
        print_test("投料量统计", "FAIL", f"请求失败: {str(e)}")
    
    # 3. 测试电量统计（单个设备）
    try:
        device_id = "short_hopper_1"
        response = requests.get(
            f"{BASE_URL}/api/export/electricity?device_id={device_id}&days={days}", 
            timeout=10
        )
        data = response.json()
        
        if data.get("success"):
            device_data = data.get("data", {})
            daily_records = device_data.get("daily_records", [])
            
            if daily_records:
                sample = daily_records[0]
                consumption = sample.get("consumption", 0)
                runtime = sample.get("runtime_hours", 0)
                
                print_test(f"电量统计 ({device_id})", "PASS", 
                          f"消耗: {consumption} kWh, 运行: {runtime:.1f}h")
            else:
                print_test(f"电量统计 ({device_id})", "WARN", "无数据")
        else:
            print_test(f"电量统计 ({device_id})", "FAIL", data.get("error", "未知错误"))
            
    except Exception as e:
        print_test(f"电量统计 ({device_id})", "FAIL", f"请求失败: {str(e)}")
    
    # 4. 测试辊道窑总表电量统计
    try:
        device_id = "roller_kiln_total"
        response = requests.get(
            f"{BASE_URL}/api/export/electricity?device_id={device_id}&days={days}", 
            timeout=10
        )
        data = response.json()
        
        if data.get("success"):
            device_data = data.get("data", {})
            daily_records = device_data.get("daily_records", [])
            
            if daily_records:
                sample = daily_records[0]
                consumption = sample.get("consumption", 0)
                runtime = sample.get("runtime_hours", 0)
                
                print_test(f"电量统计 (辊道窑总表)", "PASS", 
                          f"消耗: {consumption} kWh, 运行: {runtime:.1f}h")
            else:
                print_test(f"电量统计 (辊道窑总表)", "WARN", "无数据")
        else:
            print_test(f"电量统计 (辊道窑总表)", "FAIL", data.get("error", "未知错误"))
            
    except Exception as e:
        print_test(f"电量统计 (辊道窑总表)", "FAIL", f"请求失败: {str(e)}")
    
    # 5. 测试运行时长统计
    try:
        response = requests.get(f"{BASE_URL}/api/export/runtime?days={days}", timeout=15)
        data = response.json()
        
        if data.get("success"):
            devices = data.get("data", {}).get("devices", [])
            
            if len(devices) >= 20:  # 应该有至少20个设备
                print_test("运行时长统计", "PASS", f"获取到 {len(devices)} 个设备的数据")
                
                # 检查辊道窑总表
                roller_total = next((d for d in devices if d.get("device_id") == "roller_kiln_total"), None)
                if roller_total:
                    runtime = roller_total.get("daily_records", [{}])[0].get("runtime_hours", 0)
                    print_test("  └─ 辊道窑总表运行时长", "PASS", f"{runtime:.1f}h")
                else:
                    print_test("  └─ 辊道窑总表运行时长", "WARN", "未找到总表数据")
            else:
                print_test("运行时长统计", "WARN", f"设备数量不足: {len(devices)} (期望≥20个)")
        else:
            print_test("运行时长统计", "FAIL", data.get("error", "未知错误"))
            
    except Exception as e:
        print_test("运行时长统计", "FAIL", f"请求失败: {str(e)}")


def test_database_storage():
    """测试4: 数据库存储验证"""
    print_header("测试4: 数据库存储验证")
    
    # 通过查询历史数据来验证数据库存储
    try:
        # 查询料仓历史数据
        device_id = "short_hopper_1"
        response = requests.get(
            f"{BASE_URL}/api/hopper/{device_id}/history?hours=1", 
            timeout=10
        )
        data = response.json()
        
        if data.get("success"):
            records = data.get("data", [])
            if len(records) > 0:
                print_test("料仓数据存储", "PASS", f"查询到 {len(records)} 条历史记录")
            else:
                print_test("料仓数据存储", "WARN", "无历史数据（可能刚启动）")
        else:
            print_test("料仓数据存储", "FAIL", data.get("error", "未知错误"))
            
    except Exception as e:
        print_test("料仓数据存储", "FAIL", f"请求失败: {str(e)}")
    
    # 查询辊道窑历史数据
    try:
        response = requests.get(
            f"{BASE_URL}/api/roller/history?hours=1", 
            timeout=10
        )
        data = response.json()
        
        if data.get("success"):
            records = data.get("data", [])
            if len(records) > 0:
                print_test("辊道窑数据存储", "PASS", f"查询到 {len(records)} 条历史记录")
            else:
                print_test("辊道窑数据存储", "WARN", "无历史数据（可能刚启动）")
        else:
            print_test("辊道窑数据存储", "FAIL", data.get("error", "未知错误"))
            
    except Exception as e:
        print_test("辊道窑数据存储", "FAIL", f"请求失败: {str(e)}")


def print_summary():
    """打印测试摘要"""
    print_header("测试摘要")
    
    total = test_results["total"]
    passed = test_results["passed"]
    failed = test_results["failed"]
    warnings = test_results["warnings"]
    
    pass_rate = (passed / total * 100) if total > 0 else 0
    
    print(f"总测试数: {total}")
    print(f"✅ 通过: {passed} ({pass_rate:.1f}%)")
    print(f"❌ 失败: {failed}")
    print(f"⚠️  警告: {warnings}")
    
    if failed == 0:
        print(f"\n🎉 所有测试通过！数据流完整性验证成功！")
        return 0
    else:
        print(f"\n⚠️  有 {failed} 个测试失败，请检查日志")
        return 1


def main():
    """主函数"""
    print("\n" + "="*60)
    print("  数据流完整性测试")
    print("  ceramic-workshop-backend")
    print("="*60)
    print(f"  后端地址: {BASE_URL}")
    print(f"  测试时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*60)
    
    # 执行测试
    if not test_health_check():
        print("\n❌ 系统健康检查失败，终止测试")
        return 1
    
    test_realtime_data()
    test_database_storage()
    test_export_apis()
    
    # 打印摘要
    return print_summary()


if __name__ == "__main__":
    try:
        exit_code = main()
        sys.exit(exit_code)
    except KeyboardInterrupt:
        print("\n\n⚠️  测试被用户中断")
        sys.exit(1)
    except Exception as e:
        print(f"\n\n❌ 测试脚本异常: {str(e)}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

