# ============================================================
# 温度传感器转换器 (TemperatureSensor)
# ============================================================
# 存储字段: temperature (°C)
# ============================================================

from typing import Dict, Any
from .converter_base import BaseConverter


class TemperatureConverter(BaseConverter):
    """
    温度传感器数据转换器
    
    输入字段 (PLC原始):
        - Temperature: 温度原始值 (SINT16 有符号16位整数)
    
    输出字段 (存储):
        - temperature: 当前温度 (°C)
    
    转换公式:
        temperature = raw_value * 0.1
        PLC存储单位为0.1摄氏度，即 PLC 存储 250 表示 25.0°C
        支持负温度: PLC 存储 -100 表示 -10.0°C
    
    数据类型说明:
        PLC工作人员确认: 温度为 SINT16 类型，单位 0.1摄氏度
        SINT16 范围: -32768 ~ 32767
        实际温度范围: -3276.8°C ~ 3276.7°C
    """
    
    MODULE_TYPE = "TemperatureSensor"
    
    OUTPUT_FIELDS = {
        "temperature": {"display_name": "当前温度", "unit": "°C"},
    }
    
    # 温度缩放系数 (PLC 存储 SINT16，单位 0.1摄氏度)
    DEFAULT_SCALE = 0.1
    
    def convert(self, raw_data: Dict[str, Any], **kwargs) -> Dict[str, Any]:
        """
        转换温度传感器数据
        
        Args:
            raw_data: Parser 解析后的原始数据
            **kwargs:
                - scale: 缩放系数 (默认 0.1)
        
        Returns:
            存储字段字典
        
        说明:
            PLC中的温度数据以 SINT16 (有符号16位整数) 存储
            单位为 0.1摄氏度，需要乘以 0.1 得到实际温度值
            例如: PLC存储 1500 表示实际温度 150.0°C
                  PLC存储 -50 表示实际温度 -5.0°C
        """
        # 获取缩放系数
        scale = kwargs.get('scale', self.DEFAULT_SCALE)
        
        # 获取原始温度值 (SINT16，可能为负数)
        raw_temp = self.get_field_value(raw_data, "Temperature", 0)
        
        # 确保是整数类型 (SINT16)
        if isinstance(raw_temp, float):
            raw_temp = int(raw_temp)
        
        # 应用缩放系数 (0.1摄氏度 → 摄氏度)
        temperature = raw_temp * scale
        
        return {
            "temperature": round(temperature, 1),
        }
