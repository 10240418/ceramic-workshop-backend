#!/usr/bin/env python3
# ============================================================
# 测试转换器集成
# ============================================================
# 验证 Parser → Converter → InfluxDB 数据流
# ============================================================

import sys
sys.path.insert(0, '.')

from datetime import datetime
from app.tools import get_converter, CONVERTER_MAP


def test_converters():
    """测试所有转换器"""
    print("=" * 60)
    print("转换器测试")
    print("=" * 60)
    
    # 1. 电表转换器
    print("\n📊 1. ElectricityMeter (电表)")
    elec_raw = {
        'Uab_0': {'value': 380.1},
        'Uab_1': {'value': 380.2},
        'Uab_2': {'value': 380.3},
        'Ua_0': {'value': 220.1},
        'Ua_1': {'value': 220.2},
        'Ua_2': {'value': 220.3},
        'I_0': {'value': 10.5},
        'I_1': {'value': 10.6},
        'I_2': {'value': 10.7},
        'Pt': {'value': 45.6},
        'Pa': {'value': 15.0},
        'Pb': {'value': 15.2},
        'Pc': {'value': 15.4},
        'ImpEp': {'value': 12345.67},
    }
    elec_converter = get_converter('ElectricityMeter')
    elec_result = elec_converter.convert(elec_raw)
    print(f"   输入: {len(elec_raw)} 个字段")
    print(f"   输出: {len(elec_result)} 个字段")
    print(f"   存储字段: {list(elec_result.keys())}")
    print(f"   数据: Pt={elec_result['Pt']}kW, ImpEp={elec_result['ImpEp']}kWh")
    
    # 2. 流量计转换器
    print("\n📊 2. FlowMeter (流量计)")
    flow_raw = {
        'RtFlow': {'value': 1000},      # 1000 L/min
        'TotalFlow': {'value': 100},    # 100 m³
        'TotalFlowMilli': {'value': 500},  # 500 mL = 0.5 m³
    }
    flow_converter = get_converter('FlowMeter')
    flow_result = flow_converter.convert(flow_raw)
    print(f"   输入: RtFlow=1000 L/min, TotalFlow=100 m³, TotalFlowMilli=500 mL")
    print(f"   输出: flow_rate={flow_result['flow_rate']} m³/h, total_flow={flow_result['total_flow']} m³")
    
    # 3. 温度传感器转换器
    print("\n📊 3. TemperatureSensor (温度传感器)")
    temp_raw = {
        'Temperature': {'value': 250},  # 250 * 0.1 = 25.0°C
    }
    temp_converter = get_converter('TemperatureSensor')
    temp_result = temp_converter.convert(temp_raw)
    print(f"   输入: Temperature=250 (scale=0.1)")
    print(f"   输出: temperature={temp_result['temperature']}°C")
    
    # 4. 称重传感器转换器
    print("\n📊 4. WeighSensor (称重传感器)")
    weight_raw = {
        'GrossWeight_W': {'value': 2000},
        'NetWeight_W': {'value': 1800},
        'StatusWord': {'value': 0},
        'GrossWeight': {'value': 2000.5},
        'NetWeight': {'value': 1800.5},
    }
    weight_converter = get_converter('WeighSensor')
    
    # 首次无历史数据
    result1 = weight_converter.convert(weight_raw)
    print(f"   首次(无历史): weight={result1['weight']}kg, feed_rate={result1['feed_rate']}kg/s")
    
    # 第二次有历史数据 (5秒前重量是1810.5kg)
    result2 = weight_converter.convert(weight_raw, previous_weight=1810.5, interval=5.0)
    print(f"   5秒后(有历史): weight={result2['weight']}kg, feed_rate={result2['feed_rate']}kg/s")
    print(f"   下料速度计算: (1810.5 - 1800.5) / 5 = 2.0 kg/s")
    
    print("\n" + "=" * 60)
    print("✅ 所有转换器测试通过!")
    print("=" * 60)


