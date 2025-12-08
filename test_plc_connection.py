# ============================================================
# PLC DB6 数据块测试脚本
# ============================================================
# 数据结构:
# TempSensor1: offset 0-5 (Temp, Humi, isOnline)
# TempSensor2: offset 6-11 (Temp, Humi, isOnline)
# Motor Status: offset 12-19 (Temp, Power, Voltage, Amp)
# Motor Control: offset 20-31 (Speed, Position, Torque)
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

def get_lreal(data: bytes, offset: int) -> float:
    """读取 LREAL (float64) - Big Endian"""
    return struct.unpack('>d', data[offset:offset+8])[0]

def get_real(data: bytes, offset: int) -> float:
    """读取 REAL (float32) - Big Endian"""
    return struct.unpack('>f', data[offset:offset+4])[0]

def parse_temp_sensor(data: bytes, offset: int, name: str):
    """解析温度传感器数据"""
    temp_raw = get_word(data, offset)
    humi_raw = get_word(data, offset + 2)
    is_online = get_word(data, offset + 4)
    
    temp = temp_raw / 10.0  # 十分位
    humi = humi_raw / 10.0  # 十分位
    
    print(f"\n【{name}】")
    print(f"  温度: {temp:.1f} °C (原始值: {temp_raw})")
    print(f"  湿度: {humi:.1f} % (原始值: {humi_raw})")
    print(f"  在线: {'✅ 是' if is_online else '❌ 否'} (原始值: {is_online})")
    
    return {"temp": temp, "humi": humi, "is_online": is_online}

def parse_motor_status(data: bytes, offset: int):
    """解析电机状态数据"""
    temp_raw = get_word(data, offset)
    power = get_word(data, offset + 2)
    voltage_raw = get_word(data, offset + 4)
    amp_raw = get_word(data, offset + 6)
    
    temp = temp_raw / 10.0
    voltage = voltage_raw / 10.0
    amp = amp_raw / 10.0
    
    print(f"\n【电机状态 Motor Status】")
    print(f"  温度: {temp:.1f} °C (原始值: {temp_raw})")
    print(f"  功率: {power} W (原始值: {power})")
    print(f"  电压: {voltage:.1f} V (原始值: {voltage_raw})")
    print(f"  电流: {amp:.1f} A (原始值: {amp_raw})")
    
    return {"temp": temp, "power": power, "voltage": voltage, "amp": amp}

def parse_motor_control(data: bytes, offset: int):
    """解析电机控制数据"""
    speed = get_word(data, offset)
    position = get_lreal(data, offset + 2)  # uint64 从 offset 22 开始，8字节
    torque = get_word(data, offset + 10)
    
    print(f"\n【电机控制 Motor Control】")
    print(f"  速度: {speed} rpm")
    print(f"  位置: {position}")
    print(f"  力矩: {torque}")
    
    return {"speed": speed, "position": position, "torque": torque}

def test_db6():
    """测试 DB6 数据块读取"""
    print("=" * 60)
    print("PLC DB6 数据块测试")
    print("=" * 60)
    print(f"连接: {IP}, Rack={RACK}, Slot={SLOT}")
    print(f"读取: DB{DB_NUMBER}, 全部数据")
    print("=" * 60)
    
    client = snap7.client.Client()
    
    try:
        # 1. 连接
        client.connect(IP, RACK, SLOT)
        
        if not client.get_connected():
            print("❌ PLC 连接失败")
            return
            
        print("✅ PLC 连接成功!")
        
        # 2. 读取 DB6 全部数据 (0-40 字节足够覆盖所有数据)
        data = client.db_read(DB_NUMBER, 0, 40)
        
        print(f"\n原始数据 ({len(data)} 字节):")
        print([hex(b) for b in data])
        
        # 3. 解析数据
        print("\n" + "=" * 60)
        print("数据解析结果")
        print("=" * 60)
        
        # TempSensor1: offset 0-5
        sensor1 = parse_temp_sensor(data, 0, "温度传感器1 TempSensor1")
        
        # TempSensor2: offset 6-11
        sensor2 = parse_temp_sensor(data, 6, "温度传感器2 TempSensor2")
        
        # Motor Status: offset 12-19
        motor_status = parse_motor_status(data, 12)
        
        # Motor Control: offset 20-31
        motor_control = parse_motor_control(data, 20)
        
        print("\n" + "=" * 60)
        print("测试完成!")
        print("=" * 60)
        
    except Exception as e:
        print(f"❌ 发生错误: {e}")
        import traceback
        traceback.print_exc()
        
    finally:
        if client.get_connected():
            client.disconnect()
            print("\n连接已关闭")

if __name__ == "__main__":
    test_db6()
