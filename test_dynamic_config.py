# ============================================================
# 动态配置测试脚本 - 使用 YAML 配置解析 PLC 数据
# ============================================================
# 优势:
# 1. 无需修改代码，只需修改 configs/plc_mapping.yaml
# 2. 前后端可独立开发，不等 PLC 调试
# 3. 支持多个 DB 块灵活配置
# 4. 易于维护和扩展
# ============================================================

import snap7
import sys
from pathlib import Path

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent))

from app.plc.dynamic_parser import DynamicPLCParser

# PLC 配置
IP = "192.168.50.223"
RACK = 0
SLOT = 1

def test_dynamic_parsing():
    """测试动态配置解析"""
    print("=" * 70)
    print("PLC 动态配置测试 - 基于 YAML 配置文件")
    print("=" * 70)
    
    # 1. 创建解析器
    try:
        parser = DynamicPLCParser("configs/plc_mapping.yaml")
        print("✅ 配置文件加载成功!")
    except Exception as e:
        print(f"❌ 配置文件加载失败: {e}")
        return
    
    # 2. 列出所有可用的 DB 块
    print("\n" + "=" * 70)
    print("可用的 DB 块配置:")
    print("=" * 70)
    available_dbs = parser.list_available_dbs()
    for db in available_dbs:
        status = "✅ 启用" if db['enabled'] else "❌ 禁用"
        print(f"  [{db['key']}]")
        print(f"    DB{db['db_number']}: {db['description']}")
        print(f"    状态: {status}\n")
    
    # 3. 连接 PLC
    print("=" * 70)
    print(f"连接 PLC: {IP}, Rack={RACK}, Slot={SLOT}")
    print("=" * 70)
    
    client = snap7.client.Client()
    
    try:
        client.connect(IP, RACK, SLOT)
        
        if not client.get_connected():
            print("❌ PLC 连接失败")
            return
        
        print("✅ PLC 连接成功!")
        
        # 4. 读取并解析启用的 DB 块
        for db in available_dbs:
            if not db['enabled']:
                print(f"\n⏭️  跳过 DB{db['db_number']} (未启用)")
                continue
            
            db_key = db['key']
            db_config = parser.get_db_config(db_key)
            db_number = db_config['db_number']
            total_size = db_config['total_size']
            
            print(f"\n{'=' * 70}")
            print(f"读取 DB{db_number}: {db_config['description']}")
            print(f"{'=' * 70}")
            
            try:
                # 读取数据
                data = client.db_read(db_number, 0, total_size)
                print(f"✅ 读取成功 ({len(data)} 字节)")
                
                # 显示原始数据
                print(f"\n原始数据 (十六进制):")
                for i in range(0, len(data), 16):
                    chunk = data[i:i+16]
                    hex_str = ' '.join(f'{b:02X}' for b in chunk)
                    print(f"  [{i:3d}-{min(i+15, len(data)-1):3d}] {hex_str}")
                
                # 动态解析数据
                parsed = parser.parse_db_block(db_key, data)
                
                # 格式化输出
                print(f"\n{parser.format_output(parsed)}")
                
            except Exception as e:
                print(f"❌ 处理 DB{db_number} 失败: {e}")
                import traceback
                traceback.print_exc()
        
        print("\n" + "=" * 70)
        print("测试完成!")
        print("=" * 70)
        print("\n💡 提示:")
        print("  - 修改字段偏移量: 编辑 configs/plc_mapping.yaml")
        print("  - 添加新字段: 在对应的 fields 列表中添加配置")
        print("  - 添加新 DB 块: 在配置文件中新增 dbX_xxx 配置")
        print("  - 调整缩放因子: 修改 scale 参数")
        print("  - 启用/禁用分组: 修改 enabled 参数")
        
    except Exception as e:
        print(f"❌ 发生错误: {e}")
        import traceback
        traceback.print_exc()
    
    finally:
        if client.get_connected():
            client.disconnect()
            print("\n🔌 连接已关闭")


def test_config_modification_example():
    """演示如何修改配置"""
    print("\n" + "=" * 70)
    print("📝 配置文件修改示例")
    print("=" * 70)
    print("""
# 示例 1: 修改字段偏移量
# 如果 PLC 开发人员告诉你 "voltage_ch1 偏移量改为 25"
# 只需修改 configs/plc_mapping.yaml:

modbus_devkit:
  fields:
    - name: "voltage_ch1"
      offset: 25  # ← 改这里
      
# 示例 2: 添加新字段
# PLC 添加了新的温度传感器:

modbus_devkit:
  fields:
    - name: "temperature_ch1"  # ← 新增
      display_name: "温度通道1"
      offset: 32
      data_type: "WORD"
      unit: "°C"
      scale: 0.1

# 示例 3: 调整缩放因子
# 如果数值不对，修改 scale:

    - name: "voltage_ch1"
      scale: 0.01  # ← 从 0.1 改为 0.01

# 示例 4: 暂时禁用某个分组
# 传感器还没接好，暂时不解析:

flow_meter:
  enabled: false  # ← 改为 false

# 示例 5: 添加新的 DB 块
# 复制现有配置，修改 db_number 和字段即可

db100_new_device:
  db_number: 100
  description: "新设备数据"
  total_size: 50
  enabled: true
  sensor_group:
    enabled: true
    fields:
      - name: "temp"
        display_name: "温度"
        offset: 0
        data_type: "WORD"
        unit: "°C"
        scale: 0.1
    """)


if __name__ == "__main__":
    test_dynamic_parsing()
    test_config_modification_example()
