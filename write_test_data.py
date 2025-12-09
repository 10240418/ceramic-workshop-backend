#!/usr/bin/env python3
# ============================================================
# InfluxDB 测试数据写入工具
# ============================================================
# 快速写入测试数据，用于验证 Schema
# ============================================================

import sys
from datetime import datetime, timedelta
from influxdb_client import InfluxDBClient, Point
from influxdb_client.client.write_api import SYNCHRONOUS
import os
import random


class TestDataWriter:
    """测试数据写入器"""
    
    def __init__(self):
        self.url = os.getenv("INFLUX_URL", "http://localhost:8086")
        self.token = os.getenv("INFLUX_TOKEN", "ceramic-workshop-token")
        self.org = os.getenv("INFLUX_ORG", "ceramic-workshop")
        self.bucket = os.getenv("INFLUX_BUCKET", "sensor_data")
        
        self.client = InfluxDBClient(
            url=self.url,
            token=self.token,
            org=self.org
        )
        self.write_api = self.client.write_api(write_options=SYNCHRONOUS)
    
    # ------------------------------------------------------------
    # 1. write_roller_kiln_data() - 写入辊道窑测试数据
    # ------------------------------------------------------------
    def write_roller_kiln_data(self, count: int = 10):
        """写入辊道窑测试数据"""
        print(f"📝 写入辊道窑测试数据 ({count} 条)...")
        
        points = []
        now = datetime.utcnow()
        
        # 温度数据（12个温区）
        for i in range(count):
            timestamp = now - timedelta(minutes=i * 5)
            for zone in range(1, 13):
                point = Point("roller_kiln_temp") \
                    .tag("zone_id", str(zone)) \
                    .field("temperature", 800 + random.uniform(-50, 50)) \
                    .field("set_point", 850.0) \
                    .time(timestamp)
                points.append(point)
        
        # 能耗数据
        for i in range(count):
            timestamp = now - timedelta(minutes=i * 5)
            point = Point("roller_kiln_energy") \
                .field("voltage", 380 + random.uniform(-10, 10)) \
                .field("current", 150 + random.uniform(-20, 20)) \
                .field("power", 65 + random.uniform(-5, 5)) \
                .field("total_energy", 1500 + i * 10) \
                .field("status", 1) \
                .time(timestamp)
            points.append(point)
        
        self.write_api.write(bucket=self.bucket, record=points)
        print(f"  ✅ 已写入 {len(points)} 条数据")
    
    # ------------------------------------------------------------
    # 2. write_rotary_kiln_data() - 写入回转窑测试数据
    # ------------------------------------------------------------
    def write_rotary_kiln_data(self, device_id: int = 1, count: int = 10):
        """写入回转窑测试数据"""
        print(f"📝 写入回转窑 {device_id} 号测试数据 ({count} 条)...")
        
        points = []
        now = datetime.utcnow()
        
        # 温度数据（8个温区）
        for i in range(count):
            timestamp = now - timedelta(minutes=i * 5)
            for zone in range(1, 9):
                point = Point("rotary_kiln_temp") \
                    .tag("device_id", str(device_id)) \
                    .tag("zone_id", str(zone)) \
                    .field("temperature", 900 + random.uniform(-50, 50)) \
                    .field("set_point", 950.0) \
                    .time(timestamp)
                points.append(point)
        
        # 能耗数据
        for i in range(count):
            timestamp = now - timedelta(minutes=i * 5)
            point = Point("rotary_kiln_energy") \
                .tag("device_id", str(device_id)) \
                .field("voltage", 380 + random.uniform(-10, 10)) \
                .field("current", 200 + random.uniform(-30, 30)) \
                .field("power", 80 + random.uniform(-8, 8)) \
                .field("total_energy", 2000 + i * 15) \
                .field("status", 1) \
                .time(timestamp)
            points.append(point)
        
        # 下料数据
        for i in range(count):
            timestamp = now - timedelta(minutes=i * 5)
            point = Point("rotary_kiln_feed") \
                .tag("device_id", str(device_id)) \
                .field("feed_speed", 500 + random.uniform(-50, 50)) \
                .time(timestamp)
            points.append(point)
        
        # 料仓数据
        for i in range(count):
            timestamp = now - timedelta(minutes=i * 5)
            weight = 800 - i * 10
            point = Point("rotary_kiln_hopper") \
                .tag("device_id", str(device_id)) \
                .tag("hopper_id", "1") \
                .field("weight", weight) \
                .field("capacity", 1000.0) \
                .field("percent", weight / 10) \
                .field("low_alarm", 1 if weight < 200 else 0) \
                .time(timestamp)
            points.append(point)
        
        self.write_api.write(bucket=self.bucket, record=points)
        print(f"  ✅ 已写入 {len(points)} 条数据")
    
    # ------------------------------------------------------------
    # 3. write_scr_data() - 写入 SCR 测试数据
    # ------------------------------------------------------------
    def write_scr_data(self, device_id: int = 1, count: int = 10):
        """写入 SCR 测试数据"""
        print(f"📝 写入 SCR {device_id} 号测试数据 ({count} 条)...")
        
        points = []
        now = datetime.utcnow()
        
        # 风机数据（4台风机）
        for i in range(count):
            timestamp = now - timedelta(minutes=i * 5)
            for fan in range(1, 5):
                point = Point("scr_fan") \
                    .tag("device_id", str(device_id)) \
                    .tag("fan_id", str(fan)) \
                    .field("power", 15 + random.uniform(-2, 2)) \
                    .field("cumulative_energy", 500 + i * 5) \
                    .field("status", 1) \
                    .time(timestamp)
                points.append(point)
        
        # 氨水泵数据（2台泵）
        for i in range(count):
            timestamp = now - timedelta(minutes=i * 5)
            for pump in range(1, 3):
                point = Point("scr_pump") \
                    .tag("device_id", str(device_id)) \
                    .tag("pump_id", str(pump)) \
                    .field("power", 5 + random.uniform(-0.5, 0.5)) \
                    .field("cumulative_energy", 200 + i * 2) \
                    .field("status", 1) \
                    .time(timestamp)
                points.append(point)
        
        # 燃气数据（2条管路）
        for i in range(count):
            timestamp = now - timedelta(minutes=i * 5)
            for pipe in range(1, 3):
                point = Point("scr_gas") \
                    .tag("device_id", str(device_id)) \
                    .tag("pipeline_id", str(pipe)) \
                    .field("flow_rate", 100 + random.uniform(-10, 10)) \
                    .field("cumulative_volume", 5000 + i * 50) \
                    .time(timestamp)
                points.append(point)
        
        self.write_api.write(bucket=self.bucket, record=points)
        print(f"  ✅ 已写入 {len(points)} 条数据")
    
    # ------------------------------------------------------------
    # 4. write_alarms() - 写入告警测试数据
    # ------------------------------------------------------------
    def write_alarms(self, count: int = 5):
        """写入告警测试数据"""
        print(f"📝 写入告警测试数据 ({count} 条)...")
        
        points = []
        now = datetime.utcnow()
        
        alarm_types = ["hopper_low_weight", "temp_deviation", "communication_lost"]
        alarm_levels = ["warning", "critical"]
        device_types = ["roller_kiln", "rotary_kiln", "scr"]
        
        for i in range(count):
            timestamp = now - timedelta(hours=i)
            point = Point("alarms") \
                .tag("device_type", random.choice(device_types)) \
                .tag("device_id", str(random.randint(1, 3))) \
                .tag("alarm_type", random.choice(alarm_types)) \
                .tag("alarm_level", random.choice(alarm_levels)) \
                .field("message", f"测试告警 #{i+1}") \
                .field("value", 150.0) \
                .field("threshold", 200.0) \
                .field("acknowledged", 0) \
                .field("resolved", 0) \
                .time(timestamp)
            points.append(point)
        
        self.write_api.write(bucket=self.bucket, record=points)
        print(f"  ✅ 已写入 {len(points)} 条告警")
    
    def close(self):
        """关闭连接"""
        self.client.close()


def main():
    """主函数"""
    print("""
╔══════════════════════════════════════════════════════════════════╗
║              InfluxDB 测试数据写入工具                            ║
╚══════════════════════════════════════════════════════════════════╝
    """)
    
    writer = TestDataWriter()
    
    try:
        # 写入各类测试数据
        writer.write_roller_kiln_data(count=20)
        writer.write_rotary_kiln_data(device_id=1, count=20)
        writer.write_rotary_kiln_data(device_id=2, count=20)
        writer.write_scr_data(device_id=1, count=20)
        writer.write_scr_data(device_id=2, count=20)
        writer.write_alarms(count=10)
        
        print("\n" + "=" * 70)
        print("✅ 所有测试数据写入完成！")
        print("=" * 70)
        print("\n💡 现在可以使用以下命令查看数据:")
        print("   python query_influx.py list          # 列出所有表")
        print("   python query_influx.py count         # 统计数据量")
        print("   python query_influx.py show roller_kiln_temp")
        
    except Exception as e:
        print(f"\n❌ 写入失败: {e}")
    
    finally:
        writer.close()


if __name__ == "__main__":
    main()
