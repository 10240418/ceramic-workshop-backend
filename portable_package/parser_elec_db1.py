# -*- coding: utf-8 -*-
"""DB1 (Vw_Data) - 变频器/弧流弧压数据块解析 (独立脚本, 无外部依赖)"""

import struct
import sys

try:
    import snap7
except ImportError:
    print("snap7 not installed, run: pip install python-snap7")
    sys.exit(1)

# PLC 连接配置 (根据实际情况修改)
PLC_IP = "192.168.1.10"
PLC_RACK = 0
PLC_SLOT = 1

client = snap7.client.Client()

try:
    client.connect(PLC_IP, PLC_RACK, PLC_SLOT)
except Exception as e:
    print(f"PLC connect failed: {e}")
    sys.exit(1)

print("=" * 80)
print("DB1 (Vw_Data) - 变频器/弧流弧压数据块")
print(f"PLC: {PLC_IP}  Rack: {PLC_RACK}  Slot: {PLC_SLOT}")
print("=" * 80)

try:
    # DB1 总大小: 190 字节 (offset 0~189, 包含高压紧急停电数据)
    # TIME 类型占 4 字节，所以需要读取到 offset 189
    data = client.db_read(1, 0, 190)
    data = bytes(data)

    print()
    print("--- 电机输出数据解析 (offset 0-7) ---")
    print()

    # 电机输出 (4个 Int, 每个2字节)
    motor_output_1 = struct.unpack(">h", data[0:2])[0]
    motor_output_spare = struct.unpack(">h", data[2:4])[0]
    motor_output_2 = struct.unpack(">h", data[4:6])[0]
    motor_output_3 = struct.unpack(">h", data[6:8])[0]

    print(f"[电机输出1] Offset 0-1:   {motor_output_1}")
    print(f"[备用电机]   Offset 2-3:   {motor_output_spare}")
    print(f"[电机输出2] Offset 4-5:   {motor_output_2}")
    print(f"[电机输出3] Offset 6-7:   {motor_output_3}")
    print()

    print()
    print("=" * 80)
    print(" UVW 三相弧流弧压 (前端实际使用的数据) ")
    print("=" * 80)
    print()

    # ============================================================
    # UVW 三相弧流弧压 (offset 10-24)
    # ============================================================
    arc_current_U = struct.unpack(">h", data[10:12])[0]
    arc_voltage_U = struct.unpack(">h", data[12:14])[0]
    
    arc_current_V = struct.unpack(">h", data[16:18])[0]
    arc_voltage_V = struct.unpack(">h", data[18:20])[0]
    
    arc_current_W = struct.unpack(">h", data[22:24])[0]
    arc_voltage_W = struct.unpack(">h", data[24:26])[0]

    print(f"[U相] 弧流: {arc_current_U:5d} A  |  弧压: {arc_voltage_U:3d} V")
    print(f"[V相] 弧流: {arc_current_V:5d} A  |  弧压: {arc_voltage_V:3d} V")
    print(f"[W相] 弧流: {arc_current_W:5d} A  |  弧压: {arc_voltage_W:3d} V")
    print()

    print()
    print("--- 弧流设定值 + 自动灵敏度 (offset 32-43) ---")
    print()

    # 弧流设定值 (offset 32-42)
    arc_current_setpoint_U = struct.unpack(">h", data[32:34])[0]
    arc_sensitivity_U = struct.unpack(">h", data[34:36])[0]
    
    arc_current_setpoint_V = struct.unpack(">h", data[36:38])[0]
    arc_sensitivity_V = struct.unpack(">h", data[38:40])[0]
    
    arc_current_setpoint_W = struct.unpack(">h", data[40:42])[0]
    arc_sensitivity_W = struct.unpack(">h", data[42:44])[0]

    print(f"[U相设定] 弧流: {arc_current_setpoint_U:5d} A  |  灵敏度: {arc_sensitivity_U}")
    print(f"[V相设定] 弧流: {arc_current_setpoint_V:5d} A  |  灵敏度: {arc_sensitivity_V}")
    print(f"[W相设定] 弧流: {arc_current_setpoint_W:5d} A  |  灵敏度: {arc_sensitivity_W}")
    print()

    print()
    print("--- 死区设置 (offset 48, 64-67) ---")
    print()

    # 手动死区百分比 (offset 48)
    manual_deadzone_percent = struct.unpack(">h", data[48:50])[0]
    
    # 死区上下限 (offset 64-67)
    arc_current_deadzone_lower = struct.unpack(">h", data[64:66])[0]
    arc_current_deadzone_upper = struct.unpack(">h", data[66:68])[0]

    print(f"[手动死区百分比] Offset 48-49:  {manual_deadzone_percent} %")
    print(f"[死区下限]       Offset 64-65:  {arc_current_deadzone_lower} A")
    print(f"[死区上限]       Offset 66-67:  {arc_current_deadzone_upper} A")
    print()

    print()
    print("--- 弧流弧压内部数据 (offset 94-147, 归一化Real + 比例Int) ---")
    print()

    # A相弧流弧压 (offset 94-105)
    arc_current_A_normalized = struct.unpack(">f", data[94:98])[0]
    arc_current_A_scale = struct.unpack(">h", data[98:100])[0]
    arc_voltage_A_normalized = struct.unpack(">f", data[100:104])[0]
    arc_voltage_A_scale = struct.unpack(">h", data[104:106])[0]

    print(f"[A相] 弧流归一: {arc_current_A_normalized:.4f}  比例: {arc_current_A_scale:5d} A")
    print(f"      弧压归一: {arc_voltage_A_normalized:.4f}  比例: {arc_voltage_A_scale:3d} V")
    print()

    # B相弧流弧压 (offset 106-117)
    arc_current_B_normalized = struct.unpack(">f", data[106:110])[0]
    arc_current_B_scale = struct.unpack(">h", data[110:112])[0]
    arc_voltage_B_normalized = struct.unpack(">f", data[112:116])[0]
    arc_voltage_B_scale = struct.unpack(">h", data[116:118])[0]

    print(f"[B相] 弧流归一: {arc_current_B_normalized:.4f}  比例: {arc_current_B_scale:5d} A")
    print(f"      弧压归一: {arc_voltage_B_normalized:.4f}  比例: {arc_voltage_B_scale:3d} V")
    print()

    # C相弧流弧压 (offset 118-129)
    arc_current_C_normalized = struct.unpack(">f", data[118:122])[0]
    arc_current_C_scale = struct.unpack(">h", data[122:124])[0]
    arc_voltage_C_normalized = struct.unpack(">f", data[124:128])[0]
    arc_voltage_C_scale = struct.unpack(">h", data[128:130])[0]

    print(f"[C相] 弧流归一: {arc_current_C_normalized:.4f}  比例: {arc_current_C_scale:5d} A")
    print(f"      弧压归一: {arc_voltage_C_normalized:.4f}  比例: {arc_voltage_C_scale:3d} V")
    print()

    # 备用相弧流弧压 (offset 130-141)
    arc_current_spare_normalized = struct.unpack(">f", data[130:134])[0]
    arc_current_spare_scale = struct.unpack(">h", data[134:136])[0]
    arc_voltage_spare_normalized = struct.unpack(">f", data[136:140])[0]
    arc_voltage_spare_scale = struct.unpack(">h", data[140:142])[0]

    print(f"[备用] 弧流归一: {arc_current_spare_normalized:.4f}  比例: {arc_current_spare_scale:5d} A")
    print(f"      弧压归一: {arc_voltage_spare_normalized:.4f}  比例: {arc_voltage_spare_scale:3d} V")
    print()

    # 弧流给定 (offset 142-147)
    arc_current_setpoint_normalized = struct.unpack(">f", data[142:146])[0]
    arc_current_setpoint_scale = struct.unpack(">h", data[146:148])[0]

    print(f"[给定] 弧流归一: {arc_current_setpoint_normalized:.4f}  比例: {arc_current_setpoint_scale:5d} A")
    print()

    print()
    print("--- 变频电机电流 (offset 148-165) ---")
    print()

    # U相变频电机电流 (offset 148-153)
    vfd_motor_current_A_normalized = struct.unpack(">f", data[148:152])[0]
    vfd_motor_current_A_scale = struct.unpack(">h", data[152:154])[0]

    # V相变频电机电流 (offset 154-159)
    vfd_motor_current_B_normalized = struct.unpack(">f", data[154:158])[0]
    vfd_motor_current_B_scale = struct.unpack(">h", data[158:160])[0]

    # W相变频电机电流 (offset 160-165)
    vfd_motor_current_C_normalized = struct.unpack(">f", data[160:164])[0]
    vfd_motor_current_C_scale = struct.unpack(">h", data[164:166])[0]

    print(f"[U相] 归一: {vfd_motor_current_A_normalized:.4f}  比例: {vfd_motor_current_A_scale:5d} A")
    print(f"[V相] 归一: {vfd_motor_current_B_normalized:.4f}  比例: {vfd_motor_current_B_scale:5d} A")
    print(f"[W相] 归一: {vfd_motor_current_C_normalized:.4f}  比例: {vfd_motor_current_C_scale:5d} A")
    print()

    print()
    print("--- 电机输出归一化 (offset 166-181) ---")
    print()

    # 电机输出归一化 (4个 Real, 每个4字节)
    motor_output_1_normalized = struct.unpack(">f", data[166:170])[0]
    motor_output_spare_normalized = struct.unpack(">f", data[170:174])[0]
    motor_output_2_normalized = struct.unpack(">f", data[174:178])[0]
    motor_output_3_normalized = struct.unpack(">f", data[178:182])[0]

    print(f"[电机输出1] 归一: {motor_output_1_normalized:.4f}")
    print(f"[备用电机]   归一: {motor_output_spare_normalized:.4f}")
    print(f"[电机输出2] 归一: {motor_output_2_normalized:.4f}")
    print(f"[电机输出3] 归一: {motor_output_3_normalized:.4f}")
    print()

    print()
    print("=" * 80)
    print(" 高压紧急停电弧流设置 (前端设置页面使用, 4个数据) ")
    print("=" * 80)
    print()

    # 1. 高压紧急停电弧流上限值 (offset 182, INT, 2字节)
    emergency_stop_arc_limit = struct.unpack(">h", data[182:184])[0]
    
    # 2. 高压紧急停电标志 (offset 184, bit 0)
    # 3. 高压紧急停电功能使能 (offset 184, bit 1)
    emergency_byte = data[184]
    emergency_stop_flag = bool(emergency_byte & 0x01)  # bit 0
    emergency_stop_enabled = bool(emergency_byte & 0x02)  # bit 1
    
    # 4. 高压紧急停电消抖时间 (offset 186, TIME, 4字节)
    # PLC TIME 类型是 32 位有符号整数，存储为毫秒 (ms)
    # 范围: -2,147,483,648 ms 到 +2,147,483,647 ms
    emergency_stop_delay_ms = struct.unpack(">i", data[186:190])[0]  # 有符号 32 位整数
    emergency_stop_delay_s = emergency_stop_delay_ms / 1000.0  # 转换为秒

    print(f"[1. 高压紧急停电弧流上限] Offset 182-183:  {emergency_stop_arc_limit} A")
    print(f"[2. 高压紧急停电标志]     Offset 184 bit0: {emergency_stop_flag}")
    print(f"[3. 高压紧急停电功能使能] Offset 184 bit1: {emergency_stop_enabled}")
    print(f"[4. 高压紧急停电消抖时间] Offset 186-189:  {emergency_stop_delay_ms} ms ({emergency_stop_delay_s:.3f} s)")
    print()
    
    # 状态说明
    status_text = "已触发" if emergency_stop_flag else "未触发"
    enabled_text = "已启用" if emergency_stop_enabled else "已禁用"
    print(f"状态: {status_text}  |  功能: {enabled_text}  |  消抖时间: {emergency_stop_delay_s:.3f} s ({emergency_stop_delay_ms} ms)")
    print()

    print()
    print("--- 原始数据 (前128字节, 每行16字节) ---")
    for i in range(0, min(128, 190), 16):
        hex_str = data[i : min(i + 16, 190)].hex().upper()
        hex_fmt = " ".join([hex_str[j : j + 2] for j in range(0, len(hex_str), 2)])
        print(f"  {i:3d}: {hex_fmt}")

    print()
    print("--- 高压紧急停电数据 (offset 182-189, 共8字节) ---")
    hex_str = data[182:190].hex().upper()
    hex_fmt = " ".join([hex_str[j : j + 2] for j in range(0, len(hex_str), 2)])
    print(f"  182: {hex_fmt}")
    print(f"  解析:")
    print(f"    182-183 (INT):  弧流上限 = {emergency_stop_arc_limit} A")
    print(f"    184 (BYTE):     标志={emergency_stop_flag}, 使能={emergency_stop_enabled}")
    print(f"    185 (BYTE):     保留 = 0x{data[185]:02X}")
    print(f"    186-189 (TIME): 消抖时间 = {emergency_stop_delay_ms} ms = {emergency_stop_delay_s:.3f} s")
    print()

except Exception as e:
    print(f"Read DB1 failed: {e}")
    import traceback
    traceback.print_exc()

client.disconnect()
print()
print("=" * 80)
print("读取完成")
print("=" * 80)
input("按回车键退出...")

