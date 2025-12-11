#!/usr/bin/env python3
"""
============================================================
完整 API 测试脚本 (带详细输出)
============================================================
测试所有 24 个 API 端点，输出请求参数和响应结果

用法:
    python3 scripts/test_api_full.py

前提:
    1. 服务已启动: python3 main.py
    2. InfluxDB 运行中: docker ps
============================================================
"""
import httpx
import json
from datetime import datetime, timedelta
from typing import Optional

# API 基础地址
API_BASE = "http://localhost:8080"

# 颜色输出
class Colors:
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    MAGENTA = '\033[95m'
    RESET = '\033[0m'
    BOLD = '\033[1m'


def print_header(title: str):
    """打印分隔标题"""
    print(f"\n{'=' * 70}")
    print(f"{Colors.BOLD}{Colors.CYAN}{title}{Colors.RESET}")
    print('=' * 70)


def print_request(method: str, path: str, params: Optional[dict] = None, body: Optional[dict] = None):
    """打印请求信息"""
    full_url = f"{API_BASE}{path}"
    
    # 构建带参数的URL显示
    if params:
        param_str = "&".join([f"{k}={v}" for k, v in params.items()])
        display_url = f"{full_url}?{param_str}"
    else:
        display_url = full_url
    
    print(f"\n{Colors.BLUE}▶ {method} {display_url}{Colors.RESET}")
    
    if params:
        print(f"  {Colors.MAGENTA}📤 查询参数:{Colors.RESET}")
        for key, value in params.items():
            print(f"      {key}: {value}")
    
    if body:
        print(f"  {Colors.MAGENTA}📤 请求体:{Colors.RESET}")
        formatted_body = json.dumps(body, ensure_ascii=False, indent=6)
        for line in formatted_body.split('\n'):
            print(f"    {line}")


def print_response(resp: httpx.Response, success: bool):
    """打印响应信息"""
    status_color = Colors.GREEN if resp.status_code == 200 else Colors.RED
    result_color = Colors.GREEN if success else Colors.RED
    status_icon = "✅" if success else "❌"
    
    print(f"  {Colors.MAGENTA}📥 状态码:{Colors.RESET} {status_color}{resp.status_code}{Colors.RESET}")
    
    try:
        data = resp.json()
        formatted = json.dumps(data, ensure_ascii=False, indent=4)
        lines = formatted.split('\n')
        
        print(f"  {Colors.MAGENTA}📥 响应体:{Colors.RESET}")
        
        # 如果太长，截断显示
        max_lines = 35
        if len(lines) > max_lines:
            for line in lines[:max_lines - 5]:
                print(f"    {line}")
            print(f"    {Colors.YELLOW}... (共 {len(lines)} 行, 省略 {len(lines) - max_lines + 5} 行) ...{Colors.RESET}")
            for line in lines[-3:]:
                print(f"    {line}")
        else:
            for line in lines:
                print(f"    {line}")
        
        print(f"\n  {status_icon} {result_color}{'测试通过' if success else '测试失败'}{Colors.RESET}")
        
    except Exception as e:
        print(f"  {Colors.MAGENTA}📥 响应:{Colors.RESET} {resp.text[:500]}")
        print(f"  {Colors.RED}❌ JSON解析失败: {e}{Colors.RESET}")


def test_api(client: httpx.Client, method: str, path: str, 
             params: Optional[dict] = None, body: Optional[dict] = None,
             description: str = "") -> bool:
    """测试单个 API"""
    
    if description:
        print(f"\n{Colors.YELLOW}📌 {description}{Colors.RESET}")
    
    print_request(method, path, params, body)
    
    try:
        url = f"{API_BASE}{path}"
        
        if method == "GET":
            resp = client.get(url, params=params)
        elif method == "POST":
            resp = client.post(url, json=body)
        elif method == "PUT":
            resp = client.put(url, json=body)
        elif method == "DELETE":
            resp = client.delete(url)
        else:
            print(f"  {Colors.RED}❌ 不支持的方法: {method}{Colors.RESET}")
            return False
        
        data = resp.json()
        success = data.get('success', False) if isinstance(data, dict) else resp.status_code == 200
        print_response(resp, success)
        return success
        
    except httpx.ConnectError:
        print(f"  {Colors.RED}❌ 连接失败: 请确认服务已启动 (python3 main.py){Colors.RESET}")
        return False
    except Exception as e:
        print(f"  {Colors.RED}❌ 请求异常: {e}{Colors.RESET}")
        return False


