# ============================================================
# PLC DB6 数据块测试脚本
# ============================================================
# 数据结构 (根据 TIA Portal 实际配置):
# WeighSensor (Struct, offset 0.0-13):
#   - BaseWeigh.GrossWeigh (Word, 0.0)
#   - BaseWeigh.NetWeigh (Word, 2.0)
#   - StatusWord (Word, 4.0)
#   - AdvWeigh.GrossWeigh (DWord, 6.0)
#   - AdvWeigh.NetWeigh (DWord, 10.0)
# FlowMeter (Struct, offset 14.0-23):
#   - RtFlow (DWord, 14.0)
#   - TotalFlow (DWord, 18.0)
#   - TotalFlowMilli (Word, 22.0)
# ModbusDevKit (Struct, offset 24.0-31):
#   - VoltageCH1 (Word, 24.0)
#   - VoltageCH2 (Word, 26.0)
#   - AmpereCH1 (Word, 28.0)
#   - AmpereCH2 (Word, 30.0)
# WaterMeter (Struct, offset 32.0-39):
#   - Flow (DWord, 32.0)
#   - Total_Flow (DWord, 36.0)
# TEST (Array[0..8] of Byte, offset 40.0)
# ============================================================

import snap7
import struct
import sys

# PLC 配置
IP = "192.168.50.223"
RACK = 0
SLOT = 1
DB_NUMBER = 6

def get_word(data: bytes, offset: int) -> int:
    """读取 WORD (uint16) - Big Endian"""
    return struct.unpack('>H', data[offset:offset+2])[0]

def get_dword(data: bytes, offset: int) -> int:
    """读取 DWORD (uint32) - Big Endian"""
    return struct.unpack('>I', data[offset:offset+4])[0]

def get_real(data: bytes, offset: int) -> float:
    """读取 REAL (float32) - Big Endian"""
    return struct.unpack('>f', data[offset:offset+4])[0]

def parse_weigh_sensor(data: bytes):
    """解析称重传感器数据 (offset 0-13)"""
    gross_weigh_base = get_word(data, 0)      # 基础毛重 Word
    net_weigh_base = get_word(data, 2)        # 基础净重 Word
    status_word = get_word(data, 4)           # 状态字 Word
    gross_weigh_adv = get_dword(data, 6)      # 高级毛重 DWord
    net_weigh_adv = get_dword(data, 10)       # 高级净重 DWord
    
    print(f"\n【称重传感器 WeighSensor】")
    print(f"  基础毛重 (BaseWeigh.GrossWeigh): {gross_weigh_base} (0x{gross_weigh_base:04X})")
    print(f"  基础净重 (BaseWeigh.NetWeigh):   {net_weigh_base} (0x{net_weigh_base:04X})")
    print(f"  状态字 (StatusWord):             {status_word} (0x{status_word:04X})")
    print(f"  高级毛重 (AdvWeigh.GrossWeigh):  {gross_weigh_adv} (0x{gross_weigh_adv:08X})")
    print(f"  高级净重 (AdvWeigh.NetWeigh):    {net_weigh_adv} (0x{net_weigh_adv:08X})")
    
    return {
        "base_gross": gross_weigh_base,
        "base_net": net_weigh_base,
        "status": status_word,
        "adv_gross": gross_weigh_adv,
        "adv_net": net_weigh_adv
    }

def parse_flow_meter(data: bytes):
    """解析流量计数据 (offset 14-23)"""
    rt_flow = get_dword(data, 14)             # 实时流量 DWord
    total_flow = get_dword(data, 18)          # 累计流量 DWord
    total_flow_milli = get_word(data, 22)     # 累计流量小数 Word
    
    print(f"\n【流量计 FlowMeter】")
    print(f"  实时流量 (RtFlow):              {rt_flow} (0x{rt_flow:08X})")
    print(f"  累计流量 (TotalFlow):           {total_flow} (0x{total_flow:08X})")
    print(f"  累计流量小数 (TotalFlowMilli):  {total_flow_milli} (0x{total_flow_milli:04X})")
    
    return {
        "rt_flow": rt_flow,
        "total_flow": total_flow,
        "total_flow_milli": total_flow_milli
    }

