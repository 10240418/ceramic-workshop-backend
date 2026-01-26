#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试数据导出修复
"""

import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from datetime import datetime, timedelta, timezone
from app.services.data_export_service import get_export_service

def test_roller_kiln_zones():
    """测试辊道窑6个分区的电量和运行时长"""
    print("=" * 80)
    print("🔍 测试辊道窑6个分区")
    print("=" * 80)
    
    service = get_export_service()
    
    # 测试时间范围：2026-01-19 到 2026-01-27（8天） 
    end_time = datetime(2026, 1, 27, 16, 33, 38, tzinfo=timezone.utc)
    start_time = datetime(2026, 1, 19, 16, 33, 38, tzinfo=timezone.utc)
    
    zone_ids = ["zone1", "zone2", "zone3", "zone4", "zone5", "zone6"]
    
    for zone_id in zone_ids:
        print(f"\n📊 测试 {zone_id}:")
        
        zone_data = service._calculate_roller_zone_electricity_by_day(
            zone_id=zone_id,
            start_time=start_time,
            end_time=end_time
        )
        
        # 只显示第一天的数据
        if zone_data["daily_records"]:
            first_day = zone_data["daily_records"][0]
            print(f"  日期: {first_day['date']}")
            print(f"  电量消耗: {first_day['consumption']} kWh")
            print(f"  运行时长: {first_day['runtime_hours']} h")
            
            if first_day['consumption'] == 0.0:
                print(f"  ❌ 电量为0，需要检查！")
            else:
                print(f"  ✅ 电量正常")
            
            if first_day['runtime_hours'] == 0.0:
                print(f"  ❌ 运行时长为0，需要检查！")
            else:
                print(f"  ✅ 运行时长正常")


def test_scr_gas_meters():
    """测试SCR燃气表的燃气消耗和电量"""
    print("\n" + "=" * 80)
    print("🔍 测试SCR燃气表")
    print("=" * 80)
    
    service = get_export_service()
    
    # 测试时间范围
    end_time = datetime(2026, 1, 26, 16, 33, 38, tzinfo=timezone.utc)
    start_time = datetime(2026, 1, 19, 16, 33, 38, tzinfo=timezone.utc)
    
    scr_ids = ["scr_1", "scr_2"]
    
    for scr_id in scr_ids:
        print(f"\n📊 测试 {scr_id}:")
        
        # 测试燃气消耗
        gas_data = service.calculate_gas_consumption_by_day(
            device_ids=[scr_id],
            start_time=start_time,
            end_time=end_time
        )
        
        if scr_id in gas_data and gas_data[scr_id]["daily_records"]:
            first_day = gas_data[scr_id]["daily_records"][0]
            print(f"  日期: {first_day['date']}")
            print(f"  燃气消耗: {first_day['consumption']} m³")
            
            if first_day['consumption'] == 0.0:
                print(f"  ❌ 燃气消耗为0，需要检查！")
            else:
                print(f"  ✅ 燃气消耗正常")
        
        # 测试电量消耗（燃气表电表）
        elec_data = service.calculate_electricity_consumption_by_day(
            device_id=scr_id,
            device_type="scr",
            start_time=start_time,
            end_time=end_time
        )
        
        if elec_data["daily_records"]:
            first_day = elec_data["daily_records"][0]
            print(f"  电量消耗: {first_day['consumption']} kWh")
            print(f"  运行时长: {first_day['runtime_hours']} h")
            
            if first_day['consumption'] == 0.0:
                print(f"  ❌ 电量为0，需要检查！")
            else:
                print(f"  ✅ 电量正常")


def test_comprehensive_export():
    """测试综合导出（检查辊道窑合计运行时长）"""
    print("\n" + "=" * 80)
    print("🔍 测试综合导出（辊道窑合计运行时长）")
    print("=" * 80)
    
    service = get_export_service()
    
    # 测试时间范围
    end_time = datetime(2026, 1, 26, 16, 33, 38, tzinfo=timezone.utc)
    start_time = datetime(2026, 1, 19, 16, 33, 38, tzinfo=timezone.utc)
    
    result = service.calculate_all_data_comprehensive(
        start_time=start_time,
        end_time=end_time
    )
    
    # 查找辊道窑相关设备
    roller_zones = []
    roller_total = None
    
    for device in result["devices"]:
        if device["device_type"] == "roller_kiln_zone":
            roller_zones.append(device)
        elif device["device_type"] == "roller_kiln_total":
            roller_total = device
    
    print(f"\n📊 辊道窑6个分区:")
    for zone in roller_zones:
        if zone["daily_records"]:
            first_day = zone["daily_records"][0]
            print(f"  {zone['device_id']}: 电量={first_day['electricity_consumption']} kWh, 运行时长={first_day['runtime_hours']} h")
    
    if roller_total and roller_total["daily_records"]:
        first_day = roller_total["daily_records"][0]
        print(f"\n📊 辊道窑合计:")
        print(f"  电量: {first_day['electricity_consumption']} kWh")
        print(f"  运行时长: {first_day['runtime_hours']} h")
        
        # 计算6个分区的平均运行时长
        zone_runtimes = [zone["daily_records"][0]["runtime_hours"] for zone in roller_zones if zone["daily_records"]]
        if zone_runtimes:
            avg_runtime = sum(zone_runtimes) / len(zone_runtimes)
            print(f"  6个分区平均运行时长: {avg_runtime:.2f} h")
            
            if abs(first_day['runtime_hours'] - avg_runtime) < 0.1:
                print(f"  ✅ 合计运行时长正确（使用平均值）")
            else:
                print(f"  ❌ 合计运行时长不正确（应该是平均值 {avg_runtime:.2f} h）")


if __name__ == "__main__":
    try:
        print("\n🚀 开始测试数据导出修复\n")
        
        test_roller_kiln_zones()
        test_scr_gas_meters()
        test_comprehensive_export()
        
        print("\n" + "=" * 80)
        print("✅ 测试完成")
        print("=" * 80)
        
    except Exception as e:
        print(f"\n❌ 测试失败: {str(e)}")
        import traceback
        traceback.print_exc()

