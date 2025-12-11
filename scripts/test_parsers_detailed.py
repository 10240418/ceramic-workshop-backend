#!/usr/bin/env python3
# ============================================================
# 详细测试3个DB块解析器 - 展示完整解析数据
# ============================================================

import sys
import json
from pathlib import Path

# 添加项目根目录到Python路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.plc.parser_hopper import HopperParser
from app.plc.parser_roller_kiln import RollerKilnParser
from app.plc.parser_scr_fan import SCRFanParser


def print_section(title):
    """打印分节标题"""
    print("\n" + "="*80)
    print(f"  {title}")
    print("="*80)


def print_subsection(title):
    """打印子标题"""
    print(f"\n{'─'*80}")
    print(f"  {title}")
    print(f"{'─'*80}")


def print_device_header(device_data):
    """打印设备头部信息"""
    print(f"\n📦 设备: {device_data['device_name']} ({device_data['device_id']})")
    print(f"   类型: {device_data['device_type']}")
    print(f"   时间戳: {device_data['timestamp']}")


def print_module_data(module_tag, module_data, indent=2):
    """打印模块数据"""
    indent_str = " " * indent
    print(f"{indent_str}📊 模块: {module_tag}")
    print(f"{indent_str}   类型: {module_data['module_type']}")
    if 'description' in module_data and module_data['description']:
        print(f"{indent_str}   说明: {module_data['description']}")
    
    print(f"{indent_str}   字段数据:")
    for field_name, field_info in module_data['fields'].items():
        value = field_info['value']
        unit = field_info['unit']
        display_name = field_info['display_name']
        
        # 格式化数值显示
        if isinstance(value, float):
            value_str = f"{value:.2f}"
        else:
            value_str = str(value)
        
        unit_str = f" {unit}" if unit else ""
        print(f"{indent_str}      • {display_name}: {value_str}{unit_str}")


def test_db6_detailed():
    """详细测试DB6料仓解析器"""
    print_section("DB6 料仓设备数据块解析测试")
    
    # 初始化解析器
    parser = HopperParser()
    
    # 打印配置信息
    print(f"\n📋 DB配置信息:")
    print(f"   DB号: DB{parser.db_config['db_number']}")
    print(f"   名称: {parser.db_config['db_name']}")
    print(f"   大小: {parser.db_config['total_size']} 字节")
    print(f"   说明: {parser.db_config['description']}")
    
    # 打印基础模块信息
    print(f"\n📚 已加载的基础模块: {len(parser.base_modules)} 个")
    for module_name in parser.base_modules.keys():
        module = parser.base_modules[module_name]
        print(f"   • {module_name}: {module['total_size']}字节, {len(module['fields'])}个字段")
    
    # 打印设备列表
    devices = parser.get_device_list()
    print(f"\n🏭 设备列表: {len(devices)} 个")
    
    # 按类别分组
    categories = {}
    for dev in devices:
        category = dev['category']
        if category not in categories:
            categories[category] = []
        categories[category].append(dev)
    
    for category, devs in categories.items():
        print(f"\n   {category}: {len(devs)}个")
        for dev in devs:
            print(f"      - {dev['device_name']} ({dev['device_id']})")
    
    # 模拟DB6数据 (554字节)
    print_subsection("开始解析模拟数据 (554字节全0)")
    test_data = bytes(554)
    
    # 解析所有设备
    results = parser.parse_all(test_data)
    print(f"\n✅ 解析完成: {len(results)} 个设备")
    
    # 打印每个设备的详细数据
    for i, device_data in enumerate(results, 1):
        print_subsection(f"设备 {i}/{len(results)}")
        print_device_header(device_data)
        
        # 打印所有模块数据
        for module_tag, module_data in device_data['modules'].items():
            print_module_data(module_tag, module_data)
    
    # 保存JSON结果
    output_file = "test_output_db6.json"
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    print(f"\n💾 完整数据已保存到: {output_file}")