def parse_modbus_devkit(data: bytes):
    """解析 Modbus 设备数据 (offset 24-31)"""
    voltage_ch1 = get_word(data, 24)          # 电压通道1 Word
    voltage_ch2 = get_word(data, 26)          # 电压通道2 Word
    ampere_ch1 = get_word(data, 28)           # 电流通道1 Word
    ampere_ch2 = get_word(data, 30)           # 电流通道2 Word
    
    # 根据实际缩放因子转换 (假设 1E+0 表示不缩放)
    v_ch1 = voltage_ch1 / 10.0  # 可能是十分位
    v_ch2 = voltage_ch2 / 10.0
    a_ch1 = ampere_ch1 / 10.0
    a_ch2 = ampere_ch2 / 10.0
    
    print(f"\n【Modbus 设备 ModbusDevKit】")
    print(f"  电压通道1 (VoltageCH1): {v_ch1:.1f} V (原始: {voltage_ch1})")
    print(f"  电压通道2 (VoltageCH2): {v_ch2:.1f} V (原始: {voltage_ch2})")
    print(f"  电流通道1 (AmpereCH1):  {a_ch1:.1f} A (原始: {ampere_ch1})")
    print(f"  电流通道2 (AmpereCH2):  {a_ch2:.1f} A (原始: {ampere_ch2})")
    
    return {
        "voltage_ch1": v_ch1,
        "voltage_ch2": v_ch2,
        "ampere_ch1": a_ch1,
        "ampere_ch2": a_ch2
    }

def parse_water_meter(data: bytes):
    """解析水表数据 (offset 32-39)"""
    flow = get_dword(data, 32)                # 流量 DWord
    total_flow = get_dword(data, 36)          # 累计流量 DWord
    
    print(f"\n【水表 WaterMeter】")
    print(f"  流量 (Flow):        {flow} (0x{flow:08X})")
    print(f"  累计流量 (Total_Flow): {total_flow} (0x{total_flow:08X})")
    
    return {
        "flow": flow,
        "total_flow": total_flow
    }

def test_db6():
    """测试 DB6 数据块读取"""
    print("=" * 70)
    print("PLC DB6 (SlaveData) 数据块测试")
    print("=" * 70)
    print(f"连接: {IP}, Rack={RACK}, Slot={SLOT}")
    print(f"读取: DB{DB_NUMBER}, 完整数据结构 (0-48 字节)")
    print("=" * 70)
    
    client = snap7.client.Client()
    
    try:
        # 1. 连接
        client.connect(IP, RACK, SLOT)
        
        if not client.get_connected():
            print("❌ PLC 连接失败")
            return
            
        print("✅ PLC 连接成功!")
        
        # 2. 读取 DB6 全部数据 (0-48 字节，包含 TEST 数组)
        data = client.db_read(DB_NUMBER, 0, 49)
        
        print(f"\n原始数据 ({len(data)} 字节):")
        # 按 16 字节一行显示，方便查看
        for i in range(0, len(data), 16):
            chunk = data[i:i+16]
            hex_str = ' '.join(f'{b:02X}' for b in chunk)
            offset_str = f"[{i:3d}-{min(i+15, len(data)-1):3d}]"
            print(f"  {offset_str} {hex_str}")
        
        # 3. 解析数据
        print("\n" + "=" * 70)
        print("数据解析结果 (根据 TIA Portal DB6 实际结构)")
        print("=" * 70)
        
        # WeighSensor: offset 0-13
        weigh_data = parse_weigh_sensor(data)
        
        # FlowMeter: offset 14-23
        flow_data = parse_flow_meter(data)
        
        # ModbusDevKit: offset 24-31
        modbus_data = parse_modbus_devkit(data)
        
        # WaterMeter: offset 32-39
        water_data = parse_water_meter(data)
        
        # TEST Array: offset 40-48
        print(f"\n【测试数组 TEST [0..8]】")
        test_array = data[40:49]
        print(f"  数据: {' '.join(f'{b:02X}' for b in test_array)}")
        print(f"  十进制: {list(test_array)}")
        
        # 4. 汇总结果
        print("\n" + "=" * 70)
        print("测试完成! 数据读取正常")
        print("=" * 70)
        print("\n💡 提示:")
        print("  - 如果数值显示异常，请检查 PLC 中的数据缩放因子")
        print("  - Word/DWord 使用 Big Endian 字节序")
        print("  - 部分字段可能需要根据实际传感器调整解析逻辑")
        
    except Exception as e:
        print(f"❌ 发生错误: {e}")
        import traceback
        traceback.print_exc()
        
    finally:
        if client.get_connected():
            client.disconnect()
            print("\n🔌 连接已关闭")

if __name__ == "__main__":
    test_db6()
