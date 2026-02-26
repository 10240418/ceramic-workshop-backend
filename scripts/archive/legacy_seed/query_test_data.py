#!/usr/bin/env python3
# ============================================================
# 查询 InfluxDB 中的测试数据
# ============================================================

import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from app.core.influxdb import get_influx_client
from config import get_settings

settings = get_settings()

def query_test_data():
    """查询测试数据"""
    print("=" * 70)
    print("🔍 查询 InfluxDB 测试数据")
    print("=" * 70)
    
    client = get_influx_client()
    query_api = client.query_api()
    
    # 1. 查询数据点总数
    print("\n1️⃣  查询数据点总数...")
    query = f'''
    from(bucket: "{settings.influx_bucket}")
      |> range(start: -3h)
      |> filter(fn: (r) => r._measurement == "module_data")
      |> count()
    '''
    
    tables = query_api.query(query)
    total_points = 0
    for table in tables:
        for record in table.records:
            total_points += record.get_value()
    
    print(f"   总数据点: {total_points}")
    
    # 2. 按设备类型统计
    print("\n2️⃣  按设备类型统计...")
    query = f'''
    from(bucket: "{settings.influx_bucket}")
      |> range(start: -3h)
      |> filter(fn: (r) => r._measurement == "module_data")
      |> group(columns: ["device_type"])
      |> count()
    '''
    
    tables = query_api.query(query)
    device_stats = {}
    for table in tables:
        for record in table.records:
            device_type = record.values.get('device_type')
            count = record.get_value()
            if device_type not in device_stats:
                device_stats[device_type] = 0
            device_stats[device_type] += count
    
    for device_type, count in sorted(device_stats.items()):
        print(f"   • {device_type:15} - {count} 个点")
    
    # 3. 按模块类型统计
    print("\n3️⃣  按模块类型统计...")
    query = f'''
    from(bucket: "{settings.influx_bucket}")
      |> range(start: -3h)
      |> filter(fn: (r) => r._measurement == "module_data")
      |> group(columns: ["module_name"])
      |> count()
    '''
    
    tables = query_api.query(query)
    module_stats = {}
    for table in tables:
        for record in table.records:
            module_name = record.values.get('module_name')
            count = record.get_value()
            if module_name not in module_stats:
                module_stats[module_name] = 0
            module_stats[module_name] += count
    
    for module_name, count in sorted(module_stats.items()):
        print(f"   • {module_name:20} - {count} 个点")
    
    # 4. 查询最新的 ElectricityMeter 数据
    print("\n4️⃣  最新 ElectricityMeter 数据示例...")
    query = f'''
    from(bucket: "{settings.influx_bucket}")
      |> range(start: -1h)
      |> filter(fn: (r) => r._measurement == "module_data")
      |> filter(fn: (r) => r.module_name == "ElectricityMeter")
      |> filter(fn: (r) => r.device_type == "test_device")
      |> last()
      |> limit(n: 5)
    '''
    
    tables = query_api.query(query)
    for table in tables:
        for record in table.records:
            field = record.get_field()
            value = record.get_value()
            print(f"   • {field:15} = {value}")
    
    print("\n" + "=" * 70)
    print(" 数据查询完成！")
    print("\n 提示:")
    print("   • 访问 http://localhost:8086 查看 InfluxDB UI")
    print("   • 使用 Data Explorer 手动查询数据")
    print("   • 准备启动后端服务测试 API")
    print("=" * 70)


if __name__ == "__main__":
    query_test_data()
