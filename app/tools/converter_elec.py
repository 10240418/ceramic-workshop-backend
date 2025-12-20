# ============================================================
# 电表转换器 (ElectricityMeter)
# ============================================================
# 存储字段: Pt, ImpEp, Ua_0, I_0 (只存4个关键字段)
# ============================================================

from typing import Dict, Any
from .converter_base import BaseConverter


class ElectricityConverter(BaseConverter):
    """
    三相电表数据转换器 (精简版)
    
    输入字段 (PLC原始):
        - Uab_0, Uab_1, Uab_2: 线电压 (不存储)
        - Ua_0, Ua_1, Ua_2: 相电压 (只存A相)
        - I_0, I_1, I_2: 相电流 (只存A相)
        - Pt: 总有功功率
        - Pa, Pb, Pc: 各相功率 (不存储)
        - ImpEp: 正向有功电能
    
    输出字段 (只存储4个):
        - Pt: 总有功功率 (kW) - 除以10
        - ImpEp: 正向有功电能 (kWh) - 除以10
        - Ua_0: A相电压 (V) - 除以10
        - I_0: A相电流 (A) - 除以10
    """
    
    MODULE_TYPE = "ElectricityMeter"
    
    OUTPUT_FIELDS = {
        "Pt": {"display_name": "总有功功率", "unit": "kW"},
        "ImpEp": {"display_name": "正向有功电能", "unit": "kWh"},
        "Ua_0": {"display_name": "A相电压", "unit": "V"},
        "I_0": {"display_name": "A相电流", "unit": "A"},
    }
    
    # PLC数据缩放系数 (PLC存储值需要除以10得到实际值)
    DEFAULT_SCALE = 0.1
    
    def convert(self, raw_data: Dict[str, Any], **kwargs) -> Dict[str, Any]:
        """
        转换电表数据 (只保留4个关键字段)
        
        Args:
            raw_data: Parser 解析后的原始数据
            **kwargs:
                - scale: 缩放系数 (默认 0.1，即除以10)
        
        Returns:
            存储字段字典 (只有4个字段)
        
        说明:
            PLC中的电表数据需要除以10得到实际值
            例如: PLC存储 2200 → 实际电压 220.0V
                  PLC存储 456 → 实际功率 45.6kW
        """
        scale = kwargs.get('scale', self.DEFAULT_SCALE)
        
        return {
            # 功率和电能 (除以10)
            "Pt": round(self.get_field_value(raw_data, "Pt", 0.0) * scale, 2),
            "ImpEp": round(self.get_field_value(raw_data, "ImpEp", 0.0) * scale, 2),
            
            # 只保留A相电压和电流 (除以10)
            "Ua_0": round(self.get_field_value(raw_data, "Ua_0", 0.0) * scale, 1),
            "I_0": round(self.get_field_value(raw_data, "I_0", 0.0) * scale, 2),
        }
