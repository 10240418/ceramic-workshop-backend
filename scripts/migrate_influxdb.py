#!/usr/bin/env python3
# ============================================================
# 文件说明: migrate_influxdb.py - InfluxDB 迁移命令行工具
# ============================================================
# 使用方法:
#   python scripts/migrate_influxdb.py           # 显示当前 Schema
#   python scripts/migrate_influxdb.py migrate   # 执行迁移
#   python scripts/migrate_influxdb.py check     # 检查连接
# ============================================================

import sys
from pathlib import Path

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from app.core.influx_migration import InfluxDBMigration
from app.core.influx_schema import get_schema_summary, ALL_SCHEMAS


def print_schema_info():
    """打印 Schema 信息"""
    print("=" * 70)
    print("📊 InfluxDB Schema 定义")
    print("=" * 70)
    
    summary = get_schema_summary()
    print(f"\n总计: {summary['total_measurements']} 个 Measurements (数据表)\n")
    
    # 按分类显示
    categories = {
        "窑炉设备 (6个)": ["roller_kiln_temp", "roller_kiln_energy", "rotary_kiln_temp", 
                      "rotary_kiln_energy", "rotary_kiln_feed", "rotary_kiln_hopper"],
        "SCR设备 (3个)": ["scr_fan", "scr_pump", "scr_gas"],
        "系统功能 (2个)": ["alarms", "production_stats"],
        "模块化数据 (1个)": ["module_data"],
    }
    
    for category, measurement_names in categories.items():
        print(f"【{category}】")
        for m in summary['measurements']:
            if m['name'] in measurement_names:
                print(f"  • {m['name']}")
                print(f"    描述: {m['description']}")
                print(f"    Tags: {m['tags_count']} 个 | Fields: {m['fields_count']} 个")
                print(f"    保留: {m['retention']}")
                print()
    
    print("=" * 70)


def check_connection():
    """检查 InfluxDB 连接"""
    print("=" * 70)
    print("🔍 检查 InfluxDB 连接")
    print("=" * 70)
    
    migration = InfluxDBMigration()
    
    print(f"\n连接信息:")
    print(f"  URL: {migration.url}")
    print(f"  Org: {migration.org}")
    print(f"  Bucket: {migration.bucket}")
    print(f"  Token: {'*' * 20}")
    
    print(f"\n正在连接...")
    if migration.connect():
        print("✅ 连接成功!")
        
        # 检查 Bucket 是否存在
        try:
            buckets_api = migration.client.buckets_api()
            bucket = buckets_api.find_bucket_by_name(migration.bucket)
            if bucket:
                print(f"✅ Bucket '{migration.bucket}' 已存在")
            else:
                print(f"⚠️  Bucket '{migration.bucket}' 不存在，需要执行迁移")
        except Exception as e:
            print(f"⚠️  检查 Bucket 失败: {e}")
        
        migration.disconnect()
    else:
        print("❌ 连接失败!")
        sys.exit(1)
    
    print("=" * 70)


def run_migration():
    """执行迁移"""
    migration = InfluxDBMigration()
    success = migration.auto_migrate()
    
    if success:
        print("\n✅ 迁移成功完成!")
        sys.exit(0)
    else:
        print("\n❌ 迁移失败!")
        sys.exit(1)


def show_help():
    """显示帮助信息"""
    print("""
╔══════════════════════════════════════════════════════════════════╗
║           InfluxDB 迁移管理工具                                   ║
╚══════════════════════════════════════════════════════════════════╝

使用方法:
  python scripts/migrate_influxdb.py           # 显示当前 Schema
  python scripts/migrate_influxdb.py migrate   # 执行迁移
  python scripts/migrate_influxdb.py check     # 检查连接

功能说明:
  • migrate - 自动创建 Bucket、验证 Schema
  • check   - 检查 InfluxDB 连接状态
  • 默认    - 显示所有数据表定义

环境变量配置:
  INFLUX_URL=http://localhost:8086
  INFLUX_TOKEN=ceramic-workshop-token
  INFLUX_ORG=ceramic-workshop
  INFLUX_BUCKET=sensor_data

数据保留策略:
  所有数据表均设置为永久保留（INFINITE）
    """)


if __name__ == "__main__":
    if len(sys.argv) > 1:
        command = sys.argv[1].lower()
        
        if command == "migrate":
            run_migration()
        elif command == "check":
            check_connection()
        elif command in ["help", "-h", "--help"]:
            show_help()
        else:
            print(f"❌ 未知命令: {command}")
            show_help()
            sys.exit(1)
    else:
        # 默认显示 Schema 信息
        print_schema_info()
