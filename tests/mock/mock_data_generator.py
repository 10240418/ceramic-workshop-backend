# ============================================================
# 文件说明: mock_data_generator.py - 模拟PLC原始数据生成器
# ============================================================
# 功能:
# 1. 生成符合PLC DB块结构的16进制原始数据
# 2. 模拟各种传感器的数据变化
# 3. 支持DB8(料仓)、DB9(辊道窑)、DB10(SCR/风机)
# ============================================================

import struct
import random
import math
from datetime import datetime
from typing import Dict, Tuple


class MockDataGenerator:
    """模拟PLC原始数据生成器
    
    生成符合PLC DB块结构的原始字节数据
    """
    
    def __init__(self):
        # 基础值 (用于模拟真实工业场景)
        self._base_values = {
            # 料仓基础值 - 模拟真实陶瓷原料料仓
            # 短料仓: 容量2000kg, 无料仓: 不储料, 长料仓: 容量3500kg
            'hopper_weight': [1650, 1420, 1890, 1280, 0, 0, 2850, 3120, 2680],  # kg
            'hopper_temp': [68, 72, 75, 70, 55, 58, 82, 78, 85],  # °C 干燥温度
            'hopper_power': [18.5, 22.0, 19.8, 21.5, 8.5, 9.2, 28.5, 32.0, 26.8],  # kW
            
            # 辊道窑基础值 - 陶瓷烧成温度曲线 (预热→升温→保温→冷却)
            'roller_temp': [450, 680, 920, 1080, 1050, 780],  # °C 典型陶瓷烧成曲线
            'roller_power': [45, 62, 85, 95, 88, 55],  # kW 各温区功率
            'roller_energy': [2850, 3680, 5120, 5980, 5450, 3250],  # kWh 累计能耗
            
            # SCR脱硝设备 - 氨水喷射系统
            'scr_flow': [85.5, 92.3],  # L/min 氨水流量
            'scr_power': [15.5, 18.2],  # kW 泵功率
            
            # 引风机 - 大功率工业风机
            'fan_power': [75.0, 82.5],  # kW 风机功率
        }
        
        # 时间累计值 (用于生成连续变化的数据)
        self._tick = 0
        
        # 料仓消耗模式 (模拟下料过程)
        self._hopper_consuming = [False] * 9
        self._hopper_consume_rate = [0.0] * 9  # kg/s
        
        # 能耗累计值
        self._energy_accumulator = {
            'hopper': [0.0] * 9,
            'roller': [0.0] * 6,
            'scr': [0.0] * 2,
            'fan': [0.0] * 2,
        }
    
    def tick(self):
        """时间前进一步 (每次轮询调用)"""
        self._tick += 1
        
        # 模拟料仓下料过程 (随机触发)
        for i in range(9):
            if i in [4, 5]:  # 无料仓跳过
                continue
            # 10% 概率切换下料状态
            if random.random() < 0.1:
                self._hopper_consuming[i] = not self._hopper_consuming[i]
                if self._hopper_consuming[i]:
                    # 开始下料: 0.5-2.5 kg/s
                    self._hopper_consume_rate[i] = random.uniform(0.5, 2.5)
                else:
                    self._hopper_consume_rate[i] = 0.0
    
    def _add_noise(self, base: float, noise_range: float = 0.03) -> float:
        """添加随机波动 (默认3%波动)"""
        noise = random.uniform(-noise_range, noise_range)
        return base * (1 + noise)
    
    def _add_sine_wave(self, base: float, amplitude: float = 0.1, period: int = 60) -> float:
        """添加正弦波动 (模拟周期性变化)"""
        wave = math.sin(2 * math.pi * self._tick / period) * amplitude
        return base * (1 + wave)
    
    # ============================================================
    # 模块数据生成 - 符合 plc_modules.yaml 定义
    # ============================================================
    
    def generate_weigh_sensor(self, device_index: int) -> bytes:
        """生成称重传感器模块数据 (14字节)
        
        结构:
        - GrossWeight_W (Word, 2B)
        - NetWeight_W (Word, 2B)
        - StatusWord (Word, 2B)
        - GrossWeight (DWord, 4B)
        - NetWeight (DWord, 4B)
        """
        base_weight = self._base_values['hopper_weight'][device_index]
        weight = self._add_sine_wave(base_weight, amplitude=0.08, period=30)
        weight = max(0, weight + random.uniform(-50, 50))  # 添加随机波动
        
        gross_weight = int(weight)
        tare_weight = 100  # 皮重固定
        net_weight = max(0, gross_weight - tare_weight)
        status = 0x0001  # 正常状态
        
        # 打包为大端字节序 (PLC使用大端)
        data = struct.pack('>H', gross_weight & 0xFFFF)  # GrossWeight_W
        data += struct.pack('>H', net_weight & 0xFFFF)   # NetWeight_W
        data += struct.pack('>H', status)                 # StatusWord
        data += struct.pack('>I', gross_weight)          # GrossWeight (高精度)
        data += struct.pack('>I', net_weight)            # NetWeight (高精度)
        
        return data
    
    def generate_flow_meter(self, device_index: int) -> bytes:
        """生成流量计模块数据 (10字节)
        
        结构:
        - RtFlow (DWord, 4B) - 实时流量 L/min
        - TotalFlow (DWord, 4B) - 累计流量 m³
        - TotalFlowMilli (Word, 2B) - 累计流量小数 mL
        
        注意: PLC存储的是原始值，转换公式：Real = Raw * 0.01
        所以: Raw = Real / 0.01 = Real * 100
        """
        base_flow = self._base_values['scr_flow'][device_index]
        rt_flow = self._add_noise(base_flow, 0.1)
        rt_flow = max(0, rt_flow + random.uniform(-5, 5))
        
        # 🔧 [FIX] 流量反向计算: 真实值 / 0.01 = 真实值 * 100
        # 例如: 85.5 L/min -> 8550
        rt_flow_raw = int(rt_flow / 0.01)
        
        # 累计流量递增
        total_flow_base = 5000 + device_index * 1000
        total_flow = total_flow_base + self._tick * 0.5
        total_flow_int = int(total_flow)
        total_flow_milli = int((total_flow - total_flow_int) * 1000)
        
        data = struct.pack('>I', rt_flow_raw)        # RtFlow (原始值)
        data += struct.pack('>I', total_flow_int)    # TotalFlow
        data += struct.pack('>H', total_flow_milli)  # TotalFlowMilli
        
        return data
    
    def generate_temperature_sensor(self, temp_value: float) -> bytes:
        """生成温度传感器模块数据 (2字节)
        
        结构:
        - Temperature (Word, 2B) - 温度值
        
        注意: PLC存储的是原始值，转换公式：Real = Raw * 0.1
        所以: Raw = Real / 0.1 = Real * 10
        """
        temp = self._add_noise(temp_value, 0.02)
        temp = max(0, temp + random.uniform(-2, 2))
        
        # 🔧 [FIX] 温度反向计算: 真实值 / 0.1
        # 例如: 82.5°C -> 825
        temp_raw = int(temp / 0.1)
        return struct.pack('>H', temp_raw & 0xFFFF)
    
    def generate_electricity_meter(self, power_base: float, energy_base: float, 
                                   energy_key: str = None, energy_index: int = 0,
                                   ratio: int = 20) -> bytes:
        """生成电表模块数据 (56字节)
        
        结构 (14个Real):
        - Uab_0~2 (3个Real, 12B) - 线电压
        - Ua_0~2 (3个Real, 12B) - 相电压
        - I_0~2 (3个Real, 12B) - 电流
        - Pt, Pa, Pb, Pc (4个Real, 16B) - 功率
        - ImpEp (Real, 4B) - 电能
        
        Args:
            ratio: 电流变比 (电流互感器变比)
                   - 辊道窑: 60
                   - 其他: 20
        
        注意: PLC存储的是原始值，需要通过转换器转换：
        - 电压: Real = Raw * 0.1
        - 电流: Real = Raw * 0.1 * Ratio
        - 功率: Real = Raw * 0.1
        - 电能: Real = Raw * 0.1
        """
        # 🔧 [FIX] 生成真实的物理值，然后反向计算 PLC 原始值
        
        # 1. 电压 (工业三相380V) - PLC原始值 = 真实值 / 0.1
        uab_real = [self._add_noise(380.0, 0.02) for _ in range(3)]
        ua_real = [self._add_noise(220.0, 0.02) for _ in range(3)]
        
        uab_raw = [v / 0.1 for v in uab_real]  # 380V -> 3800
        ua_raw = [v / 0.1 for v in ua_real]    # 220V -> 2200
        
        # 2. 功率 (kW) - PLC原始值 = 真实值 / 0.1
        power_real = self._add_sine_wave(power_base, amplitude=0.1, period=45)
        power_real = max(0.1, power_real + random.uniform(-2, 2))
        
        pt_raw = power_real / 0.1              # 例如 18.5kW -> 185
        pa_raw = (power_real * 0.35) / 0.1
        pb_raw = (power_real * 0.33) / 0.1
        pc_raw = (power_real * 0.32) / 0.1
        
        # 3. 电流 (A) - PLC原始值 = 真实值 / (0.1 * Ratio)
        # I = P / (√3 * U * cosφ), cosφ ≈ 0.85
        i_real = power_real * 1000 / (1.732 * 380 * 0.85)  # 真实电流 (A)
        
        current_raw = [self._add_noise(i_real, 0.05) / (0.1 * ratio) for _ in range(3)]
        # 例如: 辊道窑 100A -> 100 / (0.1 * 60) = 16.67
        #      料仓 50A -> 50 / (0.1 * 20) = 25
        
        # 4. 累计电能 (kWh) - PLC原始值 = 真实值 / 0.1
        if energy_key and energy_key in self._energy_accumulator:
            # 每6秒增加 power * (6/3600) kWh
            self._energy_accumulator[energy_key][energy_index] += power_real * (6 / 3600)
            energy_real = energy_base + self._energy_accumulator[energy_key][energy_index]
        else:
            energy_real = energy_base + self._tick * power_real * (6 / 3600)
        
        imp_ep_raw = energy_real / 0.1  # 例如 1250.3kWh -> 12503
        
        # 打包数据 (大端序 Real)
        data = b''
        for v in uab_raw:
            data += struct.pack('>f', v)
        for v in ua_raw:
            data += struct.pack('>f', v)
        for v in current_raw:
            data += struct.pack('>f', v)
        data += struct.pack('>f', pt_raw)
        data += struct.pack('>f', pa_raw)
        data += struct.pack('>f', pb_raw)
        data += struct.pack('>f', pc_raw)
        data += struct.pack('>f', imp_ep_raw)
        
        return data
    
    # ============================================================
    # DB块数据生成
    # ============================================================
    
    def generate_db8_data(self) -> bytes:
        """生成DB8数据块 (料仓, 626字节)
        
        结构:
        - 4个短料仓: 每个72字节 (称重14 + 温度2 + 电表56)
        - 2个无料仓: 每个58字节 (温度2 + 电表56)
        - 3个长料仓: 每个74字节 (称重14 + 温度1_2 + 温度2_2 + 电表56)
        """
        data = b''
        
        # 4个短料仓 (0-287, 每个72字节)
        for i in range(4):
            data += self.generate_weigh_sensor(i)  # 14字节
            data += self.generate_temperature_sensor(self._base_values['hopper_temp'][i])  # 2字节
            data += self.generate_electricity_meter(
                self._base_values['hopper_power'][i],
                100 + i * 50,
                'hopper', i
            )  # 56字节
        
        # 2个无料仓 (288-403, 每个58字节)
        for i in range(2):
            idx = 4 + i
            data += self.generate_temperature_sensor(self._base_values['hopper_temp'][idx])  # 2字节
            data += self.generate_electricity_meter(
                self._base_values['hopper_power'][idx],
                80 + i * 30,
                'hopper', idx
            )  # 56字节
        
        # 3个长料仓 (404-625, 每个74字节)
        for i in range(3):
            idx = 6 + i
            data += self.generate_weigh_sensor(idx)  # 14字节
            data += self.generate_temperature_sensor(self._base_values['hopper_temp'][idx])  # 2字节 (温度1)
            data += self.generate_temperature_sensor(self._base_values['hopper_temp'][idx] + 5)  # 2字节 (温度2)
            data += self.generate_electricity_meter(
                self._base_values['hopper_power'][idx],
                150 + i * 60,
                'hopper', idx
            )  # 56字节
        
        return data
    
    def generate_db9_data(self) -> bytes:
        """生成DB9数据块 (辊道窑, 348字节)
        
        结构:
        - 6个温度传感器: 每个2字节 (共12字节)
        - 6个电表: 每个56字节 (主电表 + 5个分区电表, 共336字节)
        """
        data = b''
        
        # 6个温度传感器 (0-11)
        for i in range(6):
            temp = self._add_sine_wave(self._base_values['roller_temp'][i], amplitude=0.03, period=120)
            data += self.generate_temperature_sensor(temp)
        
        # 主电表 (12-67)
        total_power = sum(self._base_values['roller_power'])
        total_energy = sum(self._base_values['roller_energy'])
        data += self.generate_electricity_meter(total_power, total_energy, ratio=60)
        
        # 5个分区电表 (68-347, zone1-zone5)
        for i in range(5):
            data += self.generate_electricity_meter(
                self._base_values['roller_power'][i],
                self._base_values['roller_energy'][i],
                'roller', i,
                ratio=60
            )
        
        return data
    
    def generate_db10_data(self) -> bytes:
        """生成DB10数据块 (SCR+风机, 244字节)
        
        结构:
        - 2个SCR: 每个66字节 (流量计10 + 电表56)
        - 2个风机: 每个56字节 (电表56)
        """
        data = b''
        
        # 2个SCR (0-131, 每个66字节)
        for i in range(2):
            data += self.generate_flow_meter(i)  # 10字节
            data += self.generate_electricity_meter(
                self._base_values['scr_power'][i],
                200 + i * 100,
                'scr', i
            )  # 56字节
        
        # 2个风机 (132-243, 每个56字节)
        for i in range(2):
            data += self.generate_electricity_meter(
                self._base_values['fan_power'][i],
                500 + i * 200,
                'fan', i
            )
        
        return data
    
    def generate_all_db_data(self) -> Dict[int, bytes]:
        """生成所有DB块数据"""
        self.tick()  # 时间前进
        
        return {
            3: self.generate_db3_status_data(),   # DB3: 回转窑状态位 (148字节)
            7: self.generate_db7_status_data(),   # DB7: 辊道窑状态位 (72字节)
            8: self.generate_db8_data(),
            9: self.generate_db9_data(),
            10: self.generate_db10_data(),
            11: self.generate_db11_status_data(), # DB11: SCR/风机状态位 (40字节)
        }
    
    def _generate_module_status(self, error_rate: float = 0.05, 
                                 error_codes: list = None) -> bytes:
        """生成单个模块状态 (4字节)
        
        结构: Error(Bool, offset 0) + Status(Word, offset 2)
        - byte0: Error (bit 0)
        - byte1: 保留
        - byte2-3: Status (Word, 大端序)
        
        Args:
            error_rate: 错误率 (0.0-1.0)
            error_codes: 可能的错误码列表
        """
        if error_codes is None:
            error_codes = [0x8200, 0x8201, 0x8000, 0x0001, 0x0002]
        
        data = bytearray(4)
        
        if random.random() < (1 - error_rate):
            # 正常状态: Error=0, Status=0
            data[0] = 0x00  # Error=0
            data[1] = 0x00
            data[2] = 0x00  # Status high byte
            data[3] = 0x00  # Status low byte
        else:
            # 错误状态: Error=1, Status=错误码
            data[0] = 0x01  # Error=1
            data[1] = 0x00
            error_code = random.choice(error_codes)
            data[2] = (error_code >> 8) & 0xFF  # Status high byte
            data[3] = error_code & 0xFF         # Status low byte
        
        return bytes(data)
    
    def generate_db3_status_data(self) -> bytes:
        """生成DB3状态位数据块 - 回转窑(料仓)状态 (148字节)
        
        结构说明:
        - Kiln_Have_1~4 (短料仓有称重): 4个×16字节 = 64字节 (offset 0-63)
          每个: WeighSensor(4) + Temperature(4) + ElectricityMeter(4) + ElectricityMeter_I(4)
        - Kiln_NoHave_1~2 (短料仓无称重): 2个×12字节 = 24字节 (offset 64-87)
          每个: Temperature(4) + ElectricityMeter(4) + ElectricityMeter_I(4)
        - LongKiln_Have_1~3 (长料仓有称重): 3个×20字节 = 60字节 (offset 88-147)
          每个: WeighSensor(4) + Temperature_1(4) + Temperature_2(4) + ElectricityMeter(4) + ElectricityMeter_I(4)
        """
        data = bytearray(148)
        offset = 0
        
        # Kiln_Have_1~4 (4个×16字节 = 64字节)
        for i in range(4):
            # WeighSensor + Temperature + ElectricityMeter + ElectricityMeter_I
            for j in range(4):
                data[offset:offset+4] = self._generate_module_status()
                offset += 4
        
        # Kiln_NoHave_1~2 (2个×12字节 = 24字节)
        for i in range(2):
            # Temperature + ElectricityMeter + ElectricityMeter_I
            for j in range(3):
                data[offset:offset+4] = self._generate_module_status()
                offset += 4
        
        # LongKiln_Have_1~3 (3个×20字节 = 60字节)
        for i in range(3):
            # WeighSensor + Temperature_1 + Temperature_2 + ElectricityMeter + ElectricityMeter_I
            for j in range(5):
                data[offset:offset+4] = self._generate_module_status()
                offset += 4
        
        return bytes(data)
    
    def generate_db7_status_data(self) -> bytes:
        """生成DB7状态位数据块 - 辊道窑状态 (72字节)
        
        结构说明:
        - Temperature_1~6: 6个×4字节 = 24字节 (offset 0-23)
        - ElectricityMeter_1~6: 6个×4字节 = 24字节 (offset 24-47)
        - ElectricityMeter_I_1~6: 6个×4字节 = 24字节 (offset 48-71)
        """
        data = bytearray(72)
        offset = 0
        
        # Temperature_1~6 (6个×4字节 = 24字节)
        for i in range(6):
            data[offset:offset+4] = self._generate_module_status()
            offset += 4
        
        # ElectricityMeter_1~6 (6个×4字节 = 24字节)
        for i in range(6):
            data[offset:offset+4] = self._generate_module_status()
            offset += 4
        
        # ElectricityMeter_I_1~6 (6个×4字节 = 24字节)
        for i in range(6):
            data[offset:offset+4] = self._generate_module_status()
            offset += 4
        
        return bytes(data)
    
    def generate_db11_status_data(self) -> bytes:
        """生成DB11状态位数据块 - SCR/风机状态 (40字节)
        
        结构说明:
        - SCR_1~2: 2个×12字节 = 24字节 (offset 0-23)
          每个: GasMeter(4) + ElectricityMeter(4) + ElectricityMeter_I(4)
        - Fan_1~2: 2个×8字节 = 16字节 (offset 24-39)
          每个: ElectricityMeter(4) + ElectricityMeter_I(4)
        """
        data = bytearray(40)
        offset = 0
        
        # SCR_1~2 (2个×12字节 = 24字节)
        for i in range(2):
            # GasMeter + ElectricityMeter + ElectricityMeter_I
            for j in range(3):
                data[offset:offset+4] = self._generate_module_status()
                offset += 4
        
        # Fan_1~2 (2个×8字节 = 16字节)
        for i in range(2):
            # ElectricityMeter + ElectricityMeter_I
            for j in range(2):
                data[offset:offset+4] = self._generate_module_status()
                offset += 4
        
        return bytes(data)
    
    def generate_db1_status_data(self) -> bytes:
        """生成DB1状态位数据块 (270字节)
        
        根据 config_status.yaml 结构:
        - MB_COMM_LOAD: 4字节 (offset 0)
        - DB_MASTER_ELEC_0~36: 37*4=148字节 (offset 4-152)
        - DB_MASTER_THERMAL_0~17: 18*4=72字节 (offset 152-224)
        - 空隙: 4字节 (offset 224-228)
        - DB_MASTER_FLOW_0~1: 2*4=8字节 (offset 228-236)
        - DB_MASTER_WEIGH_0~6: 7*4=28字节 (offset 236-264)
        - DB_MASTER_WEIGHTED: 4字节 (offset 264-268)
        - 填充: 2字节 (offset 268-270)
        
        状态结构 (每设备4字节):
        - byte0: DONE(bit0), BUSY(bit1), ERROR(bit2)
        - byte1: 保留
        - byte2-3: STATUS (Word, 状态码)
        """
        data = bytearray(270)
        
        # MB_COMM_LOAD (offset 0) - CommLoadStatus: DONE(bit0), ERROR(bit1)
        # 模拟正常状态: DONE=1, ERROR=0, STATUS=0
        data[0] = 0x01  # DONE=1
        data[1] = 0x00
        data[2] = 0x00  # STATUS high byte
        data[3] = 0x00  # STATUS low byte
        
        # DB_MASTER_ELEC_0~36 (37个电表状态, offset 4-152)
        # PLC常见错误码说明:
        # 0x8200 (33280): 485通信断开/超时
        # 0x8201 (33281): 485校验错误
        # 0x8000 (32768): 通用通信故障
        # 0x0001-0x000F: 传感器故障码
        plc_error_codes = [
            0x8200,  # 485通信断开 (最常见)
            0x8201,  # 485校验错误
            0x8000,  # 通用通信故障
            0x0001,  # 传感器故障1
            0x0002,  # 传感器故障2
            0x0003,  # 传感器故障3
            0x000A,  # 传感器故障10
        ]
        
        for i in range(37):
            offset = 4 + i * 4
            # 模拟: 大部分正常, 偶尔有错误
            if random.random() < 0.95:  # 95%正常
                data[offset] = 0x01     # DONE=1, BUSY=0, ERROR=0
                data[offset + 1] = 0x00
                data[offset + 2] = 0x00  # STATUS=0
                data[offset + 3] = 0x00
            else:
                # 模拟错误状态 - 使用真实PLC错误码
                data[offset] = 0x04     # DONE=0, BUSY=0, ERROR=1
                data[offset + 1] = 0x00
                error_code = random.choice(plc_error_codes)
                data[offset + 2] = (error_code >> 8) & 0xFF  # 高字节
                data[offset + 3] = error_code & 0xFF         # 低字节
        
        # DB_MASTER_THERMAL_0~17 (18个温度状态, offset 152-224)
        temp_error_codes = [0x8200, 0x0001, 0x0002, 0x0003]  # 温度传感器典型错误
        for i in range(18):
            offset = 152 + i * 4
            if random.random() < 0.95:
                data[offset] = 0x01
                data[offset + 1] = 0x00
                data[offset + 2] = 0x00
                data[offset + 3] = 0x00
            else:
                data[offset] = 0x04
                data[offset + 1] = 0x00
                error_code = random.choice(temp_error_codes)
                data[offset + 2] = (error_code >> 8) & 0xFF
                data[offset + 3] = error_code & 0xFF
        
        # 空隙 (offset 224-228)
        data[224:228] = b'\x00\x00\x00\x00'
        
        # DB_MASTER_FLOW_0~1 (2个流量状态, offset 228-236)
        for i in range(2):
            offset = 228 + i * 4
            data[offset] = 0x01  # 正常
            data[offset + 1] = 0x00
            data[offset + 2] = 0x00
            data[offset + 3] = 0x00
        
        # DB_MASTER_WEIGH_0~6 (7个称重状态, offset 236-264)
        weight_error_codes = [0x8200, 0x0002]  # 称重传感器典型错误
        for i in range(7):
            offset = 236 + i * 4
            if random.random() < 0.95:
                data[offset] = 0x01
                data[offset + 1] = 0x00
                data[offset + 2] = 0x00
                data[offset + 3] = 0x00
            else:
                data[offset] = 0x04
                data[offset + 1] = 0x00
                error_code = random.choice(weight_error_codes)
                data[offset + 2] = (error_code >> 8) & 0xFF
                data[offset + 3] = error_code & 0xFF
        
        # DB_MASTER_WEIGHTED (offset 264-268)
        data[264] = 0x01
        data[265] = 0x00
        data[266] = 0x00
        data[267] = 0x00
        
        return bytes(data)


# 测试代码
if __name__ == "__main__":
    gen = MockDataGenerator()
    
    for i in range(3):
        print(f"\n{'='*60}")
        print(f"第 {i+1} 次生成")
        print(f"{'='*60}")
        
        data = gen.generate_all_db_data()
        
        for db_num, db_data in data.items():
            print(f"DB{db_num}: {len(db_data)} bytes")
            print(f"  前32字节: {db_data[:32].hex()}")