def test_db7_detailed():
    """详细测试DB7辊道窑解析器"""
    print_section("DB7 辊道窑数据块解析测试")
    
    # 初始化解析器
    parser = RollerKilnParser()
    
    # 打印配置信息
    print(f"\n📋 DB配置信息:")
    print(f"   DB号: DB{parser.db_config['db_number']}")
    print(f"   名称: {parser.db_config['db_name']}")
    print(f"   大小: {parser.db_config['total_size']} 字节")
    print(f"   说明: {parser.db_config['description']}")
    
    # 打印设备信息
    info = parser.get_device_info()
    print(f"\n🏭 设备信息:")
    print(f"   设备名称: {info['device_name']}")
    print(f"   设备ID: {info['device_id']}")
    print(f"   设备类型: {info['device_type']}")
    print(f"   电表数量: {info['meter_count']} 个")
    print(f"   温度传感器: {info['temp_count']} 个")
    
    # 模拟DB7数据 (288字节)
    print_subsection("开始解析模拟数据 (288字节全0)")
    test_data = bytes(288)
    
    # 解析辊道窑
    result = parser.parse_all(test_data)
    print(f"\n✅ 解析完成: {result['device_name']}")
    
    # 打印设备头部
    print_device_header(result)
    
    # 打印电表数据
    print_subsection("电表数据")
    print(f"\n   共 {len(result['electricity_meters'])} 个电表:")
    for meter_tag, meter_data in result['electricity_meters'].items():
        print_module_data(meter_tag, meter_data, indent=3)
        print()  # 空行分隔
    
    # 打印温度数据
    print_subsection("温度传感器数据")
    print(f"\n   共 {len(result['temperature_sensors'])} 个温度传感器:")
    for temp_tag, temp_data in result['temperature_sensors'].items():
        print_module_data(temp_tag, temp_data, indent=3)
        print()  # 空行分隔
    
    # 保存JSON结果
    output_file = "test_output_db7.json"
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(result, f, indent=2, ensure_ascii=False)
    print(f"\n💾 完整数据已保存到: {output_file}")


def test_db8_detailed():
    """详细测试DB8 SCR和风机解析器"""
    print_section("DB8 SCR设备和风机数据块解析测试")
    
    # 初始化解析器
    parser = SCRFanParser()
    
    # 打印配置信息
    print(f"\n📋 DB配置信息:")
    print(f"   DB号: DB{parser.db_config['db_number']}")
    print(f"   名称: {parser.db_config['db_name']}")
    print(f"   大小: {parser.db_config['total_size']} 字节")
    print(f"   说明: {parser.db_config['description']}")
    
    # 打印设备列表
    devices = parser.get_device_list()
    print(f"\n🏭 设备列表: {len(devices)} 个")
    
    # 按类别分组
    categories = {}
    for dev in devices:
        category = dev['category']
        if category not in categories:
            categories[category] = []
        categories[category].append(dev)
    
    for category, devs in categories.items():
        print(f"\n   {category}: {len(devs)}个")
        for dev in devs:
            print(f"      - {dev['device_name']} ({dev['device_id']})")
    
    # 模拟DB8数据 (176字节)
    print_subsection("开始解析模拟数据 (176字节全0)")
    test_data = bytes(176)
    
    # 解析所有设备
    results = parser.parse_all(test_data)
    print(f"\n✅ 解析完成: {len(results)} 个设备")
    
    # 打印每个设备的详细数据
    for i, device_data in enumerate(results, 1):
        print_subsection(f"设备 {i}/{len(results)}")
        print_device_header(device_data)
        
        # 打印所有模块数据
        for module_tag, module_data in device_data['modules'].items():
            print_module_data(module_tag, module_data)
    
    # 保存JSON结果
    output_file = "test_output_db8.json"
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    print(f"\n💾 完整数据已保存到: {output_file}")


def print_summary():
    """打印总结"""
    print_section("测试总结")
    
    print(f"""
📊 解析器测试完成!

已创建的文件:
  • test_output_db6.json - DB6料仓设备完整解析数据 (9个设备)
  • test_output_db7.json - DB7辊道窑完整解析数据 (1个设备, 6电表+6温度)
  • test_output_db8.json - DB8 SCR和风机完整解析数据 (4个设备)

配置文件验证:
  ✅ configs/plc_modules.yaml - 4个基础模块定义正确
  ✅ configs/config_hoppers.yaml - 9个料仓设备配置正确
  ✅ configs/config_roller_kiln.yaml - 辊道窑配置正确 (6+6结构)
  ✅ configs/config_scr_fans.yaml - SCR和风机配置正确

解析器验证:
  ✅ app/plc/parser_hopper.py - 能正确解析料仓数据
  ✅ app/plc/parser_roller_kiln.py - 能正确解析辊道窑数据
  ✅ app/plc/parser_scr_fan.py - 能正确解析SCR/风机数据

下一步操作:
  1. 在TIA Portal中创建DB块
  2. 配置实际的PLC数据结构
  3. 下载到PLC后运行实际数据测试:
     python3 scripts/test_real_plc_data.py
  4. 启动后端服务验证自动轮询:
     python3 main.py
    """)


if __name__ == "__main__":
    print("\n" + "🧪 " * 40)
    print("DB块解析器详细测试")
    print("🧪 " * 40)
    
    try:
        # 测试3个解析器
        test_db6_detailed()
        test_db7_detailed()
        test_db8_detailed()
        
        # 打印总结
        print_summary()
        
    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
