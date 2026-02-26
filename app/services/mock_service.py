# ============================================================
# 文件说明: mock_service.py - Mock 原始数据生成服务
# ============================================================
# 功能:
# 1. 生成符合PLC DB块结构的原始字节数据
# 2. 模拟各种传感器数据变化（数值参考真实现场截图）
# 3. 支持 DB3/DB7/DB8/DB9/DB10/DB11
# 4. 支持 alarm_test 模式：周期性触发温度/功率报警用于测试
# ============================================================

import struct
import random
import math
from typing import Dict, Optional, List

from config import get_settings


class MockService:
    """模拟PLC原始数据生成器

    生成符合PLC DB块结构的原始字节数据。
    数值基准来自真实现场截图：
      - 短料仓回转窑 (窑7,6,5,4): 运行温度 1380-1480°C, 功率 16-24kW
      - 无料仓回转窑 (窑2,1):     运行温度(原始) 1479-1577°C, 功率 22-24kW
      - 长料仓回转窑 (窑8,3,9):   运行温度 640-700°C, 功率 6-20kW
      - 辊道窑 zone1-6:            450-1080°C, 功率 45-95kW
      - SCR氨水泵:                 流量 25 m3/h, 功率 0.5-2kW
      - 风机:                      功率 2-4kW
    """

    def __init__(self):
        self._settings = get_settings()

        self._rnd = random.Random(self._settings.mock_random_seed)

        # --------------------------------------------------------
        # 基础值 (对应经 Converter 转换后的实际物理量)
        # 索引: 0=short1(窑7), 1=short2(窑6), 2=short3(窑5),  3=short4(窑4)
        #       4=no1(窑2),    5=no2(窑1),
        #       6=long1(窑8),  7=long2(窑3),  8=long3(窑9)
        # [注意] 所有值代表期望的最终输出值，generate_electricity_meter 内部会逆算原始值
        # --------------------------------------------------------
        self._base_values = {
            # 料仓重量 (kg), 0表示料仓停止/空, 范围 0-300kg
            'hopper_weight': [250, 220, 0, 0, 0, 0, 180, 260, 0],
            # 运行时温度 (°C), 全部回转窑约 1400°C
            'hopper_temp': [1409, 1422, 1477, 1388, 1479, 1577, 1390, 1405, 1370],
            # 运行时电功率 (kW), 期望输出 16-20kW
            'hopper_power': [18.0, 17.5, 19.0, 18.5, 20.0, 19.5, 17.0, 16.5, 18.0],
            # 累计电量基础值 (kWh), 期望输出 6000-10000kWh
            'hopper_energy': [7200, 6800, 8100, 7600, 9000, 8500, 6500, 7000, 6200],
            # 辊道窑6温区温度 (°C), 热梯度分布
            'roller_temp': [450, 680, 920, 1080, 1050, 780],
            # 辊道窑各温区功率 (kW), 期望输出 16-25kW/zone
            'roller_power': [18.0, 20.0, 22.0, 25.0, 24.0, 19.0],
            # 辊道窑各温区累计电量基础值 (kWh), 期望输出 6000-10000kWh
            'roller_energy': [7500, 8200, 9000, 9800, 9200, 7800],
            # SCR氨水泵实时流量 (L/min), 约 429 L/min
            'scr_flow': [429.0, 380.0],
            # SCR氨水泵功率 (kW)
            'scr_power': [0.5, 1.2],
            # 风机功率 (kW)
            'fan_power': [2.4, 3.2],
        }

        self._tick = 0
        self._poll_interval_s = float(self._settings.plc_poll_interval)

        # --------------------------------------------------------
        # 回转窑运行状态
        # 初始状态: 参考截图 - 短/无料仓大部分运行，长料仓部分停止
        # index:   0    1     2     3     4    5     6     7     8
        # kiln:   窑7  窑6   窑5   窑4   窑2  窑1   窑8   窑3   窑9
        # --------------------------------------------------------
        self._kiln_running = [False, True, True, False, True, True, True, True, False]
        # 窑状态切换倒计时 (tick数，避免频繁切换)
        self._kiln_state_countdown = [self._rnd.randint(30, 120) for _ in range(9)]
        # 窑停机持续时间限制 (tick数，停止后至少等这么多tick才能重启)
        self._kiln_stop_min_ticks = [self._rnd.randint(8, 20) for _ in range(9)]

        # 料仓消耗状态
        self._hopper_consuming = [False] * 9
        self._hopper_consume_rate = [0.0] * 9
        self._hopper_refill_countdown = [0] * 9

        self._energy_accumulator = {
            'hopper': [0.0] * 9,
            'roller': [0.0] * 6,
            'scr': [0.0] * 2,
            'fan': [0.0] * 2,
        }

        self._status_faults: Dict[str, Dict[str, int]] = {}
        self._status_error_rate = max(0.0, min(1.0, self._settings.mock_error_rate))

        # 上次生成的快照（advance=False 时直接返回，不产生副作用）
        self._last_snapshot: Optional[Dict[int, bytes]] = None

        self._profile = (self._settings.mock_data_profile or "realistic").strip().lower()
        self._noise_scale = 1.0
        self._flow_noise_scale = 1.0
        self._consume_rate_scale = 1.0

        # --------------------------------------------------------
        # 报警测试模式: alarm_test
        # 周期性给随机设备制造温度/功率峰值，触发报警记录
        # --------------------------------------------------------
        self._alarm_test_mode = (self._profile == "alarm_test")
        # 每个回转窑的报警峰值倒计时 (0=正常, >0=处于峰值状态)
        self._alarm_spike_countdown: List[int] = [0] * 9
        # 每个回转窑的温度波动倍率 (1.0=正常, >1.0=峰值)
        self._alarm_spike_factor: List[float] = [1.0] * 9
        # 下次触发报警峰值的倒计时
        self._next_alarm_trigger_countdown = self._rnd.randint(10, 25)

        if self._profile == "stable":
            self._noise_scale = 0.45
            self._flow_noise_scale = 0.60
            self._consume_rate_scale = 0.75
            self._status_error_rate = min(self._status_error_rate, 0.01)
        elif self._profile == "aggressive":
            self._noise_scale = 1.45
            self._flow_noise_scale = 1.35
            self._consume_rate_scale = 1.35
            self._status_error_rate = min(1.0, max(self._status_error_rate, 0.08))
        elif self._alarm_test_mode:
            # alarm_test: 中等噪声，频繁峰值
            self._noise_scale = 1.0
            self._flow_noise_scale = 1.0
            self._consume_rate_scale = 1.0
            self._status_error_rate = max(self._status_error_rate, 0.05)

    def tick(self, poll_interval_s: Optional[float] = None):
        if poll_interval_s is not None:
            self._poll_interval_s = max(0.01, float(poll_interval_s))

        self._tick += 1

        # --------------------------------------------------------
        # 1. 更新回转窑运行状态 (随机启停，模拟真实切换)
        # --------------------------------------------------------
        for i in range(9):
            self._kiln_state_countdown[i] -= 1
            if self._kiln_state_countdown[i] <= 0:
                if self._kiln_running[i]:
                    # 运行中 -> 随机停机 (概率较低，大部分时间保持运行)
                    if self._rnd.random() < 0.15:
                        self._kiln_running[i] = False
                        self._kiln_state_countdown[i] = self._rnd.randint(5, 20)
                        self._hopper_consuming[i] = False
                        self._hopper_consume_rate[i] = 0.0
                    else:
                        self._kiln_state_countdown[i] = self._rnd.randint(40, 120)
                else:
                    # 停机中 -> 随机重启
                    if self._rnd.random() < 0.40:
                        self._kiln_running[i] = True
                        self._kiln_state_countdown[i] = self._rnd.randint(60, 180)
                    else:
                        self._kiln_state_countdown[i] = self._rnd.randint(6, 15)

        # --------------------------------------------------------
        # 2. 更新料仓重量 (仅对有料仓的运行中的回转窑)
        # --------------------------------------------------------
        for i in range(9):
            if i in [4, 5]:
                # no_hopper 设备无料仓，跳过重量更新
                continue

            if not self._kiln_running[i]:
                # 停机中不消耗物料
                self._hopper_consuming[i] = False
                self._hopper_consume_rate[i] = 0.0
                continue

            current_weight = self._base_values['hopper_weight'][i]
            # 短料仓(i<4): 容量约300kg; 长料仓(i>=6): 容量约300kg
            capacity = 300
            min_weight = 30

            if self._hopper_refill_countdown[i] > 0:
                self._hopper_refill_countdown[i] -= 1
                if self._hopper_refill_countdown[i] == 0:
                    refill = self._rnd.uniform(0.72, 0.90) * capacity
                    self._base_values['hopper_weight'][i] = refill
                    self._hopper_consuming[i] = False
                    self._hopper_consume_rate[i] = 0.0
                continue

            if current_weight <= min_weight:
                self._hopper_consuming[i] = False
                self._hopper_consume_rate[i] = 0.0
                self._hopper_refill_countdown[i] = self._rnd.randint(2, 6)
                continue

            if self._hopper_consuming[i]:
                if self._rnd.random() < 0.08:
                    self._hopper_consuming[i] = False
                    self._hopper_consume_rate[i] = 0.0
            else:
                if self._rnd.random() < 0.22:
                    self._hopper_consuming[i] = True
                    # 短料仓: ~8 kg/h = 0.00222 kg/s; 长料仓: ~32 kg/h = 0.00889 kg/s
                    if i < 4:
                        self._hopper_consume_rate[i] = self._rnd.uniform(0.0015, 0.0035) * self._consume_rate_scale
                    else:
                        self._hopper_consume_rate[i] = self._rnd.uniform(0.006, 0.012) * self._consume_rate_scale

            if self._hopper_consuming[i]:
                consumed = self._hopper_consume_rate[i] * self._poll_interval_s
                self._base_values['hopper_weight'][i] = max(0.0, current_weight - consumed)

        # --------------------------------------------------------
        # 3. 报警测试模式: 周期性触发温度峰值
        # --------------------------------------------------------
        if self._alarm_test_mode or self._profile == "aggressive":
            # 倒计时结束时，随机选一个运行中的窑触发峰值
            self._next_alarm_trigger_countdown -= 1
            if self._next_alarm_trigger_countdown <= 0:
                running_indices = [i for i in range(9) if self._kiln_running[i]]
                if running_indices:
                    target_idx = self._rnd.choice(running_indices)
                    # 峰值倍率: 1.05-1.12 (超过常规运行温度约5-12%)
                    # 对于1400°C的窑: 1400*1.10=1540°C，若阈值设在1450/1500°C则会报警
                    spike_factor = self._rnd.uniform(1.05, 1.12)
                    spike_duration = self._rnd.randint(3, 8)
                    self._alarm_spike_countdown[target_idx] = spike_duration
                    self._alarm_spike_factor[target_idx] = spike_factor
                interval = self._rnd.randint(8, 20) if self._alarm_test_mode else self._rnd.randint(20, 50)
                self._next_alarm_trigger_countdown = interval

            # 更新峰值倒计时
            for i in range(9):
                if self._alarm_spike_countdown[i] > 0:
                    self._alarm_spike_countdown[i] -= 1
                    if self._alarm_spike_countdown[i] <= 0:
                        self._alarm_spike_factor[i] = 1.0

    def _add_noise(self, base: float, noise_range: float = 0.03) -> float:
        noise = self._rnd.uniform(-noise_range * self._noise_scale, noise_range * self._noise_scale)
        return base * (1 + noise)

    def _add_sine_wave(self, base: float, amplitude: float = 0.1, period: int = 60) -> float:
        wave = math.sin(2 * math.pi * self._tick / period) * amplitude
        return base * (1 + wave)

    def generate_weigh_sensor(self, device_index: int) -> bytes:
        if not self._kiln_running[device_index]:
            # 停机时重量传感器仍然有数值（物料静置），加轻微抖动
            weight = self._base_values['hopper_weight'][device_index]
            weight = max(0.0, weight + self._rnd.uniform(-8, 8))
        else:
            base_weight = self._base_values['hopper_weight'][device_index]
            wave_amp = 0.018 if self._hopper_consuming[device_index] else 0.006
            weight = self._add_sine_wave(base_weight, amplitude=wave_amp, period=24)
            weight = max(0, weight + self._rnd.uniform(-12, 12))

        gross_weight = int(weight)
        tare_weight = 100
        net_weight = max(0, gross_weight - tare_weight)
        status = 0x0001

        data = struct.pack('>H', gross_weight & 0xFFFF)
        data += struct.pack('>H', net_weight & 0xFFFF)
        data += struct.pack('>H', status)
        data += struct.pack('>I', gross_weight)
        data += struct.pack('>I', net_weight)
        return data

    def generate_flow_meter(self, device_index: int) -> bytes:
        # base_flow 单位: L/min (converter 公式: raw × 0.001 = L/min)
        base_flow = self._base_values['scr_flow'][device_index]
        rt_flow = self._add_noise(base_flow, 0.08 * self._flow_noise_scale)
        rt_flow = max(0, rt_flow + self._rnd.uniform(-15.0, 15.0) * self._flow_noise_scale)
        # 逆算原始值: raw = flow_lpm / SCALE_FLOW_RATE = flow_lpm / 0.001
        rt_flow_raw = int(rt_flow / 0.001)

        # 累计流量 (m³): 基础值 + 随tick累加 (1 L/min = 1/1000 m³/min)
        # 429 L/min × 60min/h × t_hours = total m³
        total_flow_base = 4154.0 + device_index * 800  # m³ 起始累计
        total_flow = total_flow_base + self._tick * rt_flow * (self._poll_interval_s / 60000.0)
        total_flow_int = int(total_flow)
        total_flow_milli = int((total_flow - total_flow_int) * 1000)

        data = struct.pack('>I', rt_flow_raw)
        data += struct.pack('>I', total_flow_int)
        data += struct.pack('>H', total_flow_milli)
        return data

    def generate_temperature_sensor(self, temp_value: float, kiln_running: bool = True) -> bytes:
        if not kiln_running:
            # 停机时传感器读数接近室温/随机小负值（参考截图 -0.7°C, -1.5°C）
            temp = self._rnd.uniform(-2.0, 4.5)
        else:
            temp = self._add_noise(temp_value, 0.015)
            # 应用报警峰值（由 generate_db8_data 传入时已乘以 spike_factor，此处无需重复）
            temp = max(0, temp + self._rnd.uniform(-3, 3))
        temp_raw = int(temp / 0.1)
        # 处理负值: PLC 原始温度传感器允许负值 (有符号字)
        if temp_raw < 0:
            temp_raw = temp_raw & 0xFFFF
        return struct.pack('>H', temp_raw & 0xFFFF)

    def generate_electricity_meter(self, power_kw: float, energy_kwh: float,
                                   energy_key: str = None, energy_index: int = 0,
                                   ratio: int = 20) -> bytes:
        """
        生成电表原始字节数据 (逆算 converter_elec.py 的换算公式)。

        converter_elec.py 换算公式:
            Pt    = raw_Pt    × SCALE_POWER   × ratio  (SCALE_POWER=0.0001)
            I     = raw_I     × SCALE_CURRENT × ratio  (SCALE_CURRENT=0.001)
            ImpEp = raw_ImpEp × ratio
            Ua    = raw_Ua    × SCALE_VOLTAGE            (SCALE_VOLTAGE=0.1)

        逆算:
            raw_Pt    = power_kw  / (0.0001 × ratio)
            raw_I     = i_physical / (0.001 × ratio)
            raw_ImpEp = energy_kwh / ratio
            raw_Ua    = voltage_v  / 0.1

        电流由三相功率公式推算 (PF=0.60, 与工业电机实测相符):
            I = P_kW × 1000 / (sqrt3 × 380 × 0.60)
        """
        # 电压 (不受变比影响): raw = V / 0.1
        uab_raw = [self._add_noise(380.0, 0.02) / 0.1 for _ in range(3)]
        ua_raw = [self._add_noise(220.0, 0.02) / 0.1 for _ in range(3)]

        # 功率加噪
        power_noisy = self._add_sine_wave(power_kw, amplitude=0.08, period=45)
        power_noisy = max(0.05, power_noisy + self._rnd.uniform(-0.5, 0.5))

        # 逆算功率原始值: raw = Pt / (0.0001 × ratio)
        pt_raw = power_noisy / (0.0001 * ratio)
        pa_raw = (power_noisy * 0.35) / (0.0001 * ratio)
        pb_raw = (power_noisy * 0.33) / (0.0001 * ratio)
        pc_raw = (power_noisy * 0.32) / (0.0001 * ratio)

        # 逆算电流原始值: 物理电流 → raw = I / (0.001 × ratio)
        # PF=0.60: 18kW/380V/sqrt3/0.60 ≈ 45.5A, 符合工业电机实测 40-50A
        i_physical = power_noisy * 1000.0 / (1.732 * 380.0 * 0.60)
        current_raw = [self._add_noise(i_physical, 0.03) / (0.001 * ratio) for _ in range(3)]

        # 能耗累计
        if energy_key and energy_key in self._energy_accumulator:
            self._energy_accumulator[energy_key][energy_index] += power_noisy * (self._poll_interval_s / 3600.0)
            energy_total = energy_kwh + self._energy_accumulator[energy_key][energy_index]
        else:
            energy_total = energy_kwh + self._tick * power_noisy * (self._poll_interval_s / 3600.0)

        # 逆算能耗原始值: raw = ImpEp / ratio
        imp_ep_raw = energy_total / ratio

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

    def _make_stopped_electricity_meter(self, energy_kwh: float, energy_key: str = None,
                                        energy_index: int = 0, ratio: int = 20) -> bytes:
        """生成停机状态下的电表数据：功率接近0，能量不增加。编码逻辑与 generate_electricity_meter 一致。"""
        uab_raw = [self._add_noise(380.0, 0.01) / 0.1 for _ in range(3)]
        ua_raw = [self._add_noise(220.0, 0.01) / 0.1 for _ in range(3)]
        # 停机时有微小待机功率 (约 0.05-0.3kW)
        standby_power = self._rnd.uniform(0.05, 0.3)
        # 逆算功率原始值
        pt_raw = standby_power / (0.0001 * ratio)
        pa_raw = pb_raw = pc_raw = pt_raw / 3.0
        current_raw = [0.0] * 3

        # 停机状态下能量不累加
        if energy_key and energy_key in self._energy_accumulator:
            energy_total = energy_kwh + self._energy_accumulator[energy_key][energy_index]
        else:
            energy_total = energy_kwh

        # 逆算能耗原始值: raw = ImpEp / ratio
        imp_ep_raw = energy_total / ratio

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

    def generate_db8_data(self) -> bytes:
        data = b''

        # --- 短料仓 x4 (窑7,6,5,4 = indices 0-3) ---
        for i in range(4):
            running = self._kiln_running[i]
            base_temp = self._base_values['hopper_temp'][i]
            base_power = self._base_values['hopper_power'][i]
            energy_base = self._base_values['hopper_energy'][i]

            # 应用报警峰值因子 (alarm_test/aggressive 模式)
            spike = self._alarm_spike_factor[i]
            eff_temp = base_temp * spike
            eff_power = base_power * (0.88 + self._rnd.uniform(0.0, 0.30)) if running else 0.2

            data += self.generate_weigh_sensor(i)
            data += self.generate_temperature_sensor(eff_temp, kiln_running=running)
            if running:
                data += self.generate_electricity_meter(eff_power, energy_base, 'hopper', i)
            else:
                data += self._make_stopped_electricity_meter(energy_base, 'hopper', i)

        # --- 无料仓 x2 (窑2,1 = indices 4-5), 无重量传感器 ---
        for i in range(2):
            idx = 4 + i
            running = self._kiln_running[idx]
            base_temp = self._base_values['hopper_temp'][idx]
            base_power = self._base_values['hopper_power'][idx]
            energy_base = self._base_values['hopper_energy'][idx]

            spike = self._alarm_spike_factor[idx]
            eff_temp = base_temp * spike
            eff_power = base_power * (0.88 + self._rnd.uniform(0.0, 0.25)) if running else 0.2

            data += self.generate_temperature_sensor(eff_temp, kiln_running=running)
            if running:
                data += self.generate_electricity_meter(eff_power, energy_base, 'hopper', idx)
            else:
                data += self._make_stopped_electricity_meter(energy_base, 'hopper', idx)

        # --- 长料仓 x3 (窑8,3,9 = indices 6-8) ---
        for i in range(3):
            idx = 6 + i
            running = self._kiln_running[idx]
            base_temp = self._base_values['hopper_temp'][idx]
            base_power = self._base_values['hopper_power'][idx]
            energy_base = self._base_values['hopper_energy'][idx]

            spike = self._alarm_spike_factor[idx]
            eff_temp = base_temp * spike
            eff_power = base_power * (0.88 + self._rnd.uniform(0.0, 0.30)) if running else 0.2

            data += self.generate_weigh_sensor(idx)
            data += self.generate_temperature_sensor(eff_temp, kiln_running=running)
            # 长料仓有两个温度传感器 (上下部)
            eff_temp2 = (base_temp + self._rnd.uniform(8, 25)) * spike  # 第二个温度探头
            data += self.generate_temperature_sensor(eff_temp2, kiln_running=running)
            if running:
                data += self.generate_electricity_meter(eff_power, energy_base, 'hopper', idx)
            else:
                data += self._make_stopped_electricity_meter(energy_base, 'hopper', idx)

        return data

    def generate_db9_data(self) -> bytes:
        data = b''
        for i in range(6):
            # 辊道窑温度: 正弦波缓慢变化，幅度±2%，周期120 ticks
            temp = self._add_sine_wave(self._base_values['roller_temp'][i], amplitude=0.02, period=120)
            temp = max(0.0, temp + self._rnd.uniform(-5, 5))
            data += self.generate_temperature_sensor(temp, kiln_running=True)

        # 辊道窑总电表 (ratio=60 对应辊道窑变比)
        total_power = sum(self._base_values['roller_power'])
        total_energy = sum(self._base_values['roller_energy'])
        data += self.generate_electricity_meter(total_power, total_energy, ratio=60)

        # 各温区独立电表
        for i in range(5):
            data += self.generate_electricity_meter(
                self._base_values['roller_power'][i],
                self._base_values['roller_energy'][i],
                'roller', i,
                ratio=60,
            )

        return data

    def generate_db10_data(self) -> bytes:
        data = b''
        # SCR氨水泵 x2
        for i in range(2):
            data += self.generate_flow_meter(i)
            data += self.generate_electricity_meter(
                self._base_values['scr_power'][i],
                200 + i * 120,  # 氨水泵累计电量基础 (kWh), SCR功率小所以能耗也小
                'scr', i,
            )

        # 风机 x2
        for i in range(2):
            data += self.generate_electricity_meter(
                self._base_values['fan_power'][i],
                380 + i * 150,  # 风机累计电量基础 (kWh)
                'fan', i,
            )

        return data

    def generate_all_db_data(
        self,
        advance: bool = True,
        poll_interval_s: Optional[float] = None,
    ) -> Dict[int, bytes]:
        """生成所有 DB 的模拟原始数据

        Args:
            advance: True=推进一帧并生成新数据；False=返回上次生成的快照（无副作用）
            poll_interval_s: 推进时使用的轮询间隔（秒）
        """
        if not advance:
            # 返回快照：不调用 tick，不修改任何内部状态
            if self._last_snapshot is not None:
                return self._last_snapshot
            # 首次调用快照时先生成一帧初始数据
            advance = True

        self.tick(poll_interval_s=poll_interval_s)
        self._last_snapshot = {
            3: self.generate_db3_status_data(),
            7: self.generate_db7_status_data(),
            8: self.generate_db8_data(),
            9: self.generate_db9_data(),
            10: self.generate_db10_data(),
            11: self.generate_db11_status_data(),
        }
        return self._last_snapshot

    def _generate_module_status(self, key: str, error_rate: Optional[float] = None,
                                error_codes: Optional[List[int]] = None) -> bytes:
        if error_codes is None:
            error_codes = [0x8200, 0x8201, 0x8000, 0x0001, 0x0002]
        if error_rate is None:
            error_rate = self._status_error_rate

        data = bytearray(4)
        fault = self._status_faults.get(key)
        if fault and fault.get('remain', 0) > 0:
            fault['remain'] -= 1
            error_code = fault['code']
            data[0] = 0x01
            data[1] = 0x00
            data[2] = (error_code >> 8) & 0xFF
            data[3] = error_code & 0xFF
            if fault['remain'] <= 0:
                self._status_faults.pop(key, None)
            return bytes(data)

        if self._rnd.random() < error_rate:
            error_code = self._rnd.choice(error_codes)
            duration = self._rnd.randint(2, 12)
            self._status_faults[key] = {'remain': duration, 'code': error_code}
            data[0] = 0x01
            data[1] = 0x00
            data[2] = (error_code >> 8) & 0xFF
            data[3] = error_code & 0xFF
        else:
            data[0] = 0x00
            data[1] = 0x00
            data[2] = 0x00
            data[3] = 0x00

        return bytes(data)

    def generate_db3_status_data(self) -> bytes:
        data = bytearray(148)
        offset = 0
        for i in range(4):
            for j in range(4):
                key = f"db3.kiln_have{i+1}.m{j+1}"
                data[offset:offset + 4] = self._generate_module_status(key)
                offset += 4

        for i in range(2):
            for j in range(3):
                key = f"db3.kiln_nohave{i+1}.m{j+1}"
                data[offset:offset + 4] = self._generate_module_status(key)
                offset += 4

        for i in range(3):
            for j in range(5):
                key = f"db3.long_kiln{i+1}.m{j+1}"
                data[offset:offset + 4] = self._generate_module_status(key)
                offset += 4

        return bytes(data)

    def generate_db7_status_data(self) -> bytes:
        data = bytearray(72)
        offset = 0
        for i in range(6):
            key = f"db7.temperature{i+1}"
            data[offset:offset + 4] = self._generate_module_status(key)
            offset += 4

        for i in range(6):
            key = f"db7.electricity{i+1}"
            data[offset:offset + 4] = self._generate_module_status(key)
            offset += 4

        for i in range(6):
            key = f"db7.electricity_i{i+1}"
            data[offset:offset + 4] = self._generate_module_status(key)
            offset += 4

        return bytes(data)

    def generate_db11_status_data(self) -> bytes:
        data = bytearray(40)
        offset = 0
        for i in range(2):
            for j in range(3):
                key = f"db11.scr{i+1}.m{j+1}"
                data[offset:offset + 4] = self._generate_module_status(key)
                offset += 4

        for i in range(2):
            for j in range(2):
                key = f"db11.fan{i+1}.m{j+1}"
                data[offset:offset + 4] = self._generate_module_status(key)
                offset += 4

        return bytes(data)
