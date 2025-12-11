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
        - Temperature: 温度原始值 (Word)
    
    输出字段 (存储):
        - temperature: 当前温度 (°C)
    
    转换公式:
        temperature = raw_value * scale
        (scale 默认为 0.1，即 PLC 存储 250 表示 25.0°C)
    """
    
    MODULE_TYPE = "TemperatureSensor"
    
    OUTPUT_FIELDS = {
        "temperature": {"display_name": "当前温度", "unit": "°C"},
    }
    
    # 温度缩放系数 (PLC 存储整数时使用)
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
        """
        # 获取缩放系数
        scale = kwargs.get('scale', self.DEFAULT_SCALE)
        
        # 获取原始温度值
        raw_temp = self.get_field_value(raw_data, "Temperature", 0)
        
        # 应用缩放系数
        temperature = raw_temp * scale
        
        return {
            "temperature": round(temperature, 1),
        }
