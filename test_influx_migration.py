#!/usr/bin/env python3
# ============================================================
# InfluxDB Schema 迁移测试
# ============================================================

import sys
from pathlib import Path

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent))

from app.core.influx_migration import InfluxDBMigration
from app.core.influx_schema import get_schema_summary


def main():
    """主函数"""
    print("""
╔══════════════════════════════════════════════════════════════════╗
║           InfluxDB Schema 迁移测试                                ║
╚══════════════════════════════════════════════════════════════════╝
    """)
    
    # 1. 显示 Schema 定义
    print("📋 当前 Schema 定义:")
    print("=" * 70)
    summary = get_schema_summary()
    
    for m in summary['measurements']:
        print(f"\n📊 {m['name']}")
        print(f"   描述: {m['description']}")
        print(f"   Tags: {m['tags_count']} 个")
        print(f"   Fields: {m['fields_count']} 个")
        print(f"   保留: {m['retention']}")
    
    print("\n" + "=" * 70)
    print(f"总计: {summary['total_measurements']} 个 Measurements")
    print("=" * 70)
    
    # 2. 确认执行迁移
    print("\n⚠️  准备执行 InfluxDB 迁移")
    print("将创建以下内容:")
    print("  - Bucket: sensor_data (主数据，永久保留 ♾️)")
    print("  - Schema: 10 个 Measurements")
    print("  - 所有数据永久保留，无自动过期策略")
    
    confirm = input("\n是否继续? (yes/no): ").strip().lower()
    if confirm != 'yes' and confirm != 'y':
        print("❌ 已取消")
        return
    
    # 3. 执行迁移
    print("\n" + "=" * 70)
    migration = InfluxDBMigration()
    success = migration.auto_migrate()
    
    if success:
        print("\n🎉 迁移测试成功！")
        print("\n💡 提示:")
        print("  - 启动服务时会自动执行迁移")
        print("  - 修改 Schema 后重新运行此脚本")
        print("  - 或在 main.py 启动时自动迁移")
    else:
        print("\n❌ 迁移测试失败！")
        print("请检查:")
        print("  - InfluxDB 是否运行 (docker-compose up -d influxdb)")
        print("  - 环境变量是否正确配置")
        print("  - Token 是否有效")


if __name__ == "__main__":
    main()
