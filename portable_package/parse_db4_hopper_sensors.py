# -*- coding: utf-8 -*-
"""DB4 料仓传感器 - 原始值 -> 计算方法 -> 数据库格式 (独立诊断脚本)"""

import struct
import sys
from datetime import datetime

try:
    import snap7
except ImportError:
    print("snap7 not installed, run: pip install python-snap7")
    sys.exit(1)

# PLC 连接配置
PLC_IP = "192.168.50.235"
PLC_RACK = 0
PLC_SLOT = 1

DB_NUMBER = 4
DB_SIZE = 144

# 电流互感器变比 (料仓=20)
RATIO = 20

# InfluxDB 存储信息
MEASUREMENT = "sensor_data"
DEVICE_ID = "hopper_unit_4"
DEVICE_TYPE = "hopper_sensor_unit"


def parse_and_show(data: bytes):
    """解析 DB4 并展示: 原始值 -> 计算过程 -> 数据库字段"""

    now = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")

    # ================================================================
    # 1. PM10 粉尘浓度 (Offset 0-1, Word)
    # 转换器: converter_pm10.py - 直接使用, 无需缩放
    # DB字段: pm10, concentration (ug/m3)
    # ================================================================
    print()
    print("=" * 72)
    print("  1. PM10 粉尘浓度  |  Offset 0-1  |  Word (2 bytes)")
    print("=" * 72)
    pm10_raw = struct.unpack(">H", data[0:2])[0]
    pm10_db = round(float(pm10_raw), 1)
    print(f"  [RAW]  Hex: 0x{pm10_raw:04X}  Decimal: {pm10_raw}")
    print(f"  [CALC] pm10 = raw (直接使用, 无需缩放)")
    print(f"         {pm10_raw} -> {pm10_db}")
    print(f"  [DB]   pm10 = {pm10_db} ug/m3")
    print(f"         concentration = {pm10_db} ug/m3")

    # ================================================================
    # 2. 温度 (Offset 2-3, Int16, 单位 0.1C)
    # 转换器: converter_temp.py - raw * 0.1
    # DB字段: temperature (C)
    # ================================================================
    print()
    print("=" * 72)
    print("  2. 温度传感器  |  Offset 2-3  |  Int16 (2 bytes)")
    print("=" * 72)
    temp_raw = struct.unpack(">h", data[2:4])[0]
    temp_db = round(temp_raw * 0.1, 1)
    if temp_db < -10.0:
        temp_db = abs(temp_db)
        print(f"  [RAW]  Hex: 0x{temp_raw & 0xFFFF:04X}  Decimal: {temp_raw}")
        print(f"  [CALC] temperature = raw * 0.1 = {temp_raw} * 0.1 = {round(temp_raw * 0.1, 1)}")
        print(f"         (< -10C, 取绝对值修正) -> {temp_db}")
    else:
        print(f"  [RAW]  Hex: 0x{temp_raw & 0xFFFF:04X}  Decimal: {temp_raw}")
        print(f"  [CALC] temperature = raw * 0.1 = {temp_raw} * 0.1 = {temp_db}")
    print(f"  [DB]   temperature = {temp_db} C")

    # ================================================================
    # 3. 电表 (Offset 4-59, 14xReal, 56 bytes)
    # 转换器: converter_elec.py
    #   电压: raw * 0.1
    #   电流: raw * 0.001 * ratio(20)
    #   功率: raw * 0.001 * ratio(20)
    #   能耗: raw * 2
    # ================================================================
    print()
    print("=" * 72)
    print("  3. 三相电表  |  Offset 4-59  |  14 x Real (56 bytes)")
    print("     变比 ratio = 20")
    print("=" * 72)

    base = 4

    # 读取全部14个 Real 原始浮点值
    def read_real(offset):
        return struct.unpack(">f", data[base + offset: base + offset + 4])[0]

    # 线电压 (不存数据库, 仅显示)
    Uab_0_raw = read_real(0)
    Uab_1_raw = read_real(4)
    Uab_2_raw = read_real(8)

    # 相电压
    Ua_0_raw = read_real(12)
    Ua_1_raw = read_real(16)
    Ua_2_raw = read_real(20)

    # 电流
    I_0_raw = read_real(24)
    I_1_raw = read_real(28)
    I_2_raw = read_real(32)

    # 功率
    Pt_raw = read_real(36)
    Pa_raw = read_real(40)
    Pb_raw = read_real(44)
    Pc_raw = read_real(48)

    # 能耗
    ImpEp_raw = read_real(52)

    # -- 3.1 线电压 (不写入DB, 仅诊断) --
    print()
    print("  [3.1] 线电压 (不写入数据库, 仅诊断)")
    for name, raw in [("Uab_0", Uab_0_raw), ("Uab_1", Uab_1_raw), ("Uab_2", Uab_2_raw)]:
        val = round(raw * 0.1, 1)
        print(f"    {name}: [RAW] {raw:.1f}  [CALC] {raw:.1f} * 0.1 = {val} V")

    # -- 3.2 相电压 (写入DB: Ua_0, Ua_1, Ua_2) --
    print()
    print("  [3.2] 相电压: raw * 0.1  -> DB字段: Ua_0, Ua_1, Ua_2")
    Ua_0_db = round(Ua_0_raw * 0.1, 1)
    Ua_1_db = round(Ua_1_raw * 0.1, 1)
    Ua_2_db = round(Ua_2_raw * 0.1, 1)
    for name, raw, db_val in [("Ua_0", Ua_0_raw, Ua_0_db), ("Ua_1", Ua_1_raw, Ua_1_db), ("Ua_2", Ua_2_raw, Ua_2_db)]:
        print(f"    {name}: [RAW] {raw:.1f}  [CALC] {raw:.1f} * 0.1 = {db_val}  [DB] {name} = {db_val} V")

    # -- 3.3 电流 (写入DB: I_0, I_1, I_2) --
    print()
    print(f"  [3.3] 电流: raw * 0.001 * {RATIO}  -> DB字段: I_0, I_1, I_2")
    I_0_db = round(I_0_raw * 0.001 * RATIO, 2)
    I_1_db = round(I_1_raw * 0.001 * RATIO, 2)
    I_2_db = round(I_2_raw * 0.001 * RATIO, 2)
    for name, raw, db_val in [("I_0", I_0_raw, I_0_db), ("I_1", I_1_raw, I_1_db), ("I_2", I_2_raw, I_2_db)]:
        print(f"    {name}: [RAW] {raw:.1f}  [CALC] {raw:.1f} * 0.001 * {RATIO} = {db_val}  [DB] {name} = {db_val} A")

    # -- 3.4 功率 (写入DB: Pt; Pa/Pb/Pc 不写入) --
    print()
    print(f"  [3.4] 功率: raw * 0.001 * {RATIO}  -> DB字段: Pt")
    Pt_db = round(Pt_raw * 0.001 * RATIO, 2)
    print(f"    Pt:  [RAW] {Pt_raw:.1f}  [CALC] {Pt_raw:.1f} * 0.001 * {RATIO} = {Pt_db}  [DB] Pt = {Pt_db} kW")
    # 各相功率仅诊断
    for name, raw in [("Pa", Pa_raw), ("Pb", Pb_raw), ("Pc", Pc_raw)]:
        val = round(raw * 0.001 * RATIO, 2)
        print(f"    {name}:  [RAW] {raw:.1f}  [CALC] {raw:.1f} * 0.001 * {RATIO} = {val} kW  (不写入DB)")

    # -- 3.5 能耗 (写入DB: ImpEp) --
    print()
    print("  [3.5] 能耗: raw * 2  -> DB字段: ImpEp")
    ImpEp_db = round(ImpEp_raw * 2, 2)
    print(f"    ImpEp: [RAW] {ImpEp_raw:.2f}  [CALC] {ImpEp_raw:.2f} * 2 = {ImpEp_db}  [DB] ImpEp = {ImpEp_db} kWh")

    # ================================================================
    # 4. 振动传感器 (Offset 60-143, 84 bytes)
    # 转换器: converter_vibration.py - PLC Word 原始值即为物理量
    # DB字段: vx,vy,vz (mm/s), dx,dy,dz (um), hzx,hzy,hzz (Hz)
    # ================================================================
    print()
    print("=" * 72)
    print("  4. 振动传感器  |  Offset 60-143  |  Word (84 bytes)")
    print("     PLC Word 值即为物理量, 直接使用")
    print("=" * 72)

    vib_base = 60

    # -- 4.1 速度幅值 (相对偏移 12-17, 绝对偏移 72-77) --
    VX_raw = struct.unpack(">H", data[vib_base + 12: vib_base + 14])[0]
    VY_raw = struct.unpack(">H", data[vib_base + 14: vib_base + 16])[0]
    VZ_raw = struct.unpack(">H", data[vib_base + 16: vib_base + 18])[0]
    print()
    print("  [4.1] 速度幅值 (DB4 Offset 72-77)  -> DB字段: vx, vy, vz")
    for name, db_name, raw in [("VX", "vx", VX_raw), ("VY", "vy", VY_raw), ("VZ", "vz", VZ_raw)]:
        print(f"    {name}: [RAW] 0x{raw:04X} = {raw}  [CALC] 直接使用  [DB] {db_name} = {raw} mm/s")

    # -- 4.2 位移幅值 (相对偏移 26-31, 绝对偏移 86-91) --
    DX_raw = struct.unpack(">H", data[vib_base + 26: vib_base + 28])[0]
    DY_raw = struct.unpack(">H", data[vib_base + 28: vib_base + 30])[0]
    DZ_raw = struct.unpack(">H", data[vib_base + 30: vib_base + 32])[0]
    print()
    print("  [4.2] 位移幅值 (DB4 Offset 86-91)  -> DB字段: dx, dy, dz")
    for name, db_name, raw in [("DX", "dx", DX_raw), ("DY", "dy", DY_raw), ("DZ", "dz", DZ_raw)]:
        print(f"    {name}: [RAW] 0x{raw:04X} = {raw}  [CALC] 直接使用  [DB] {db_name} = {raw} um")

    # -- 4.3 频率 (相对偏移 32-37, 绝对偏移 92-97) --
    HZX_raw = struct.unpack(">H", data[vib_base + 32: vib_base + 34])[0]
    HZY_raw = struct.unpack(">H", data[vib_base + 34: vib_base + 36])[0]
    HZZ_raw = struct.unpack(">H", data[vib_base + 36: vib_base + 38])[0]
    print()
    print("  [4.3] 频率 (DB4 Offset 92-97)  -> DB字段: hzx, hzy, hzz")
    for name, db_name, raw in [("HZX", "hzx", HZX_raw), ("HZY", "hzy", HZY_raw), ("HZZ", "hzz", HZZ_raw)]:
        print(f"    {name}: [RAW] 0x{raw:04X} = {raw}  [CALC] 直接使用  [DB] {db_name} = {raw} Hz")

    # ================================================================
    # 5. 数据库写入格式汇总 (InfluxDB Point)
    # ================================================================
    print()
    print("=" * 72)
    print("  5. 数据库写入格式汇总 (InfluxDB)")
    print("=" * 72)
    print()
    print(f"  measurement = {MEASUREMENT}")
    print(f"  timestamp   = {now}")
    print()
    print("  [Tags]")
    print(f"    device_id   = {DEVICE_ID}")
    print(f"    device_type = {DEVICE_TYPE}")
    print()

    # PM10 模块
    print("  [Point 1] module_type=pm10, module_tag=pm10")
    print(f"    fields: {{ pm10: {pm10_db}, concentration: {pm10_db} }}")
    print()

    # 温度模块
    print("  [Point 2] module_type=temperature, module_tag=temperature")
    print(f"    fields: {{ temperature: {temp_db} }}")
    print()

    # 电表模块
    print("  [Point 3] module_type=electricity, module_tag=electricity")
    print(f"    fields: {{ Ua_0: {Ua_0_db}, Ua_1: {Ua_1_db}, Ua_2: {Ua_2_db},")
    print(f"              I_0: {I_0_db}, I_1: {I_1_db}, I_2: {I_2_db},")
    print(f"              Pt: {Pt_db}, ImpEp: {ImpEp_db} }}")
    print()

    # 振动模块
    print("  [Point 4] module_type=vibration, module_tag=vibration")
    print(f"    fields: {{ vx: {VX_raw}, vy: {VY_raw}, vz: {VZ_raw},")
    print(f"              dx: {DX_raw}, dy: {DY_raw}, dz: {DZ_raw},")
    print(f"              hzx: {HZX_raw}, hzy: {HZY_raw}, hzz: {HZZ_raw} }}")

    # ================================================================
    # 6. 原始数据 hex dump (全部144字节)
    # ================================================================
    print()
    print("=" * 72)
    print("  6. 原始数据 Hex Dump (144 bytes)")
    print("=" * 72)
    print()
    for i in range(0, DB_SIZE, 16):
        chunk = data[i: min(i + 16, DB_SIZE)]
        hex_str = " ".join([f"{b:02X}" for b in chunk])
        ascii_str = "".join([chr(b) if 32 <= b < 127 else "." for b in chunk])
        print(f"  {i:3d}: {hex_str:<48s}  {ascii_str}")


# ================================================================
# 主入口
# ================================================================
client = snap7.client.Client()

try:
    client.connect(PLC_IP, PLC_RACK, PLC_SLOT)
except Exception as e:
    print(f"PLC connect failed: {e}")
    sys.exit(1)

print()
print("=" * 72)
print("  DB4 料仓传感器 - 原始值 -> 计算方法 -> 数据库格式")
print(f"  PLC: {PLC_IP}  Rack: {PLC_RACK}  Slot: {PLC_SLOT}")
print(f"  DB: {DB_NUMBER}  Size: {DB_SIZE} bytes")
print(f"  Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
print("=" * 72)

try:
    data = client.db_read(DB_NUMBER, 0, DB_SIZE)
    data = bytes(data)
    parse_and_show(data)

except Exception as e:
    print(f"Read DB4 failed: {e}")
    import traceback
    traceback.print_exc()

client.disconnect()
print()
print("=" * 80)
print("读取完成")
print("=" * 80)
input("按回车键退出...")
