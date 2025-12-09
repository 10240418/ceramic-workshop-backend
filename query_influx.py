#!/usr/bin/env python3
# ============================================================
# InfluxDB 数据查询工具
# ============================================================
# 使用方法:
# python query_influx.py list                    # 列出所有表
# python query_influx.py show roller_kiln_temp   # 查看表数据
# python query_influx.py count                   # 统计各表数据量
# ============================================================

import sys
from datetime import datetime, timedelta
from influxdb_client import InfluxDBClient
from tabulate import tabulate
import os


class InfluxDBQuery:
    """InfluxDB 查询工具"""
    
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
        self.query_api = self.client.query_api()
    
    # ------------------------------------------------------------
    # 1. list_measurements() - 列出所有数据表
    # ------------------------------------------------------------
    def list_measurements(self):
        """列出所有 Measurements（数据表）"""
        print("\n📊 InfluxDB 数据表列表\n")
        
        flux_query = f'''
        import "influxdata/influxdb/schema"
        
        schema.measurements(bucket: "{self.bucket}")
        '''
        
        try:
            tables = self.query_api.query(flux_query)
            
            if not tables:
                print("❌ 没有找到任何数据表")
                return
            
            measurements = []
            for table in tables:
                for record in table.records:
                    measurements.append(record.values.get("_value"))
            
            # 显示表格
            data = [[i+1, m] for i, m in enumerate(measurements)]
            print(tabulate(data, headers=["#", "Measurement (表名)"], tablefmt="grid"))
            print(f"\n总计: {len(measurements)} 个数据表")
            
        except Exception as e:
            print(f"❌ 查询失败: {e}")
    
    # ------------------------------------------------------------
    # 2. show_data() - 查看指定表的数据
    # ------------------------------------------------------------
    def show_data(self, measurement: str, limit: int = 20):
        """查看指定表的数据
        
        Args:
            measurement: 表名
            limit: 显示行数
        """
        print(f"\n📋 {measurement} - 最新 {limit} 条数据\n")
        
        flux_query = f'''
        from(bucket: "{self.bucket}")
          |> range(start: -7d)
          |> filter(fn: (r) => r._measurement == "{measurement}")
          |> limit(n: {limit})
        '''
        
        try:
            tables = self.query_api.query(flux_query)
            
            if not tables:
                print("❌ 表中没有数据")
                return
            
            # 收集所有记录
            records = []
            for table in tables:
                for record in table.records:
                    records.append({
                        'time': record.get_time().strftime('%Y-%m-%d %H:%M:%S'),
                        'field': record.get_field(),
                        'value': record.get_value(),
                        **{k: v for k, v in record.values.items() 
                           if k not in ['_start', '_stop', '_time', '_value', '_field', '_measurement', 'result', 'table']}
                    })
            
            if not records:
                print("❌ 没有查询到数据")
                return
            
            # 显示表格
            headers = list(records[0].keys())
            data = [[r[h] for h in headers] for r in records[:limit]]
            print(tabulate(data, headers=headers, tablefmt="grid"))
            print(f"\n显示: {min(len(records), limit)} 条记录")
            
        except Exception as e:
            print(f"❌ 查询失败: {e}")
    
    # ------------------------------------------------------------
    # 3. count_data() - 统计各表数据量
    # ------------------------------------------------------------
    def count_data(self):
        """统计各表的数据量"""
        print("\n📊 数据表统计信息\n")
        
        # 先获取所有表名
        flux_query = f'''
        import "influxdata/influxdb/schema"
        
        schema.measurements(bucket: "{self.bucket}")
        '''
        
        try:
            tables = self.query_api.query(flux_query)
            measurements = []
            for table in tables:
                for record in table.records:
                    measurements.append(record.values.get("_value"))
            
            if not measurements:
                print("❌ 没有找到任何数据表")
                return
            
            # 统计每个表的数据量
            stats = []
            for m in measurements:
                count_query = f'''
                from(bucket: "{self.bucket}")
                  |> range(start: -7d)
                  |> filter(fn: (r) => r._measurement == "{m}")
                  |> count()
                '''
                
                result = self.query_api.query(count_query)
                total = 0
                for table in result:
                    for record in table.records:
                        total += record.get_value()
                
                stats.append([m, total])
            
            # 排序并显示
            stats.sort(key=lambda x: x[1], reverse=True)
            print(tabulate(stats, headers=["Measurement (表名)", "记录数（近7天）"], tablefmt="grid"))
            
        except Exception as e:
            print(f"❌ 统计失败: {e}")
    
    # ------------------------------------------------------------
    # 4. show_tags() - 查看表的 Tags（索引）
    # ------------------------------------------------------------
    def show_tags(self, measurement: str):
        """查看指定表的 Tags
        
        Args:
            measurement: 表名
        """
        print(f"\n🏷️  {measurement} - Tags 信息\n")
        
        flux_query = f'''
        import "influxdata/influxdb/schema"
        
        schema.tagKeys(bucket: "{self.bucket}", predicate: (r) => r._measurement == "{measurement}")
        '''
        
        try:
            tables = self.query_api.query(flux_query)
            
            tags = []
            for table in tables:
                for record in table.records:
                    tags.append(record.values.get("_value"))
            
            if not tags:
                print("❌ 该表没有定义 Tags")
                return
            
            # 显示表格
            data = [[i+1, t] for i, t in enumerate(tags)]
            print(tabulate(data, headers=["#", "Tag Key"], tablefmt="grid"))
            
        except Exception as e:
            print(f"❌ 查询失败: {e}")
    
    def close(self):
        """关闭连接"""
        self.client.close()


def show_help():
    """显示帮助信息"""
    print("""
╔══════════════════════════════════════════════════════════════════╗
║                InfluxDB 数据查询工具                              ║
╚══════════════════════════════════════════════════════════════════╝

使用方法:
    python query_influx.py list                      # 列出所有数据表
    python query_influx.py show <表名> [行数]        # 查看表数据
    python query_influx.py count                     # 统计各表数据量
    python query_influx.py tags <表名>               # 查看表的 Tags
    python query_influx.py help                      # 显示帮助

示例:
    python query_influx.py list
    python query_influx.py show roller_kiln_temp 50
    python query_influx.py count
    python query_influx.py tags rotary_kiln_temp
    """)


def main():
    """主函数"""
    if len(sys.argv) < 2:
        show_help()
        return
    
    command = sys.argv[1].lower()
    
    if command == "help":
        show_help()
        return
    
    query = InfluxDBQuery()
    
    try:
        if command == "list":
            query.list_measurements()
        
        elif command == "show":
            if len(sys.argv) < 3:
                print("❌ 请指定表名: python query_influx.py show <表名>")
                return
            measurement = sys.argv[2]
            limit = int(sys.argv[3]) if len(sys.argv) > 3 else 20
            query.show_data(measurement, limit)
        
        elif command == "count":
            query.count_data()
        
        elif command == "tags":
            if len(sys.argv) < 3:
                print("❌ 请指定表名: python query_influx.py tags <表名>")
                return
            measurement = sys.argv[2]
            query.show_tags(measurement)
        
        else:
            print(f"❌ 未知命令: {command}")
            show_help()
    
    finally:
        query.close()


if __name__ == "__main__":
    main()
