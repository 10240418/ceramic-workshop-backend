# ============================================================
# 电表转换器 (ElectricityMeter)
# ============================================================
# 存储字段: Pt, ImpEp, Ua_0~2, I_0~2
# ============================================================

from typing import Dict, Any
from .converter_base import BaseConverter


class ElectricityConverter(BaseConverter):
    """
    三相电表数据转换器
    
    输入字段 (PLC原始):
        - Uab_0, Uab_1, Uab_2: 线电压 (不存储)
        - Ua_0, Ua_1, Ua_2: 相电压
        - I_0, I_1, I_2: 相电流
        - Pt: 总有功功率
        - Pa, Pb, Pc: 各相功率 (不存储)
        - ImpEp: 正向有功电能
    
    输出字段 (存储):
        - Pt: 总有功功率 (kW)
        - ImpEp: 正向有功电能 (kWh)
        - Ua_0, Ua_1, Ua_2: 三相电压 (V)
        - I_0, I_1, I_2: 三相电流 (A)
    """
    
    MODULE_TYPE = "ElectricityMeter"
    
    OUTPUT_FIELDS = {
        "Pt": {"display_name": "总有功功率", "unit": "kW"},
        "ImpEp": {"display_name": "正向有功电能", "unit": "kWh"},
        "Ua_0": {"display_name": "A相电压", "unit": "V"},
        "Ua_1": {"display_name": "B相电压", "unit": "V"},
        "Ua_2": {"display_name": "C相电压", "unit": "V"},
        "I_0": {"display_name": "A相电流", "unit": "A"},
        "I_1": {"display_name": "B相电流", "unit": "A"},
        "I_2": {"display_name": "C相电流", "unit": "A"},
    }
    
    def convert(self, raw_data: Dict[str, Any], **kwargs) -> Dict[str, Any]:
        """
        转换电表数据
        
        Args:
            raw_data: Parser 解析后的原始数据
        
        Returns:
            存储字段字典
        """
        return {
            # 功率和电能
            "Pt": self.get_field_value(raw_data, "Pt", 0.0),
            "ImpEp": self.get_field_value(raw_data, "ImpEp", 0.0),
            
            # 三相电压
            "Ua_0": self.get_field_value(raw_data, "Ua_0", 0.0),
            "Ua_1": self.get_field_value(raw_data, "Ua_1", 0.0),
            "Ua_2": self.get_field_value(raw_data, "Ua_2", 0.0),
            
            # 三相电流
            "I_0": self.get_field_value(raw_data, "I_0", 0.0),
            "I_1": self.get_field_value(raw_data, "I_1", 0.0),
            "I_2": self.get_field_value(raw_data, "I_2", 0.0),
        }
