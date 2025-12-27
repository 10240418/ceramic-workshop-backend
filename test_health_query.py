#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试健康检测查询
"""

from app.core.influxdb import get_influx_client
from config import get_settings

settings = get_settings()
client = get_influx_client()
query_api = client.query_api()

print("=" * 60)
print("测试 1: 查询所有数据（不分组）")
print("=" * 60)

query1 = f'''
from(bucket: "{settings.influx_bucket}")
    |> range(start: -30m)
    |> filter(fn: (r) => r["_measurement"] == "sensor_data")
    |> filter(fn: (r) => r["_field"] == "Pt" or r["_field"] == "temperature" or r["_field"] == "weight" or r["_field"] == "flow_rate")
    |> limit(n: 10)
'''

try:
    tables = query_api.query(query1, org=settings.influx_org)
    count = sum(len(t.records) for t in tables)
    print(f"找到 {count} 条记录")
    
    for table in tables:
        for record in table.records[:5]:  # 只显示前5条
            print(f"  device_id={record.values.get('device_id')}, "
                  f"module_type={record.values.get('module_type')}, "
                  f"module_tag={record.values.get('module_tag')}, "
                  f"field={record.get_field()}, "
                  f"time={record.get_time()}")
except Exception as e:
    print(f"❌ 查询失败: {e}")

print("\n" + "=" * 60)
print("测试 2: 使用健康检测的查询（分组+last）")
print("=" * 60)

query2 = f'''
from(bucket: "{settings.influx_bucket}")
    |> range(start: -30m)
    |> filter(fn: (r) => r["_measurement"] == "sensor_data")
    |> filter(fn: (r) => r["_field"] == "Pt" or r["_field"] == "temperature" or r["_field"] == "weight" or r["_field"] == "flow_rate")
    |> group(columns: ["device_id", "module_type", "module_tag"])
    |> last()
    |> keep(columns: ["device_id", "module_type", "module_tag", "_time"])
'''

try:
    tables = query_api.query(query2, org=settings.influx_org)
    count = sum(len(t.records) for t in tables)
    print(f"找到 {count} 条记录")
    
    for table in tables:
        for record in table.records[:20]:  # 显示前20条
            print(f"  device_id={record.values.get('device_id')}, "
                  f"module_type={record.values.get('module_type')}, "
                  f"module_tag={record.values.get('module_tag')}, "
                  f"time={record.get_time()}")
except Exception as e:
    print(f"❌ 查询失败: {e}")
    import traceback
    traceback.print_exc()

print("\n" + "=" * 60)
print("测试 3: 查询特定设备")
print("=" * 60)

query3 = f'''
from(bucket: "{settings.influx_bucket}")
    |> range(start: -30m)
    |> filter(fn: (r) => r["_measurement"] == "sensor_data")
    |> filter(fn: (r) => r["device_id"] == "short_hopper_1")
    |> limit(n: 10)
'''

try:
    tables = query_api.query(query3, org=settings.influx_org)
    count = sum(len(t.records) for t in tables)
    print(f"找到 {count} 条记录（short_hopper_1）")
    
    for table in tables:
        for record in table.records[:5]:
            print(f"  field={record.get_field()}, "
                  f"value={record.get_value()}, "
                  f"module_type={record.values.get('module_type')}, "
                  f"module_tag={record.values.get('module_tag')}")
except Exception as e:
    print(f"❌ 查询失败: {e}")
