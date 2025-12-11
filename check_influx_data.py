#!/usr/bin/env python3
# 临时脚本：检查 InfluxDB 数据

from app.core.influxdb import get_influx_client
from config import get_settings

settings = get_settings()
client = get_influx_client()
query_api = client.query_api()

# 查询最近24小时的所有数据
query = f'from(bucket: "{settings.influx_bucket}") |> range(start: -24h) |> limit(n: 5)'

print(f"🔍 查询 InfluxDB bucket: {settings.influx_bucket}")
print(f"📊 查询语句: {query}\n")

try:
    result = query_api.query(query)
    
    total_records = 0
    for table in result:
        total_records += len(table.records)
        if table.records:
            print(f"✅ 找到 {len(table.records)} 条记录")
            for record in table.records[:3]:  # 只显示前3条
                print(f"   - {record.get_time()}: {record.get_field()} = {record.get_value()}")
                print(f"     Tags: device_id={record.values.get('device_id')}, device_type={record.values.get('device_type')}")
    
    if total_records == 0:
        print("❌ InfluxDB 中没有数据！")
        print("\n可能原因:")
        print("1. 轮询服务未启动或崩溃")
        print("2. PLC 连接失败导致无法读取数据")
        print("3. 数据解析或写入过程出错")
        print("\n建议检查:")
        print("- 查看后端启动日志中的 '🚀 开始轮询数据' 信息")
        print("- 运行: python3 scripts/test_complete_flow.py")
    else:
        print(f"\n✅ 总共找到 {total_records} 条记录")
    
except Exception as e:
    print(f"❌ 查询失败: {e}")
