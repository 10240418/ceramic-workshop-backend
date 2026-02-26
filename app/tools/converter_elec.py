# ============================================================
# 电表转换器 (ElectricityMeter)
# ============================================================
# 实时数据字段: Pt, ImpEp, Ua_0, I_0, I_1, I_2 (7个字段，用于API返回)
# 存储字段: Pt, ImpEp, Ua_0 (3个字段，不存储三相电流)
# 
# [FIX] 2026-01-10 更新计算公式 (根据实际PLC原始数据验证):
# [FIX] 2026-01-20 功率系数调整: 原 0.001 → 0.0001 (×0.1)
#   - 电压 Ua: raw × 0.1 (不乘变比)
#   - 电流 I:  raw × 0.001 × ratio (料仓/风机=20, 辊道窑=60, SCR=20)
#   - 功率 Pt: raw × 0.0001 × ratio
#   - 能耗 ImpEp: raw × 2 (不乘变比，直接乘2)
# ============================================================

from typing import Dict, Any
from .converter_base import BaseConverter


class ElectricityConverter(BaseConverter):
    """
    三相电表数据转换器
    
    输入字段 (PLC原始 - 单精度浮点数):
        - Uab_0, Uab_1, Uab_2: 线电压 (不存储)
        - Ua_0, Ua_1, Ua_2: 三相电压 (只存A相 Ua_0)
        - I_0, I_1, I_2: 三相电流 (实时显示，不存储)
        - Pt: 总有功功率
        - Pa, Pb, Pc: 各相功率 (不存储)
        - ImpEp: 正向有功电能
    
    计算公式 (2026-01-20 更新):
        - 电压: raw × 0.1 → 实际电压 (V)
        - 电流: raw × 0.001 × ratio → 实际电流 (A)
        - 功率: raw × 0.0001 × ratio → 实际功率 (kW)
        - 能耗: raw × 2 → 实际能耗 (kWh)
    
    电流互感器变比:
        - 辊道窑 (roller_kiln): ratio = 60
        - 料仓/风机 (hopper/fan): ratio = 20
        - SCR氨水泵 (scr): ratio = 20
    """
    
    MODULE_TYPE = "ElectricityMeter"
    
    # 电流互感器变比配置 (实际变比值)
    CURRENT_RATIO_ROLLER = 60     # 辊道窑电流变比
    CURRENT_RATIO_DEFAULT = 20    # 料仓/风机电流变比
    CURRENT_RATIO_SCR = 20        # SCR氨水泵电流变比 (与料仓/风机相同)
    
    # 缩放系数
    SCALE_VOLTAGE = 0.1           # 电压: raw × 0.1
    SCALE_CURRENT = 0.001         # 电流: raw × 0.001 × ratio
    SCALE_POWER = 0.0001          # 功率: raw × 0.0001 × ratio (2026-01-20: 原0.001×0.1)
    SCALE_ENERGY = 2.0            # 能耗: raw × 2 (不乘变比)
    
    # 实时数据字段 (包含三相电流，用于API返回)
    REALTIME_FIELDS = {
        "Pt": {"display_name": "总有功功率", "unit": "kW"},
        "ImpEp": {"display_name": "正向有功电能", "unit": "kWh"},
        "Ua_0": {"display_name": "A相电压", "unit": "V"},
        "I_0": {"display_name": "A相电流", "unit": "A"},
        "I_1": {"display_name": "B相电流", "unit": "A"},
        "I_2": {"display_name": "C相电流", "unit": "A"},
    }
    
    # 存储字段 (含三相电流，用于写入数据库)
    OUTPUT_FIELDS = {
        "Pt": {"display_name": "总有功功率", "unit": "kW"},
        "ImpEp": {"display_name": "正向有功电能", "unit": "kWh"},
        "Ua_0": {"display_name": "A相电压", "unit": "V"},
        "I_0": {"display_name": "A相电流", "unit": "A"},
        "I_1": {"display_name": "B相电流", "unit": "A"},
        "I_2": {"display_name": "C相电流", "unit": "A"},
    }
    
    # 保留旧的 DEFAULT_SCALE 用于兼容
    DEFAULT_SCALE = 0.1
    
    def convert(self, raw_data: Dict[str, Any], **kwargs) -> Dict[str, Any]:
        """
        转换电表数据 (包含三相电流，用于实时API)
        
        Args:
            raw_data: Parser 解析后的原始数据 (单精度浮点数)
            **kwargs:
                - is_roller_kiln: 是否是辊道窑设备 (默认 False, ratio=60)
                - is_scr: 是否是SCR氨水泵 (默认 False, ratio=2)
                - current_ratio: 手动指定变比 (覆盖默认值)
        
        Returns:
            实时数据字段字典 (6个字段，包含三相电流)
        
        计算公式:
            - 电压: raw × 0.1
            - 电流: raw × 0.001 × ratio
            - 功率: raw × 0.0001 × ratio
            - 能耗: raw × 2
        """
        # 判断电流变比: 优先级 is_scr > is_roller_kiln > default
        is_scr = kwargs.get('is_scr', False)
        is_roller_kiln = kwargs.get('is_roller_kiln', False)
        
        if is_scr:
            current_ratio = self.CURRENT_RATIO_SCR
        elif is_roller_kiln:
            current_ratio = self.CURRENT_RATIO_ROLLER
        else:
            current_ratio = self.CURRENT_RATIO_DEFAULT
        
        # 允许手动指定变比（覆盖默认值）
        current_ratio = kwargs.get('current_ratio', current_ratio)
        
        return {
            # 功率: raw × 0.0001 × ratio (保留3位小数)
            "Pt": round(self.get_field_value(raw_data, "Pt", 0.0) * self.SCALE_POWER * current_ratio, 3),
            
            # 能耗: raw × ratio (直接乘变比，不乘2)
            "ImpEp": round(self.get_field_value(raw_data, "ImpEp", 0.0) * current_ratio, 2),
            
            # A相电压: raw × 0.1 (不乘变比)
            "Ua_0": round(self.get_field_value(raw_data, "Ua_0", 0.0) * self.SCALE_VOLTAGE, 1),
            
            # 三相电流: raw × 0.001 × ratio
            "I_0": round(self.get_field_value(raw_data, "I_0", 0.0) * self.SCALE_CURRENT * current_ratio, 2),
            "I_1": round(self.get_field_value(raw_data, "I_1", 0.0) * self.SCALE_CURRENT * current_ratio, 2),
            "I_2": round(self.get_field_value(raw_data, "I_2", 0.0) * self.SCALE_CURRENT * current_ratio, 2),
        }
    
    def convert_for_storage(self, raw_data: Dict[str, Any], **kwargs) -> Dict[str, Any]:
        """
        转换电表数据 (含三相电流，用于存储到数据库)

        Args:
            raw_data: Parser 解析后的原始数据
            **kwargs:
                - is_roller_kiln: 是否是辊道窑设备 (默认 False)
                - is_scr: 是否是SCR氨水泵 (默认 False)
                - current_ratio: 手动指定变比 (覆盖默认值)

        Returns:
            存储字段字典 (6个字段: Pt, ImpEp, Ua_0, I_0, I_1, I_2)
        """
        # 判断电流变比: 优先级 is_scr > is_roller_kiln > default
        is_scr = kwargs.get('is_scr', False)
        is_roller_kiln = kwargs.get('is_roller_kiln', False)

        if is_scr:
            current_ratio = self.CURRENT_RATIO_SCR
        elif is_roller_kiln:
            current_ratio = self.CURRENT_RATIO_ROLLER
        else:
            current_ratio = self.CURRENT_RATIO_DEFAULT

        # 允许手动指定变比（覆盖默认值）
        current_ratio = kwargs.get('current_ratio', current_ratio)

        return {
            # 功率: raw × 0.0001 × ratio (保留3位小数)
            "Pt": round(self.get_field_value(raw_data, "Pt", 0.0) * self.SCALE_POWER * current_ratio, 3),

            # 能耗: raw × ratio (直接乘变比，不乘2)
            "ImpEp": round(self.get_field_value(raw_data, "ImpEp", 0.0) * current_ratio, 2),

            # A相电压: raw × 0.1 (不乘变比)
            "Ua_0": round(self.get_field_value(raw_data, "Ua_0", 0.0) * self.SCALE_VOLTAGE, 1),

            # 三相电流: raw × 0.001 × ratio
            "I_0": round(self.get_field_value(raw_data, "I_0", 0.0) * self.SCALE_CURRENT * current_ratio, 2),
            "I_1": round(self.get_field_value(raw_data, "I_1", 0.0) * self.SCALE_CURRENT * current_ratio, 2),
            "I_2": round(self.get_field_value(raw_data, "I_2", 0.0) * self.SCALE_CURRENT * current_ratio, 2),
        }

