# ============================================================
# API测试脚本 - 验证所有API端点
# ============================================================
# 使用方法:
# 1. 确保后端服务正在运行 (python quickstart.py)
# 2. 运行此脚本: python test_api.py
# ============================================================

import requests
import time
from datetime import datetime, timedelta

BASE_URL = "http://localhost:8080/api"


def test_health_endpoints():
    """测试健康检查端点"""
    print("\n" + "=" * 60)
    print("测试健康检查端点")
    print("=" * 60)
    
    endpoints = [
        "/health",
        "/health/plc",
        "/health/database"
    ]
    
    for endpoint in endpoints:
        try:
            response = requests.get(f"{BASE_URL}{endpoint}")
            status = "✅" if response.status_code == 200 else "❌"
            print(f"{status} GET {endpoint}: {response.status_code}")
            if response.status_code == 200:
                print(f"   Response: {response.json()}")
        except Exception as e:
            print(f"❌ GET {endpoint}: {e}")


def test_roller_kiln_endpoints():
    """测试辊道窑端点"""
    print("\n" + "=" * 60)
    print("测试辊道窑端点")
    print("=" * 60)
    
    # 实时数据
    try:
        response = requests.get(f"{BASE_URL}/kiln/roller/realtime")
        status = "✅" if response.status_code == 200 else "❌"
        print(f"{status} GET /kiln/roller/realtime: {response.status_code}")
        if response.status_code == 200:
            data = response.json()
            print(f"   温区数量: {len(data['data']['zones'])}")
            print(f"   当前功率: {data['data']['power']} kW")
    except Exception as e:
        print(f"❌ GET /kiln/roller/realtime: {e}")
    
    # 历史数据
    try:
        end = datetime.now()
        start = end - timedelta(hours=1)
        response = requests.get(
            f"{BASE_URL}/kiln/roller/history",
            params={
                "start": start.isoformat(),
                "end": end.isoformat(),
                "interval": "1m"
            }
        )
        status = "✅" if response.status_code == 200 else "❌"
        print(f"{status} GET /kiln/roller/history: {response.status_code}")
    except Exception as e:
        print(f"❌ GET /kiln/roller/history: {e}")


def test_rotary_kiln_endpoints():
    """测试回转窑端点"""
    print("\n" + "=" * 60)
    print("测试回转窑端点")
    print("=" * 60)
    
    # 设备列表
    try:
        response = requests.get(f"{BASE_URL}/kiln/rotary")
        status = "✅" if response.status_code == 200 else "❌"
        print(f"{status} GET /kiln/rotary: {response.status_code}")
        if response.status_code == 200:
            data = response.json()
            print(f"   设备数量: {len(data['data'])}")
    except Exception as e:
        print(f"❌ GET /kiln/rotary: {e}")
    
    # 实时数据 (设备1)
    try:
        response = requests.get(f"{BASE_URL}/kiln/rotary/1/realtime")
        status = "✅" if response.status_code == 200 else "❌"
        print(f"{status} GET /kiln/rotary/1/realtime: {response.status_code}")
        if response.status_code == 200:
            data = response.json()
            print(f"   设备名称: {data['data']['device_name']}")
            print(f"   温区数量: {len(data['data']['zones'])}")
            print(f"   下料速度: {data['data']['feed_speed']} kg/h")
            print(f"   料仓重量: {data['data']['hopper']['weight']} kg ({data['data']['hopper']['percent']}%)")
    except Exception as e:
        print(f"❌ GET /kiln/rotary/1/realtime: {e}")


def test_scr_endpoints():
    """测试SCR设备端点"""
    print("\n" + "=" * 60)
    print("测试SCR设备端点")
    print("=" * 60)
    
    # 设备列表
    try:
        response = requests.get(f"{BASE_URL}/scr")
        status = "✅" if response.status_code == 200 else "❌"
        print(f"{status} GET /scr: {response.status_code}")
        if response.status_code == 200:
            data = response.json()
            print(f"   设备数量: {len(data['data'])}")
    except Exception as e:
        print(f"❌ GET /scr: {e}")
    
    # 实时数据 (设备1)
    try:
        response = requests.get(f"{BASE_URL}/scr/1/realtime")
        status = "✅" if response.status_code == 200 else "❌"
        print(f"{status} GET /scr/1/realtime: {response.status_code}")
        if response.status_code == 200:
            data = response.json()
            print(f"   设备名称: {data['data']['device_name']}")
            print(f"   风机数量: {len(data['data']['fans'])}")
            print(f"   氨水泵数量: {len(data['data']['ammonia_pumps'])}")
            print(f"   燃气管路数量: {len(data['data']['gas_pipelines'])}")
    except Exception as e:
        print(f"❌ GET /scr/1/realtime: {e}")
    
    # 风机数据
    try:
        response = requests.get(f"{BASE_URL}/scr/1/fans")
        status = "✅" if response.status_code == 200 else "❌"
        print(f"{status} GET /scr/1/fans: {response.status_code}")
    except Exception as e:
        print(f"❌ GET /scr/1/fans: {e}")


def main():
    """主函数"""
    print("\n" + "=" * 60)
    print("   陶瓷车间数字孪生系统 - API测试")
    print("=" * 60)
    print(f"测试目标: {BASE_URL}")
    
    # 检查服务是否运行
    try:
        response = requests.get(f"{BASE_URL}/health", timeout=2)
        if response.status_code != 200:
            print("\n❌ 后端服务未运行或健康检查失败")
            print("请先运行: python quickstart.py")
            return
    except Exception:
        print("\n❌ 无法连接到后端服务")
        print("请先运行: python quickstart.py")
        return
    
    print("✅ 后端服务正在运行")
    print("\n等待3秒让数据轮询服务写入数据...")
    time.sleep(3)
    
    # 运行测试
    test_health_endpoints()
    test_roller_kiln_endpoints()
    test_rotary_kiln_endpoints()
    test_scr_endpoints()
    
    print("\n" + "=" * 60)
    print("测试完成!")
    print("=" * 60)
    print(f"\n📖 查看完整API文档: http://localhost:8080/docs")


if __name__ == "__main__":
    main()
