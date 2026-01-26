#!/usr/bin/env python3
# ============================================================
# 文件说明: mock_polling_service.py - 模拟轮询服务
# ============================================================
# 功能:
# 1. 模拟PLC轮询，生成符合DB块结构的原始数据
# 2. 使用与正式代码相同的解析器和转换器
# 3. 将数据写入InfluxDB
# 4. 每4秒轮询一次
#
# 使用方法:
#   python tests/mock/mock_polling_service.py
#
# 停止方法:
#   Ctrl+C
# ============================================================

import sys
import os
import asyncio
import signal
from datetime import datetime
from typing import Dict, Any

# 添加项目根目录到路径
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, PROJECT_ROOT)

from mock_data_generator import MockDataGenerator
from config import get_settings
from app.core.influxdb import write_point
from app.plc.parser_hopper import HopperParser
from app.plc.parser_roller_kiln import RollerKilnParser
from app.plc.parser_scr_fan import SCRFanParser
from app.tools import get_converter, CONVERTER_MAP

settings = get_settings()

# ============================================================
# 配置
# ============================================================
POLL_INTERVAL = 6  # 轮询间隔 (秒) - 与后端保持一致

# 解析器实例
_parsers: Dict[int, Any] = {
    8: HopperParser(),
    9: RollerKilnParser(),
    10: SCRFanParser(),
}

# 历史重量缓存 (用于计算下料速度)
_weight_history: Dict[str, float] = {}

# 运行状态
_is_running = True


def signal_handler(sig, frame):
    """处理Ctrl+C信号"""
    global _is_running
    print("\n⏹️  收到停止信号，正在退出...")
    _is_running = False


def write_device_to_influx(device_data: Dict[str, Any], db_number: int, timestamp: datetime):
    """写入设备数据到InfluxDB（复用正式代码的逻辑）
    
    Args:
        device_data: 解析后的设备数据
        db_number: DB块号
        timestamp: 时间戳
    """
    global _weight_history
    
    device_id = device_data['device_id']
    device_type = device_data['device_type']
    
    # 遍历所有模块
    for module_tag, module_data in device_data['modules'].items():
        module_type = module_data['module_type']
        raw_fields = module_data['fields']
        
        # 使用转换器转换数据
        if module_type in CONVERTER_MAP:
            converter = get_converter(module_type)
            
            # 称重模块需要传入历史数据
            if module_type == 'WeighSensor':
                cache_key = f"{device_id}:{module_tag}"
                previous_weight = _weight_history.get(cache_key)
                
                fields = converter.convert(
                    raw_fields,
                    previous_weight=previous_weight,
                    interval=POLL_INTERVAL
                )
                
                # 更新历史缓存
                _weight_history[cache_key] = fields.get('weight', 0.0)
            else:
                fields = converter.convert(raw_fields)
        else:
            # 未知模块类型，直接提取原始值
            fields = {}
            for field_name, field_info in raw_fields.items():
                if isinstance(field_info, dict):
                    fields[field_name] = field_info.get('value', 0)
                else:
                    fields[field_name] = field_info
        
        # 跳过空字段
        if not fields:
            continue
        
        # 写入InfluxDB
        write_point(
            measurement="sensor_data",
            tags={
                "device_id": device_id,
                "device_type": device_type,
                "module_type": module_type,
                "module_tag": module_tag,
                "db_number": str(db_number)
            },
            fields=fields,
            timestamp=timestamp
        )


async def poll_mock_data():
    """模拟轮询主循环"""
    global _is_running
    
    print("=" * 60)
    print("🚀 模拟轮询服务启动")
    print("=" * 60)
    print(f"📊 轮询间隔: {POLL_INTERVAL}秒")
    print(f"📦 DB块: DB8(料仓), DB9(辊道窑), DB10(SCR/风机)")
    print(f"🔗 InfluxDB: {settings.influx_url}")
    print(f"📁 Bucket: {settings.influx_bucket}")
    print("=" * 60)
    print("按 Ctrl+C 停止服务")
    print("=" * 60)
    
    # 初始化数据生成器
    generator = MockDataGenerator()
    
    poll_count = 0
    
    while _is_running:
        try:
            poll_count += 1
            timestamp = datetime.now()
            
            print(f"\n[{timestamp.strftime('%H:%M:%S')}] 第 {poll_count} 次轮询...")
            
            # 生成所有DB块的模拟数据
            all_db_data = generator.generate_all_db_data()
            
            total_devices = 0
            
            # 遍历每个DB块
            for db_number, raw_data in all_db_data.items():
                parser = _parsers.get(db_number)
                if not parser:
                    print(f"  ⚠️  DB{db_number}: 未找到解析器")
                    continue
                
                # 解析原始数据
                devices = parser.parse_all(raw_data)
                
                # 写入InfluxDB
                for device in devices:
                    write_device_to_influx(device, db_number, timestamp)
                
                total_devices += len(devices)
                print(f"  ✅ DB{db_number}: {len(devices)}个设备数据已写入")
            
            print(f"  📊 共写入 {total_devices} 个设备数据")
            
        except Exception as e:
            print(f"  ❌ 轮询错误: {e}")
            import traceback
            traceback.print_exc()
        
        # 等待下次轮询
        await asyncio.sleep(POLL_INTERVAL)
    
    print("\n✅ 模拟轮询服务已停止")


def main():
    """主入口"""
    # 注册信号处理
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # 运行异步轮询
    try:
        asyncio.run(poll_mock_data())
    except KeyboardInterrupt:
        print("\n⏹️  服务已停止")


if __name__ == "__main__":
    main()
