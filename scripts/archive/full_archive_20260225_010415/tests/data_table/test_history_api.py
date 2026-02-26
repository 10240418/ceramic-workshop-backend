#!/usr/bin/env python3
# ============================================================
# 文件说明: test_history_api.py - 历史数据API测试脚本
# ============================================================
# 功能:
# 1. 测试所有历史数据API（与Flutter端data_display_page.dart调用一致）
# 2. 模拟Flutter端初始化时获取最近120秒的历史数据
# 3. 将查询结果输出到JSON文件，便于调试分析
#
# 使用方法:
#   python tests/data_table/test_history_api.py
#
# 输出文件:
#   tests/data_table/history_data_output.json
# ============================================================

import sys
import os
import json
import requests
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional

# 添加项目根目录到路径
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, PROJECT_ROOT)

# ============================================================
# 配置
# ============================================================
BASE_URL = "http://localhost:8080"
DEFAULT_TIME_RANGE_SECONDS = 120  # 默认120秒时间范围
OUTPUT_FILE = os.path.join(os.path.dirname(__file__), "history_data_output.json")

# 设备ID映射（与Flutter端一致）
HOPPER_DEVICE_IDS = {
    1: 'short_hopper_1',
    2: 'short_hopper_2',
    3: 'short_hopper_3',
    4: 'short_hopper_4',
    5: 'no_hopper_1',
    6: 'no_hopper_2',
    7: 'long_hopper_1',
    8: 'long_hopper_2',
    9: 'long_hopper_3',
}

ROLLER_ZONE_IDS = {
    1: 'zone1',
    2: 'zone2',
    3: 'zone3',
    4: 'zone4',
    5: 'zone5',
    6: 'zone6',
}

SCR_DEVICE_IDS = {
    1: 'scr_1',
    2: 'scr_2',
}

FAN_DEVICE_IDS = {
    1: 'fan_1',
    2: 'fan_2',
}


def calculate_aggregate_interval(start: datetime, end: datetime) -> str:
    """根据时间范围计算最佳聚合间隔（与Flutter端逻辑一致）"""
    duration = end - start
    minutes = duration.total_seconds() / 60
    
    if minutes < 2:
        return '5s'
    elif minutes < 10:
        return '10s'
    elif minutes < 30:
        return '30s'
    elif minutes < 120:
        return '1m'
    elif minutes < 360:
        return '5m'
    elif minutes < 1440:
        return '15m'
    elif minutes < 10080:
        return '1h'
    else:
        return '6h'


def fetch_history_data(url: str, params: Dict[str, str]) -> Dict[str, Any]:
    """发送HTTP请求获取历史数据"""
    try:
        full_url = f"{BASE_URL}{url}"
        response = requests.get(full_url, params=params, timeout=10)
        
        return {
            "url": full_url,
            "params": params,
            "status_code": response.status_code,
            "response": response.json() if response.status_code == 200 else None,
            "error": None if response.status_code == 200 else f"HTTP {response.status_code}"
        }
    except Exception as e:
        return {
            "url": f"{BASE_URL}{url}",
            "params": params,
            "status_code": None,
            "response": None,
            "error": str(e)
        }


def test_hopper_temperature_history(device_id: str, start: datetime, end: datetime) -> Dict:
    """测试料仓温度历史API"""
    interval = calculate_aggregate_interval(start, end)
    params = {
        'start': start.isoformat(),
        'end': end.isoformat(),
        'interval': interval,
        'module_type': 'TemperatureSensor',
        'fields': 'temperature'
    }
    return fetch_history_data(f"/api/hopper/{device_id}/history", params)


def test_hopper_weight_history(device_id: str, start: datetime, end: datetime) -> Dict:
    """测试料仓称重历史API"""
    interval = calculate_aggregate_interval(start, end)
    params = {
        'start': start.isoformat(),
        'end': end.isoformat(),
        'interval': interval,
        'module_type': 'WeighSensor',
        'fields': 'weight,feed_rate'
    }
    return fetch_history_data(f"/api/hopper/{device_id}/history", params)


def test_roller_temperature_history(zone: str, start: datetime, end: datetime) -> Dict:
    """测试辊道窑温度历史API"""
    interval = calculate_aggregate_interval(start, end)
    params = {
        'start': start.isoformat(),
        'end': end.isoformat(),
        'interval': interval,
        'zone': zone,
        'module_type': 'TemperatureSensor',
        'fields': 'temperature'
    }
    return fetch_history_data("/api/roller/history", params)


def test_roller_power_history(zone: str, start: datetime, end: datetime) -> Dict:
    """测试辊道窑功率历史API"""
    interval = calculate_aggregate_interval(start, end)
    params = {
        'start': start.isoformat(),
        'end': end.isoformat(),
        'interval': interval,
        'zone': zone,
        'module_type': 'ElectricityMeter',
        'fields': 'Pt,ImpEp'
    }
    return fetch_history_data("/api/roller/history", params)


