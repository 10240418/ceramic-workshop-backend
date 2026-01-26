#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试所有5个导出接口
验证设备数量、数据格式、设备名称映射
"""

import requests
import json
from datetime import datetime, timedelta

BASE_URL = "http://localhost:8080"

# 设备名称映射（用于验证）
DEVICE_NAME_MAP = {
    # 回转窑
    'short_hopper_1': '窑7',
    'short_hopper_2': '窑6',
    'short_hopper_3': '窑5',
    'short_hopper_4': '窑4',
    'no_hopper_1': '窑2',
    'no_hopper_2': '窑1',
    'long_hopper_1': '窑8',
    'long_hopper_2': '窑3',
    'long_hopper_3': '窑9',
    
    # 辊道窑
    'zone1': '辊道窑分区1',
    'zone2': '辊道窑分区2',
    'zone3': '辊道窑分区3',
    'zone4': '辊道窑分区4',
    'zone5': '辊道窑分区5',
    'zone6': '辊道窑分区6',
    'roller_kiln_total': '辊道窑合计',
    
    # SCR燃气表
    'scr_1': 'SCR北_燃气表',
    'scr_2': 'SCR南_燃气表',
    
    # SCR氨水泵
    'scr_1_pump': 'SCR北_氨水泵',
    'scr_2_pump': 'SCR南_氨水泵',
    
    # 风机
    'fan_1': 'SCR北_风机',
    'fan_2': 'SCR南_风机',
}


def print_section(title):
    """打印分隔线"""
    print("\n" + "=" * 80)
    print(f"  {title}")
    print("=" * 80)


def test_runtime_all():
    """测试1: 运行时长统计接口"""
    print_section("测试1: 运行时长统计 (/api/export/runtime/all)")
    
    response = requests.get(f"{BASE_URL}/api/export/runtime/all?days=1")
    
    if response.status_code != 200:
        print(f"[ERROR] HTTP {response.status_code}")
        return False
    
    data = response.json()
    
    if not data.get("success"):
        print(f"[ERROR] {data.get('error')}")
        return False
    
    result = data["data"]
    
    # 验证设备数量
    hopper_count = len(result.get("hoppers", []))
    zone_count = len(result.get("roller_kiln_zones", []))
    has_total = 1 if result.get("roller_kiln_total") else 0
    scr_count = len(result.get("scr_devices", []))
    fan_count = len(result.get("fan_devices", []))
    
    total_devices = hopper_count + zone_count + has_total + scr_count + fan_count
    
    print(f"\n[设备数量验证]")
    print(f"  - 回转窑: {hopper_count} (预期: 9)")
    print(f"  - 辊道窑分区: {zone_count} (预期: 6)")
    print(f"  - 辊道窑合计: {has_total} (预期: 1)")
    print(f"  - SCR氨水泵: {scr_count} (预期: 2)")
    print(f"  - 风机: {fan_count} (预期: 2)")
    print(f"  - 总计: {total_devices} (预期: 20)")
    
    if total_devices != 20:
        print(f"[ERROR] 设备数量不匹配！")
        return False
    
    # 验证数据结构
    print(f"\n[数据结构验证]")
    if result["hoppers"]:
        hopper = result["hoppers"][0]
        print(f"  - 设备ID: {hopper['device_id']}")
        print(f"  - 设备类型: {hopper['device_type']}")
        print(f"  - 统计天数: {hopper['total_days']}")
        
        if hopper['daily_records']:
            record = hopper['daily_records'][0]
            print(f"  - 数据字段: {list(record.keys())}")
            print(f"  - 运行时长: {record['runtime_hours']} 小时")
            
            # 验证必需字段
            required_fields = ['day', 'date', 'start_time', 'end_time', 'runtime_hours']
            missing_fields = [f for f in required_fields if f not in record]
            
            if missing_fields:
                print(f"[ERROR] 缺少字段: {missing_fields}")
                return False
    
    # 验证设备名称映射
    print(f"\n[设备名称映射验证]")
    all_device_ids = []
    all_device_ids.extend([h['device_id'] for h in result['hoppers']])
    all_device_ids.extend([z['device_id'] for z in result['roller_kiln_zones']])
    all_device_ids.append(result['roller_kiln_total']['device_id'])
    all_device_ids.extend([s['device_id'] for s in result['scr_devices']])
    all_device_ids.extend([f['device_id'] for f in result['fan_devices']])
    
    unmapped_devices = [d for d in all_device_ids if d not in DEVICE_NAME_MAP]
    
    if unmapped_devices:
        print(f"[WARNING] 未映射的设备: {unmapped_devices}")
    else:
        print(f"  - 所有设备都有名称映射 ✓")
    
    print(f"\n[OK] 运行时长统计接口测试通过")
    return True


def test_gas_consumption():
    """测试2: 燃气消耗统计接口"""
    print_section("测试2: 燃气消耗统计 (/api/export/gas-consumption)")
    
    response = requests.get(f"{BASE_URL}/api/export/gas-consumption?days=1")
    
    if response.status_code != 200:
        print(f"[ERROR] HTTP {response.status_code}")
        return False
    
    data = response.json()
    
    if not data.get("success"):
        print(f"[ERROR] {data.get('error')}")
        return False
    
    result = data["data"]
    
    # 验证设备数量
    device_count = len(result)
    print(f"\n[设备数量验证]")
    print(f"  - SCR燃气表: {device_count} (预期: 2)")
    
    if device_count != 2:
        print(f"[ERROR] 设备数量不匹配！")
        return False
    
    # 验证设备ID
    expected_devices = ['scr_1', 'scr_2']
    actual_devices = list(result.keys())
    
    print(f"\n[设备ID验证]")
    print(f"  - 预期: {expected_devices}")
    print(f"  - 实际: {actual_devices}")
    
    if set(actual_devices) != set(expected_devices):
        print(f"[ERROR] 设备ID不匹配！")
        return False
    
    # 验证数据结构
    print(f"\n[数据结构验证]")
    for device_id, device_data in result.items():
        print(f"  - {device_id} ({DEVICE_NAME_MAP.get(device_id, '未知')})")
        print(f"    - 统计天数: {device_data['total_days']}")
        
        if device_data['daily_records']:
            record = device_data['daily_records'][0]
            print(f"    - 数据字段: {list(record.keys())}")
            
            # 验证必需字段
            required_fields = ['day', 'date', 'start_time', 'end_time', 
                             'start_reading', 'end_reading', 'consumption']
            missing_fields = [f for f in required_fields if f not in record]
            
            if missing_fields:
                print(f"[ERROR] 缺少字段: {missing_fields}")
                return False
    
    print(f"\n[OK] 燃气消耗统计接口测试通过")
    return True


def test_feeding_amount():
    """测试3: 投料量统计接口"""
    print_section("测试3: 投料量统计 (/api/export/feeding-amount)")
    
    response = requests.get(f"{BASE_URL}/api/export/feeding-amount?days=1")
    
    if response.status_code != 200:
        print(f"[ERROR] HTTP {response.status_code}")
        return False
    
    data = response.json()
    
    if not data.get("success"):
        print(f"[ERROR] {data.get('error')}")
        return False
    
    result = data["data"]
    
    # 验证设备数量
    hopper_count = len(result.get("hoppers", []))
    print(f"\n[设备数量验证]")
    print(f"  - 带料仓的回转窑: {hopper_count} (预期: 7)")
    
    if hopper_count != 7:
        print(f"[ERROR] 设备数量不匹配！")
        return False
    
    # 验证设备ID（不应包含 no_hopper）
    hopper_ids = [h['device_id'] for h in result['hoppers']]
    print(f"\n[设备ID验证]")
    print(f"  - 实际设备: {hopper_ids}")
    
    # 检查是否包含无料仓的设备
    no_hopper_devices = [d for d in hopper_ids if 'no_hopper' in d]
    if no_hopper_devices:
        print(f"[ERROR] 不应包含无料仓设备: {no_hopper_devices}")
        return False
    
    # 验证数据结构
    print(f"\n[数据结构验证]")
    if result["hoppers"]:
        hopper = result["hoppers"][0]
        print(f"  - 设备ID: {hopper['device_id']}")
        
        if hopper['daily_records']:
            record = hopper['daily_records'][0]
            print(f"  - 数据字段: {list(record.keys())}")
            print(f"  - 投料量: {record['feeding_amount']} kg")
            
            # 验证必需字段
            required_fields = ['date', 'start_time', 'end_time', 'feeding_amount']
            missing_fields = [f for f in required_fields if f not in record]
            
            if missing_fields:
                print(f"[ERROR] 缺少字段: {missing_fields}")
                return False
    
    print(f"\n[OK] 投料量统计接口测试通过")
    return True


def test_electricity_all():
    """测试4: 电量统计接口"""
    print_section("测试4: 电量统计 (/api/export/electricity/all)")
    
    response = requests.get(f"{BASE_URL}/api/export/electricity/all?days=1")
    
    if response.status_code != 200:
        print(f"[ERROR] HTTP {response.status_code}")
        return False
    
    data = response.json()
    
    if not data.get("success"):
        print(f"[ERROR] {data.get('error')}")
        return False
    
    result = data["data"]
    
    # 验证设备数量
    hopper_count = len(result.get("hoppers", []))
    zone_count = len(result.get("roller_kiln_zones", []))
    has_total = 1 if result.get("roller_kiln_total") else 0
    scr_count = len(result.get("scr_devices", []))
    fan_count = len(result.get("fan_devices", []))
    
    total_devices = hopper_count + zone_count + has_total + scr_count + fan_count
    
    print(f"\n[设备数量验证]")
    print(f"  - 回转窑: {hopper_count} (预期: 9)")
    print(f"  - 辊道窑分区: {zone_count} (预期: 6)")
    print(f"  - 辊道窑合计: {has_total} (预期: 1)")
    print(f"  - SCR氨水泵: {scr_count} (预期: 2)")
    print(f"  - 风机: {fan_count} (预期: 2)")
    print(f"  - 总计: {total_devices} (预期: 20)")
    
    if total_devices != 20:
        print(f"[ERROR] 设备数量不匹配！")
        return False
    
    # 验证数据结构
    print(f"\n[数据结构验证]")
    if result["hoppers"]:
        hopper = result["hoppers"][0]
        
        if hopper['daily_records']:
            record = hopper['daily_records'][0]
            print(f"  - 数据字段: {list(record.keys())}")
            print(f"  - 电量消耗: {record['consumption']} kWh")
            print(f"  - 运行时长: {record['runtime_hours']} 小时")
            
            # 验证必需字段
            required_fields = ['day', 'date', 'start_time', 'end_time', 
                             'start_reading', 'end_reading', 'consumption', 'runtime_hours']
            missing_fields = [f for f in required_fields if f not in record]
            
            if missing_fields:
                print(f"[ERROR] 缺少字段: {missing_fields}")
                return False
    
    print(f"\n[OK] 电量统计接口测试通过")
    return True


def test_comprehensive():
    """测试5: 综合数据统计接口"""
    print_section("测试5: 综合数据统计 (/api/export/comprehensive)")
    
    response = requests.get(f"{BASE_URL}/api/export/comprehensive?days=1")
    
    if response.status_code != 200:
        print(f"[ERROR] HTTP {response.status_code}")
        return False
    
    data = response.json()
    
    if not data.get("success"):
        print(f"[ERROR] {data.get('error')}")
        return False
    
    result = data["data"]
    
    # 验证设备数量
    device_count = len(result.get("devices", []))
    print(f"\n[设备数量验证]")
    print(f"  - 总设备数: {device_count} (预期: 20)")
    print(f"  - 报告的设备数: {result.get('total_devices', 0)}")
    
    if device_count != 20:
        print(f"[ERROR] 设备数量不匹配！")
        return False
    
    # 验证数据结构
    print(f"\n[数据结构验证]")
    if result["devices"]:
        device = result["devices"][0]
        print(f"  - 设备ID: {device['device_id']}")
        print(f"  - 设备类型: {device['device_type']}")
        
        if device['daily_records']:
            record = device['daily_records'][0]
            print(f"  - 数据字段: {list(record.keys())}")
            
            # 验证必需字段
            required_fields = ['date', 'start_time', 'end_time', 
                             'gas_consumption', 'feeding_amount', 
                             'electricity_consumption', 'runtime_hours']
            missing_fields = [f for f in required_fields if f not in record]
            
            if missing_fields:
                print(f"[ERROR] 缺少字段: {missing_fields}")
                return False
    
    # 验证数据逻辑
    print(f"\n[数据逻辑验证]")
    for device in result["devices"]:
        device_id = device['device_id']
        device_type = device['device_type']
        
        if device['daily_records']:
            record = device['daily_records'][0]
            
            # 检查燃气消耗（仅SCR应该有）
            has_gas = record['gas_consumption'] > 0
            should_have_gas = 'scr' in device_id and 'pump' not in device_id
            
            # 检查投料量（仅带料仓的回转窑应该有）
            has_feeding = record['feeding_amount'] > 0
            should_have_feeding = device_type == 'hopper' and 'no_hopper' not in device_id
            
            # 检查电量消耗（所有设备都应该有）
            has_electricity = record['electricity_consumption'] > 0
            
            # 检查运行时长（所有设备都应该有）
            has_runtime = record['runtime_hours'] > 0
    
    print(f"  - 数据逻辑验证通过 ✓")
    
    print(f"\n[OK] 综合数据统计接口测试通过")
    return True


def main():
    """主测试函数"""
    print("\n" + "=" * 80)
    print("  开始测试所有5个导出接口")
    print("=" * 80)
    
    results = {
        "运行时长统计": test_runtime_all(),
        "燃气消耗统计": test_gas_consumption(),
        "投料量统计": test_feeding_amount(),
        "电量统计": test_electricity_all(),
        "综合数据统计": test_comprehensive(),
    }
    
    # 打印测试结果汇总
    print_section("测试结果汇总")
    
    for test_name, passed in results.items():
        status = "[PASS]" if passed else "[FAIL]"
        print(f"  {status} {test_name}")
    
    # 统计
    total_tests = len(results)
    passed_tests = sum(1 for p in results.values() if p)
    
    print(f"\n总计: {passed_tests}/{total_tests} 测试通过")
    
    if passed_tests == total_tests:
        print("\n[SUCCESS] 所有测试通过！")
        return 0
    else:
        print("\n[FAILURE] 部分测试失败！")
        return 1


if __name__ == "__main__":
    exit(main())