def main():
    """主测试函数"""
    print(f"\n{Colors.BOLD}{'=' * 70}")
    print(f"🧪 陶瓷车间后端 - 完整 API 测试")
    print(f"{'=' * 70}{Colors.RESET}")
    print(f"📍 API 地址: {API_BASE}")
    print(f"🕐 测试时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"📋 共计测试: 24 个 API 端点")
    
    results = {"passed": 0, "failed": 0, "tests": []}
    
    with httpx.Client(timeout=10.0) as client:
        
        # ============================================================
        # 1. 健康检查 API (3个)
        # ============================================================
        print_header("1️⃣  健康检查 API (3个)")
        
        tests = [
            ("GET", "/api/health", None, None, "系统健康状态"),
            ("GET", "/api/health/plc", None, None, "PLC连接状态"),
            ("GET", "/api/health/database", None, None, "数据库连接状态"),
        ]
        
        for method, path, params, body, desc in tests:
            success = test_api(client, method, path, params, body, desc)
            results["tests"].append({"api": f"{method} {path}", "passed": success})
            if success:
                results["passed"] += 1
            else:
                results["failed"] += 1
        
        # ============================================================
        # 2. 料仓 API (4个测试)
        # ============================================================
        print_header("2️⃣  料仓 API (4个测试)")
        
        tests = [
            ("GET", "/api/hopper/list", None, None, "获取所有料仓列表"),
            ("GET", "/api/hopper/list", {"hopper_type": "short_hopper"}, None, "按类型筛选料仓"),
            ("GET", "/api/hopper/short_hopper_1", None, None, "获取料仓实时数据"),
            ("GET", "/api/hopper/short_hopper_1/history", 
             {"module_type": "WeighSensor", "fields": "weight,feed_rate", "interval": "5m"}, 
             None, "获取料仓历史数据"),
        ]
        
        for method, path, params, body, desc in tests:
            success = test_api(client, method, path, params, body, desc)
            results["tests"].append({"api": f"{method} {path}", "passed": success})
            if success:
                results["passed"] += 1
            else:
                results["failed"] += 1
        
        # ============================================================
        # 3. 辊道窑 API (4个)
        # ============================================================
        print_header("3️⃣  辊道窑 API (4个)")
        
        tests = [
            ("GET", "/api/roller/info", None, None, "获取辊道窑信息"),
            ("GET", "/api/roller/realtime", None, None, "获取辊道窑实时数据"),
            ("GET", "/api/roller/history", 
             {"module_type": "TemperatureSensor", "zone": "zone1", "interval": "5m"}, 
             None, "获取辊道窑历史数据"),
            ("GET", "/api/roller/zone/zone1", None, None, "获取指定温区数据"),
        ]
        
        for method, path, params, body, desc in tests:
            success = test_api(client, method, path, params, body, desc)
            results["tests"].append({"api": f"{method} {path}", "passed": success})
            if success:
                results["passed"] += 1
            else:
                results["failed"] += 1
        
        # ============================================================
        # 4. SCR API (3个)
        # ============================================================
        print_header("4️⃣  SCR 设备 API (3个)")
        
        tests = [
            ("GET", "/api/scr/list", None, None, "获取SCR设备列表"),
            ("GET", "/api/scr/scr_1", None, None, "获取SCR实时数据"),
            ("GET", "/api/scr/scr_1/history", 
             {"module_type": "FlowMeter", "fields": "flow_rate,total_flow", "interval": "5m"}, 
             None, "获取SCR历史数据"),
        ]
        
        for method, path, params, body, desc in tests:
            success = test_api(client, method, path, params, body, desc)
            results["tests"].append({"api": f"{method} {path}", "passed": success})
            if success:
                results["passed"] += 1
            else:
                results["failed"] += 1
        
        # ============================================================
        # 5. 风机 API (3个)
        # ============================================================
        print_header("5️⃣  风机设备 API (3个)")
        
        tests = [
            ("GET", "/api/fan/list", None, None, "获取风机设备列表"),
            ("GET", "/api/fan/fan_1", None, None, "获取风机实时数据"),
            ("GET", "/api/fan/fan_1/history", 
             {"fields": "Pt,ImpEp", "interval": "10m"}, 
             None, "获取风机历史数据"),
        ]
        
        for method, path, params, body, desc in tests:
            success = test_api(client, method, path, params, body, desc)
            results["tests"].append({"api": f"{method} {path}", "passed": success})
            if success:
                results["passed"] += 1
            else:
                results["failed"] += 1
        
        # ============================================================
        # 6. 配置 API (4个)
        # ============================================================
        print_header("6️⃣  配置 API (4个)")
        
        tests = [
            ("GET", "/api/config/server", None, None, "获取服务器配置"),
            ("GET", "/api/config/plc", None, None, "获取PLC配置"),
            ("PUT", "/api/config/plc", None, 
             {"ip_address": "192.168.50.223", "poll_interval": 5}, 
             "更新PLC配置"),
            ("POST", "/api/config/plc/test", None, None, "测试PLC连接"),
        ]
        
        for method, path, params, body, desc in tests:
            success = test_api(client, method, path, params, body, desc)
            results["tests"].append({"api": f"{method} {path}", "passed": success})
            if success:
                results["passed"] += 1
            else:
                results["failed"] += 1
    
    # ============================================================
    # 测试结果汇总
    # ============================================================
    print_header("📊 测试结果汇总")
    
    total = results["passed"] + results["failed"]
    pass_rate = (results["passed"] / total * 100) if total > 0 else 0
    
    print(f"\n  {Colors.BOLD}总计测试:{Colors.RESET} {total} 个 API")
    print(f"  {Colors.GREEN}✅ 通过:{Colors.RESET} {results['passed']} 个")
    print(f"  {Colors.RED}❌ 失败:{Colors.RESET} {results['failed']} 个")
    print(f"  {Colors.BOLD}通过率:{Colors.RESET} {pass_rate:.1f}%")
    
    # 显示失败的测试
    failed_tests = [t for t in results["tests"] if not t["passed"]]
    if failed_tests:
        print(f"\n  {Colors.RED}失败的测试:{Colors.RESET}")
        for t in failed_tests:
            print(f"    ❌ {t['api']}")
    
    # 最终结果
    if results["failed"] == 0:
        print(f"\n  {Colors.GREEN}{Colors.BOLD}🎉 所有 API 测试通过!{Colors.RESET}")
    else:
        print(f"\n  {Colors.YELLOW}⚠️  部分 API 测试失败，请检查上述日志{Colors.RESET}")
    
    print("\n" + "=" * 70 + "\n")
    
    return results["failed"] == 0


if __name__ == "__main__":
    import sys
    success = main()
    sys.exit(0 if success else 1)