def test_scr_power_history(device_id: str, start: datetime, end: datetime) -> Dict:
    """测试SCR功率历史API"""
    interval = calculate_aggregate_interval(start, end)
    params = {
        'start': start.isoformat(),
        'end': end.isoformat(),
        'interval': interval,
        'module_type': 'ElectricityMeter',
        'fields': 'Pt,ImpEp'
    }
    return fetch_history_data(f"/api/scr/{device_id}/history", params)


def test_fan_power_history(device_id: str, start: datetime, end: datetime) -> Dict:
    """测试风机功率历史API"""
    interval = calculate_aggregate_interval(start, end)
    params = {
        'start': start.isoformat(),
        'end': end.isoformat(),
        'interval': interval,
        'module_type': 'ElectricityMeter',
        'fields': 'Pt,ImpEp'
    }
    return fetch_history_data(f"/api/fan/{device_id}/history", params)


def run_all_tests() -> Dict[str, Any]:
    """运行所有历史数据API测试（模拟Flutter端初始化）"""
    
    # 计算时间范围（最近120秒）
    now = datetime.now()
    start = now - timedelta(seconds=DEFAULT_TIME_RANGE_SECONDS)
    
    print("=" * 60)
    print("🧪 历史数据API测试")
    print("=" * 60)
    print(f"📅 时间范围: {start.strftime('%H:%M:%S')} ~ {now.strftime('%H:%M:%S')} (最近{DEFAULT_TIME_RANGE_SECONDS}秒)")
    print(f" 聚合间隔: {calculate_aggregate_interval(start, now)}")
    print("=" * 60)
    
    results = {
        "test_time": now.isoformat(),
        "time_range": {
            "start": start.isoformat(),
            "end": now.isoformat(),
            "duration_seconds": DEFAULT_TIME_RANGE_SECONDS,
            "interval": calculate_aggregate_interval(start, now)
        },
        "hopper": {},
        "roller": {},
        "scr": {},
        "fan": {},
        "summary": {
            "total_tests": 0,
            "success": 0,
            "failed": 0,
            "empty_data": 0
        }
    }
    
    # ==================== 1. 测试料仓历史数据 ====================
    print("\n📦 测试料仓历史数据...")
    
    for idx, device_id in HOPPER_DEVICE_IDS.items():
        print(f"  测试 {device_id}...")
        
        # 温度历史
        temp_result = test_hopper_temperature_history(device_id, start, now)
        results["summary"]["total_tests"] += 1
        
        temp_data_count = 0
        if temp_result["response"] and temp_result["response"].get("success"):
            data = temp_result["response"].get("data", {})
            if isinstance(data, list):
                temp_data_count = len(data)
            elif isinstance(data, dict):
                temp_data_count = data.get("count", len(data.get("data", [])))
            
            if temp_data_count > 0:
                results["summary"]["success"] += 1
            else:
                results["summary"]["empty_data"] += 1
        else:
            results["summary"]["failed"] += 1
        
        # 称重历史
        weight_result = test_hopper_weight_history(device_id, start, now)
        results["summary"]["total_tests"] += 1
        
        weight_data_count = 0
        if weight_result["response"] and weight_result["response"].get("success"):
            data = weight_result["response"].get("data", {})
            if isinstance(data, list):
                weight_data_count = len(data)
            elif isinstance(data, dict):
                weight_data_count = data.get("count", len(data.get("data", [])))
                
            if weight_data_count > 0:
                results["summary"]["success"] += 1
            else:
                results["summary"]["empty_data"] += 1
        else:
            results["summary"]["failed"] += 1
        
        results["hopper"][device_id] = {
            "temperature": {
                "status": "success" if temp_result["response"] and temp_result["response"].get("success") else "failed",
                "data_count": temp_data_count,
                "response": temp_result
            },
            "weight": {
                "status": "success" if weight_result["response"] and weight_result["response"].get("success") else "failed",
                "data_count": weight_data_count,
                "response": weight_result
            }
        }
        
        print(f"    ✓ 温度: {temp_data_count}条, 称重: {weight_data_count}条")
    
    # ==================== 2. 测试辊道窑历史数据 ====================
    print("\n 测试辊道窑历史数据...")
    
    for idx, zone_id in ROLLER_ZONE_IDS.items():
        print(f"  测试 {zone_id}...")
        
        # 温度历史
        temp_result = test_roller_temperature_history(zone_id, start, now)
        results["summary"]["total_tests"] += 1
        
        temp_data_count = 0
        if temp_result["response"] and temp_result["response"].get("success"):
            data = temp_result["response"].get("data", {})
            if isinstance(data, list):
                temp_data_count = len(data)
            elif isinstance(data, dict):
                temp_data_count = data.get("count", len(data.get("data", [])))
                
            if temp_data_count > 0:
                results["summary"]["success"] += 1
            else:
                results["summary"]["empty_data"] += 1
        else:
            results["summary"]["failed"] += 1
        
        # 功率历史
        power_result = test_roller_power_history(zone_id, start, now)
        results["summary"]["total_tests"] += 1
        
        power_data_count = 0
        if power_result["response"] and power_result["response"].get("success"):
            data = power_result["response"].get("data", {})
            if isinstance(data, list):
                power_data_count = len(data)
            elif isinstance(data, dict):
                power_data_count = data.get("count", len(data.get("data", [])))
                
            if power_data_count > 0:
                results["summary"]["success"] += 1
            else:
                results["summary"]["empty_data"] += 1
        else:
            results["summary"]["failed"] += 1
        
        results["roller"][zone_id] = {
            "temperature": {
                "status": "success" if temp_result["response"] and temp_result["response"].get("success") else "failed",
                "data_count": temp_data_count,
                "response": temp_result
            },
            "power": {
                "status": "success" if power_result["response"] and power_result["response"].get("success") else "failed",
                "data_count": power_data_count,
                "response": power_result
            }
        }
        
        print(f"    ✓ 温度: {temp_data_count}条, 功率: {power_data_count}条")
    
    # ==================== 3. 测试SCR历史数据 ====================
    print("\n⚗️ 测试SCR历史数据...")
    
    for idx, device_id in SCR_DEVICE_IDS.items():
        print(f"  测试 {device_id}...")
        
        power_result = test_scr_power_history(device_id, start, now)
        results["summary"]["total_tests"] += 1
        
        power_data_count = 0
        if power_result["response"] and power_result["response"].get("success"):
            data = power_result["response"].get("data", {})
            if isinstance(data, list):
                power_data_count = len(data)
            elif isinstance(data, dict):
                power_data_count = data.get("count", len(data.get("data", [])))
                
            if power_data_count > 0:
                results["summary"]["success"] += 1
            else:
                results["summary"]["empty_data"] += 1
        else:
            results["summary"]["failed"] += 1
        
        results["scr"][device_id] = {
            "power": {
                "status": "success" if power_result["response"] and power_result["response"].get("success") else "failed",
                "data_count": power_data_count,
                "response": power_result
            }
        }
        
        print(f"    ✓ 功率: {power_data_count}条")
    
    # ==================== 4. 测试风机历史数据 ====================
    print("\n🌀 测试风机历史数据...")
    
    for idx, device_id in FAN_DEVICE_IDS.items():
        print(f"  测试 {device_id}...")
        
        power_result = test_fan_power_history(device_id, start, now)
        results["summary"]["total_tests"] += 1
        
        power_data_count = 0
        if power_result["response"] and power_result["response"].get("success"):
            data = power_result["response"].get("data", {})
            if isinstance(data, list):
                power_data_count = len(data)
            elif isinstance(data, dict):
                power_data_count = data.get("count", len(data.get("data", [])))
                
            if power_data_count > 0:
                results["summary"]["success"] += 1
            else:
                results["summary"]["empty_data"] += 1
        else:
            results["summary"]["failed"] += 1
        
        results["fan"][device_id] = {
            "power": {
                "status": "success" if power_result["response"] and power_result["response"].get("success") else "failed",
                "data_count": power_data_count,
                "response": power_result
            }
        }
        
        print(f"    ✓ 功率: {power_data_count}条")
    
    return results