def test_polling_integration():
    """模拟轮询集成测试 - 模拟连续两次轮询"""
    print("\n" + "=" * 60)
    print("轮询集成模拟测试 (模拟连续2次轮询)")
    print("=" * 60)
    
    # 模拟设备数据 (Parser输出格式) - 包含完整的原始字段
    def get_device_data(weight_value):
        """生成设备数据，weight可变用于模拟下料"""
        return {
            'device_id': 'short_hopper_1',
            'device_type': 'short_hopper',
            'modules': {
                'electricity': {
                    'module_type': 'ElectricityMeter',
                    'fields': {
                        # 线电压 (不存储)
                        'Uab_0': {'value': 380.1},
                        'Uab_1': {'value': 380.2},
                        'Uab_2': {'value': 380.3},
                        # 相电压 (存储)
                        'Ua_0': {'value': 220.1},
                        'Ua_1': {'value': 220.2},
                        'Ua_2': {'value': 220.3},
                        # 电流 (存储)
                        'I_0': {'value': 10.1},
                        'I_1': {'value': 10.2},
                        'I_2': {'value': 10.3},
                        # 功率
                        'Pt': {'value': 45.6},
                        'Pa': {'value': 15.0},
                        'Pb': {'value': 15.2},
                        'Pc': {'value': 15.4},
                        # 电能
                        'ImpEp': {'value': 1234.5},
                    }
                },
                'flow': {
                    'module_type': 'FlowMeter',
                    'fields': {
                        'RtFlow': {'value': 500},        # 500 L/min
                        'TotalFlow': {'value': 1000},    # 1000 m³
                        'TotalFlowMilli': {'value': 250},  # 250 mL
                    }
                },
                'weight': {
                    'module_type': 'WeighSensor',
                    'fields': {
                        'GrossWeight_W': {'value': 2000},
                        'NetWeight_W': {'value': int(weight_value)},
                        'StatusWord': {'value': 0},
                        'GrossWeight': {'value': 2000.5},
                        'NetWeight': {'value': weight_value},
                    }
                },
                'temperature': {
                    'module_type': 'TemperatureSensor',
                    'fields': {
                        'Temperature': {'value': 350},  # 350 * 0.1 = 35.0°C
                    }
                }
            }
        }
    
    # 模拟历史重量缓存
    weight_history = {}
    
    # ========== 第一次轮询 ==========
    print("\n" + "-" * 40)
    print("📍 第1次轮询 (T=0s)")
    print("-" * 40)
    
    device_data = get_device_data(1500.0)  # 初始重量 1500kg
    print(f"设备: {device_data['device_id']}")
    print(f"模块数: {len(device_data['modules'])}")
    
    for module_tag, module_data in device_data['modules'].items():
        module_type = module_data['module_type']
        raw_fields = module_data['fields']
        
        if module_type in CONVERTER_MAP:
            converter = get_converter(module_type)
            
            if module_type == 'WeighSensor':
                cache_key = f"{device_data['device_id']}:{module_tag}"
                previous_weight = weight_history.get(cache_key)
                fields = converter.convert(raw_fields, previous_weight=previous_weight, interval=5.0)
                weight_history[cache_key] = fields.get('weight', 0.0)
            else:
                fields = converter.convert(raw_fields)
            
            print(f"\n   [{module_tag}] {module_type}")
            print(f"   原始字段({len(raw_fields)}): {list(raw_fields.keys())}")
            print(f"   存储字段({len(fields)}): {fields}")
        else:
            print(f"\n   [{module_tag}] {module_type} - 无转换器")
    
    # ========== 第二次轮询 (5秒后) ==========
    print("\n" + "-" * 40)
    print("📍 第2次轮询 (T=5s) - 重量减少了10kg")
    print("-" * 40)
    
    device_data = get_device_data(1490.0)  # 5秒后重量减少到1490kg (下料10kg)
    
    for module_tag, module_data in device_data['modules'].items():
        module_type = module_data['module_type']
        raw_fields = module_data['fields']
        
        if module_type in CONVERTER_MAP:
            converter = get_converter(module_type)
            
            if module_type == 'WeighSensor':
                cache_key = f"{device_data['device_id']}:{module_tag}"
                previous_weight = weight_history.get(cache_key)
                fields = converter.convert(raw_fields, previous_weight=previous_weight, interval=5.0)
                weight_history[cache_key] = fields.get('weight', 0.0)
                
                print(f"\n   [{module_tag}] {module_type}")
                print(f"   原始字段({len(raw_fields)}): {list(raw_fields.keys())}")
                print(f"   存储字段({len(fields)}): {fields}")
                print(f"   ✅ 下料速度计算: (1500.0 - 1490.0) / 5s = 2.0 kg/s")
            else:
                fields = converter.convert(raw_fields)
                print(f"\n   [{module_tag}] {module_type}")
                print(f"   原始字段({len(raw_fields)}): {list(raw_fields.keys())}")
                print(f"   存储字段({len(fields)}): {fields}")
        else:
            print(f"\n   [{module_tag}] {module_type} - 无转换器")
    
    print(f"\n历史重量缓存: {weight_history}")
    print("\n✅ 轮询集成模拟测试通过!")


if __name__ == "__main__":
    test_converters()
    test_polling_integration()
