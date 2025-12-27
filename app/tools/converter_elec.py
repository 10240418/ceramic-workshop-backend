# ============================================================
# 电表转换器 (ElectricityMeter)
# ============================================================
# 实时数据字段: Pt, ImpEp, Ua_0, I_0, I_1, I_2 (7个字段，用于API返回)
# 存储字段: Pt, ImpEp, Ua_0 (3个字段，不存储三相电流)
# 电流变比: 辊道窑=60, 其余=20
# ============================================================

from typing import Dict, Any
from .converter_base import BaseConverter


class ElectricityConverter(BaseConverter):
    """
    三相电表数据转换器
    
    输入字段 (PLC原始):
        - Uab_0, Uab_1, Uab_2: 线电压 (不存储)
        - Ua_0, Ua_1, Ua_2: 三相电压 (只存A相 Ua_0)
        - I_0, I_1, I_2: 三相电流 (实时显示，不存储)
        - Pt: 总有功功率
        - Pa, Pb, Pc: 各相功率 (不存储)
        - ImpEp: 正向有功电能
    
    实时数据字段 (API返回，7个):
        - Pt: 总有功功率 (kW)
        - ImpEp: 正向有功电能 (kWh)
        - Ua_0: A相电压 (V)
        - I_0: A相电流 (A) - 已乘变比
        - I_1: B相电流 (A) - 已乘变比
        - I_2: C相电流 (A) - 已乘变比
    
    存储字段 (写入InfluxDB，3个):
        - Pt: 总有功功率 (kW)
        - ImpEp: 正向有功电能 (kWh)
        - Ua_0: A相电压 (V)
    
    电流变比说明:
        PLC读取的是电流互感器二次侧数据，需要乘以变比得到一次侧实际电流
        - 辊道窑 (roller_kiln): 变比 = 60
        - 其余设备 (hopper, scr, fan): 变比 = 20
    """
    
    MODULE_TYPE = "ElectricityMeter"
    
    # 电流变比配置
    CURRENT_RATIO_ROLLER = 60   # 辊道窑电流变比
    CURRENT_RATIO_DEFAULT = 20  # 其余设备电流变比
    
    # 实时数据字段 (包含三相电流，用于API返回)
    REALTIME_FIELDS = {
        "Pt": {"display_name": "总有功功率", "unit": "kW"},
        "ImpEp": {"display_name": "正向有功电能", "unit": "kWh"},
        "Ua_0": {"display_name": "A相电压", "unit": "V"},
        "I_0": {"display_name": "A相电流", "unit": "A"},
        "I_1": {"display_name": "B相电流", "unit": "A"},
        "I_2": {"display_name": "C相电流", "unit": "A"},
    }
    
    # 存储字段 (不含三相电流，用于写入数据库)
    OUTPUT_FIELDS = {
        "Pt": {"display_name": "总有功功率", "unit": "kW"},
        "ImpEp": {"display_name": "正向有功电能", "unit": "kWh"},
        "Ua_0": {"display_name": "A相电压", "unit": "V"},
    }
    
    # PLC数据缩放系数 (PLC存储值需要除以10得到实际值)
    DEFAULT_SCALE = 0.1
    
    def convert(self, raw_data: Dict[str, Any], **kwargs) -> Dict[str, Any]:
        """
        转换电表数据 (包含三相电流，用于实时API)
        
        Args:
            raw_data: Parser 解析后的原始数据
            **kwargs:
                - scale: 缩放系数 (默认 0.1，即除以10)
                - current_ratio: 电流变比 (默认 20，辊道窑用 60)
                - is_roller_kiln: 是否是辊道窑设备 (默认 False)
        
        Returns:
            实时数据字段字典 (7个字段，包含三相电流)
        """
        scale = kwargs.get('scale', self.DEFAULT_SCALE)
        
        # 判断电流变比
        is_roller_kiln = kwargs.get('is_roller_kiln', False)
        current_ratio = kwargs.get('current_ratio', 
                                   self.CURRENT_RATIO_ROLLER if is_roller_kiln else self.CURRENT_RATIO_DEFAULT)
        
        return {
            # 功率和电能 (除以10)
            "Pt": round(self.get_field_value(raw_data, "Pt", 0.0) * scale, 2),
            "ImpEp": round(self.get_field_value(raw_data, "ImpEp", 0.0) * scale, 2),
            
            # A相电压 (除以10)
            "Ua_0": round(self.get_field_value(raw_data, "Ua_0", 0.0) * scale, 1),
            
            # 三相电流 (除以10后乘变比) - 用于实时显示
            "I_0": round(self.get_field_value(raw_data, "I_0", 0.0) * scale * current_ratio, 2),
            "I_1": round(self.get_field_value(raw_data, "I_1", 0.0) * scale * current_ratio, 2),
            "I_2": round(self.get_field_value(raw_data, "I_2", 0.0) * scale * current_ratio, 2),
        }
    
    def convert_for_storage(self, raw_data: Dict[str, Any], **kwargs) -> Dict[str, Any]:
        """
        转换电表数据 (不含三相电流，用于存储到数据库)
        
        Args:
            raw_data: Parser 解析后的原始数据
            **kwargs:
                - scale: 缩放系数 (默认 0.1，即除以10)
        
        Returns:
            存储字段字典 (3个字段，不含三相电流)
        """
        scale = kwargs.get('scale', self.DEFAULT_SCALE)
        
        return {
            # 功率和电能 (除以10)
            "Pt": round(self.get_field_value(raw_data, "Pt", 0.0) * scale, 2),
            "ImpEp": round(self.get_field_value(raw_data, "ImpEp", 0.0) * scale, 2),
            
            # A相电压 (除以10)
            "Ua_0": round(self.get_field_value(raw_data, "Ua_0", 0.0) * scale, 1),
        }