def main():
    """主入口"""
    print("\n" + "=" * 60)
    print(" 历史数据API测试脚本")
    print("=" * 60)
    print("📋 测试内容:")
    print("   - 9个料仓温度+称重历史 (short_hopper_1~4, no_hopper_1~2, long_hopper_1~3)")
    print("   - 6个辊道窑温区温度+功率历史 (zone1~6)")
    print("   - 2个SCR功率历史 (scr_1~2)")
    print("   - 2个风机功率历史 (fan_1~2)")
    print("=" * 60)
    
    # 运行测试
    results = run_all_tests()
    
    # 输出摘要
    print("\n" + "=" * 60)
    print(" 测试摘要")
    print("=" * 60)
    summary = results["summary"]
    print(f"  总测试数: {summary['total_tests']}")
    print(f"  ✓ 成功(有数据): {summary['success']}")
    print(f"  ⚠ 成功(无数据): {summary['empty_data']}")
    print(f"  ✗ 失败: {summary['failed']}")
    
    # 问题诊断
    if summary['empty_data'] > 0 or summary['failed'] > 0:
        print("\n  发现问题:")
        if summary['empty_data'] > 0:
            print(f"   - {summary['empty_data']}个API返回成功但数据为空")
            print("     可能原因: 模拟轮询服务运行时间不足120秒，或时间范围参数问题")
        if summary['failed'] > 0:
            print(f"   - {summary['failed']}个API请求失败")
            print("     可能原因: 后端服务未启动，或API路径/参数错误")
    
    # 保存结果到JSON文件
    print(f"\n 保存结果到: {OUTPUT_FILE}")
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        json.dump(results, f, indent=2, ensure_ascii=False, default=str)
    
    print("\n[正确] 测试完成!")
    print("=" * 60)
    
    return results


if __name__ == "__main__":
    main()
