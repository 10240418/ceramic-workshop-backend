# ============================================================
# 称重传感器转换器 (WeighSensor)
# ============================================================
# 基于柯力称重仪表 MODBUS RTU 协议
# 寄存器40003 bit8-11 包含分度值（小数点位置）
# ============================================================

from typing import Dict, Any, Optional
from .converter_base import BaseConverter


# 分度值映射表 (根据手册 bit8-11)
# 状态字的 bit8-11 表示重量分度值
DIVISION_MAP = {
    0b0000: 1.0,      # 0 -> 1
    0b0001: 2.0,      # 1 -> 2
    0b0010: 5.0,      # 2 -> 5
    0b0011: 10.0,     # 3 -> 10
    0b0100: 20.0,     # 4 -> 20
    0b0101: 50.0,     # 5 -> 50
    0b0110: 0.1,      # 6 -> 0.1
    0b0111: 0.2,      # 7 -> 0.2
    0b1000: 0.5,      # 8 -> 0.5
    0b1001: 0.01,     # 9 -> 0.01
    0b1010: 0.02,     # 10 -> 0.02
    0b1011: 0.05,     # 11 -> 0.05
    0b1100: 0.001,    # 12 -> 0.001
    0b1101: 0.002,    # 13 -> 0.002
    0b1110: 0.005,    # 14 -> 0.005
    0b1111: 1.0,      # 15 -> 无定义，默认1
}


class WeightConverter(BaseConverter):
    """
    称重传感器数据转换器 (基于柯力仪表 MODBUS RTU 协议)
    
    输入字段 (从PLC/仪表读取):
        - GrossWeight_W: 毛重 Word 精度 (对应寄存器40001)
        - NetWeight_W: 净重 Word 精度 (对应寄存器40002)
        - StatusWord: 状态字 (对应寄存器40003)
        - GrossWeight: 毛重 DWord 高精度 (对应寄存器40004-40005)
        - NetWeight: 净重 DWord 高精度 (对应寄存器40006-40007)
    
    StatusWord 各位含义 (寄存器40003):
        bit0-4: 输出状态 OUT1-OUT5
        bit5: 稳定标志 (1=稳定)
        bit6: 零点标志
        bit7: 超载标志
        bit8-11: 分度值 (小数点位置) - 关键!
        bit12-14: 输入状态 IN1-IN3
        bit15: 配料完成标志
    
    输出字段 (存储):
        - weight: 实时重量 (kg)
        - is_stable: 稳定标志
        - is_overload: 超载标志
    
    注意:
        feed_rate 不再由此模块计算, 改由 feeding_analysis_service v5.0 负责
    
    重量计算公式:
        实际重量 = 原始值 × 分度值
        分度值从 StatusWord 的 bit8-11 获取
    """
    
    MODULE_TYPE = "WeighSensor"
    
    OUTPUT_FIELDS = {
        "weight": {"display_name": "实时重量", "unit": "kg"},
        "is_stable": {"display_name": "稳定", "unit": ""},
        "is_overload": {"display_name": "超载", "unit": ""},
    }
    
    @staticmethod
    def parse_status_word(status_word: int) -> Dict[str, Any]:
        """
        解析状态字 (寄存器40003)
        
        Args:
            status_word: 状态字原始值 (16位)
        
        Returns:
            包含各状态位的字典
        """
        # bit8-11: 分度值编码
        division_code = (status_word >> 8) & 0x0F
        division_value = DIVISION_MAP.get(division_code, 1.0)
        
        return {
            "out1": bool(status_word & 0x01),        # bit0
            "out2": bool(status_word & 0x02),        # bit1
            "out3": bool(status_word & 0x04),        # bit2
            "out4": bool(status_word & 0x08),        # bit3
            "out5": bool(status_word & 0x10),        # bit4
            "is_stable": bool(status_word & 0x20),   # bit5
            "is_zero": bool(status_word & 0x40),     # bit6
            "is_overload": bool(status_word & 0x80), # bit7
            "division_code": division_code,          # bit8-11
            "division_value": division_value,        # 分度值
            "in1": bool(status_word & 0x1000),       # bit12
            "in2": bool(status_word & 0x2000),       # bit13
            "in3": bool(status_word & 0x4000),       # bit14
            "batch_complete": bool(status_word & 0x8000),  # bit15
        }
    
    def convert(self, raw_data: Dict[str, Any], **kwargs) -> Dict[str, Any]:
        """
        转换称重传感器数据
        
        Args:
            raw_data: Parser 解析后的原始数据
            **kwargs:
                - force_scale: 强制使用的缩放系数 (可选, 用于覆盖状态字)
        
        Returns:
            存储字段字典: weight, is_stable, is_overload
        
        说明:
            1. 从 StatusWord 解析分度值
            2. 使用分度值将原始重量转换为实际重量
            3. feed_rate 不再由此模块计算, 改由 feeding_analysis_service 负责
        """
        # 获取参数
        force_scale: Optional[float] = kwargs.get('force_scale')
        
        # 获取状态字并解析
        status_word = int(self.get_field_value(raw_data, "StatusWord", 0))
        status = self.parse_status_word(status_word)
        
        # 确定缩放系数
        if force_scale is not None:
            scale = force_scale
        else:
            scale = status["division_value"]
        
        # 获取当前重量
        # 优先使用高精度 DWord 值 (寄存器40004-40005)
        raw_weight = self.get_field_value(raw_data, "GrossWeight", 0.0)
        
        # 如果高精度值为 0，回退到 Word 精度值
        if raw_weight == 0:
            raw_weight = self.get_field_value(raw_data, "GrossWeight_W", 0.0)
        
        # 应用分度值得到实际重量
        current_weight = float(raw_weight) * scale
        
        return {
            "weight": round(current_weight, 3),
            "is_stable": status["is_stable"],
            "is_overload": status["is_overload"],
        }
