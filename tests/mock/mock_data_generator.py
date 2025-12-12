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
        # 基础值 (用于模拟真实波动)
        self._base_values = {
            # 料仓基础值
            'hopper_weight': [1500, 1800, 2200, 1600, 0, 0, 2500, 2800, 3000],  # 9个料仓
            'hopper_temp': [75, 80, 72, 78, 65, 68, 82, 85, 79],  # 温度
            'hopper_power': [35, 42, 38, 40, 25, 28, 45, 50, 48],  # 功率
            
            # 辊道窑基础值
            'roller_temp': [820, 850, 880, 900, 870, 840],  # 6个温区温度
            'roller_power': [38, 42, 45, 48, 44, 40],  # 6个温区功率
            'roller_energy': [1250, 1380, 1520, 1680, 1450, 1320],  # 能耗
            
            # SCR基础值
            'scr_flow': [120, 135],  # 2个SCR流量
            'scr_power': [28, 32],  # 2个SCR功率
            
            # 风机基础值
            'fan_power': [55, 62],  # 2个风机功率
        }
        
        # 时间累计值 (用于生成连续变化的数据)
        self._tick = 0
        
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
    
    def _add_noise(self, base: float, noise_range: float = 0.05) -> float:
        """添加随机波动"""
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
        """
        base_flow = self._base_values['scr_flow'][device_index]
        rt_flow = self._add_noise(base_flow, 0.1)
        rt_flow = max(0, rt_flow + random.uniform(-5, 5))
        
        # 累计流量递增
        total_flow_base = 5000 + device_index * 1000
        total_flow = total_flow_base + self._tick * 0.5
        total_flow_int = int(total_flow)
        total_flow_milli = int((total_flow - total_flow_int) * 1000)
        
        data = struct.pack('>I', int(rt_flow * 100))  # RtFlow (放大100倍存储)
        data += struct.pack('>I', total_flow_int)     # TotalFlow
        data += struct.pack('>H', total_flow_milli)   # TotalFlowMilli
        
        return data
    
    def generate_temperature_sensor(self, temp_value: float) -> bytes:
        """生成温度传感器模块数据 (2字节)
        
        结构:
        - Temperature (Word, 2B) - 温度值 (放大10倍)
        """
        temp = self._add_noise(temp_value, 0.02)
        temp = max(0, temp + random.uniform(-2, 2))
        
        # 温度放大10倍存储 (如 82.5°C -> 825)
        temp_int = int(temp * 10)
        return struct.pack('>H', temp_int & 0xFFFF)
    
    def generate_electricity_meter(self, power_base: float, energy_base: float, 
                                   energy_key: str = None, energy_index: int = 0) -> bytes:
        """生成电表模块数据 (56字节)
        
        结构 (14个Real):
        - Uab_0~2 (3个Real, 12B) - 线电压
        - Ua_0~2 (3个Real, 12B) - 相电压
        - I_0~2 (3个Real, 12B) - 电流
        - Pt, Pa, Pb, Pc (4个Real, 16B) - 功率
        - ImpEp (Real, 4B) - 电能
        """
        # 电压 (工业三相380V)
        uab_base = 380.0
        ua_base = 220.0
        
        uab = [self._add_noise(uab_base, 0.02) for _ in range(3)]
        ua = [self._add_noise(ua_base, 0.02) for _ in range(3)]
        
        # 电流 (根据功率计算)
        power = self._add_sine_wave(power_base, amplitude=0.1, period=45)
        power = max(0.1, power + random.uniform(-2, 2))
        
        # I = P / (√3 * U * cosφ), cosφ ≈ 0.85
        i_base = power * 1000 / (1.732 * 380 * 0.85)
        current = [self._add_noise(i_base, 0.05) for _ in range(3)]
        
        # 功率分配
        pt = power
        pa = power * 0.35
        pb = power * 0.33
        pc = power * 0.32
        
        # 累计电能 (递增)
        if energy_key and energy_key in self._energy_accumulator:
            # 每4秒增加 power * (4/3600) kWh
            self._energy_accumulator[energy_key][energy_index] += power * (4 / 3600)
            imp_ep = energy_base + self._energy_accumulator[energy_key][energy_index]
        else:
            imp_ep = energy_base + self._tick * power * (4 / 3600)
        
        # 打包数据 (大端序 Real)
        data = b''
        for v in uab:
            data += struct.pack('>f', v)
        for v in ua:
            data += struct.pack('>f', v)
        for v in current:
            data += struct.pack('>f', v)
        data += struct.pack('>f', pt)
        data += struct.pack('>f', pa)
        data += struct.pack('>f', pb)
        data += struct.pack('>f', pc)
        data += struct.pack('>f', imp_ep)
        
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
        data += self.generate_electricity_meter(total_power, total_energy)
        
        # 5个分区电表 (68-347, zone1-zone5)
        for i in range(5):
            data += self.generate_electricity_meter(
                self._base_values['roller_power'][i],
                self._base_values['roller_energy'][i],
                'roller', i
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
            8: self.generate_db8_data(),
            9: self.generate_db9_data(),
            10: self.generate_db10_data(),
        }


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
