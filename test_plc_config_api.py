#!/usr/bin/env python3
"""
PLC 动态配置系统使用示例
演示如何通过 API 管理 PLC 数据点配置
"""

import requests
import json

BASE_URL = "http://localhost:8080/api/plc-config"


def print_response(title, response):
    """打印响应结果"""
    print(f"\n{'='*70}")
    print(f"📋 {title}")
    print(f"{'='*70}")
    print(json.dumps(response.json(), indent=2, ensure_ascii=False))


def main():
    print("""
╔══════════════════════════════════════════════════════════════════╗
║          PLC 动态配置系统 API 使用示例                             ║
╚══════════════════════════════════════════════════════════════════╝
    """)
    
    # 1. 获取配置摘要
    print("\n1️⃣  获取配置摘要")
    resp = requests.get(BASE_URL)
    print_response("配置摘要", resp)
    
    # 2. 获取回转窑数据点列表
    print("\n2️⃣  获取回转窑数据点列表")
    resp = requests.get(f"{BASE_URL}/rotary_kiln")
    print_response("回转窑数据点", resp)
    
    # 3. 添加新数据点
    print("\n3️⃣  添加新数据点（温区3温度）")
    new_point = {
        "name": "温区3温度",
        "point_id": "zone_3_temp",
        "db_offset": 8,
        "data_type": "WORD",
        "scale": 0.1,
        "unit": "°C",
        "measurement": "rotary_kiln_temp",
        "field_name": "temperature",
        "tags": {"zone_id": "3"},
        "enabled": True
    }
    
    resp = requests.post(
        f"{BASE_URL}/rotary_kiln/point",
        json=new_point
    )
    print_response("添加数据点结果", resp)
    
    # 4. 更新数据点
    print("\n4️⃣  更新数据点（修改温区1温度的偏移量）")
    updates = {
        "db_offset": 10,
        "scale": 1.0
    }
    
    resp = requests.put(
        f"{BASE_URL}/rotary_kiln/point/zone_1_temp",
        json=updates
    )
    print_response("更新数据点结果", resp)
    
    # 5. 验证配置
    print("\n5️⃣  验证配置有效性")
    resp = requests.post(f"{BASE_URL}/validate")
    print_response("配置验证结果", resp)
    
    # 6. 获取自动生成的 Schema
    print("\n6️⃣  获取自动生成的 InfluxDB Schema")
    resp = requests.get(f"{BASE_URL}/schema/generate")
    result = resp.json()
    
    print(f"\n{'='*70}")
    print(f"📋 InfluxDB Schema")
    print(f"{'='*70}")
    print(f"\n总计 {result['data']['total']} 个 Measurements:\n")
    for name in result['data']['measurement_names']:
        print(f"  📊 {name}")
    
    # 7. 热重载配置
    print("\n7️⃣  热重载配置")
    resp = requests.post(f"{BASE_URL}/reload")
    print_response("热重载结果", resp)
    
    print("\n" + "="*70)
    print("✅ 示例演示完成！")
    print("="*70)
    print("\n💡 提示:")
    print("  - 查看完整 API 文档: http://localhost:8080/docs")
    print("  - 查看使用指南: PLC_CONFIG_GUIDE.md")


if __name__ == "__main__":
    try:
        main()
    except requests.exceptions.ConnectionError:
        print("❌ 无法连接到服务，请先启动 FastAPI 服务:")
        print("   python main.py")
    except Exception as e:
        print(f"❌ 错误: {e}")
