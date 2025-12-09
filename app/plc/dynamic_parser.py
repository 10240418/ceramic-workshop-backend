# ============================================================
# 文件说明: dynamic_parser.py - 通用 PLC 数据动态解析器
# ============================================================
# 方法列表:
# 1. load_mapping_config()      - 加载配置文件
# 2. parse_field()              - 解析单个字段
# 3. parse_db_block()           - 解析整个 DB 块
# 4. get_db_config()            - 获取指定 DB 配置
# ============================================================

import struct
import yaml
from pathlib import Path
from typing import Dict, Any, List, Optional

class DynamicPLCParser:
    """通用 PLC 数据动态解析器
    
    根据 YAML 配置文件自动解析任意 DB 块数据
    无需修改代码，只需修改配置文件即可适配不同的 PLC 数据结构
    """
    
    def __init__(self, config_path: str = "configs/plc_mapping.yaml"):
        """初始化解析器
        
        Args:
            config_path: 配置文件路径
        """
        self.config_path = Path(config_path)
        self.config = self._load_config()
    
    # ------------------------------------------------------------
    # 1. _load_config() - 加载配置文件
    # ------------------------------------------------------------
    def _load_config(self) -> Dict[str, Any]:
        """加载 PLC 映射配置文件"""
        if not self.config_path.exists():
            raise FileNotFoundError(f"配置文件不存在: {self.config_path}")
        
        with open(self.config_path, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f)
    
    # ------------------------------------------------------------
    # 2. _parse_field() - 解析单个字段
    # ------------------------------------------------------------
    def _parse_field(self, data: bytes, field_config: Dict[str, Any]) -> Any:
        """根据字段配置解析数据
        
        Args:
            data: 原始字节数据
            field_config: 字段配置 (包含 offset, data_type, scale 等)
            
        Returns:
            解析后的数值
        """
        offset = field_config['offset']
        data_type = field_config['data_type']
        scale = field_config.get('scale', 1)
        
        # 根据数据类型解析
        if data_type == 'WORD':  # 16-bit unsigned
            raw_value = struct.unpack('>H', data[offset:offset+2])[0]
        elif data_type == 'DWORD':  # 32-bit unsigned
            raw_value = struct.unpack('>I', data[offset:offset+4])[0]
        elif data_type == 'INT':  # 16-bit signed
            raw_value = struct.unpack('>h', data[offset:offset+2])[0]
        elif data_type == 'DINT':  # 32-bit signed
            raw_value = struct.unpack('>i', data[offset:offset+4])[0]
        elif data_type == 'REAL':  # 32-bit float
            raw_value = struct.unpack('>f', data[offset:offset+4])[0]
        elif data_type == 'LREAL':  # 64-bit float
            raw_value = struct.unpack('>d', data[offset:offset+8])[0]
        elif data_type == 'BOOL':  # Boolean (1 byte)
            raw_value = data[offset] != 0
        elif data_type == 'BYTE':  # 8-bit unsigned
            raw_value = data[offset]
        elif data_type == 'ARRAY':  # 字节数组
            array_size = field_config.get('array_size', 1)
            raw_value = list(data[offset:offset+array_size])
        else:
            raise ValueError(f"不支持的数据类型: {data_type}")
        
        # 应用缩放因子 (数组和布尔值不缩放)
        if data_type not in ['ARRAY', 'BOOL']:
            return raw_value * scale
        return raw_value
    
    # ------------------------------------------------------------
    # 3. parse_db_block() - 解析整个 DB 块
    # ------------------------------------------------------------
    def parse_db_block(self, db_key: str, data: bytes) -> Dict[str, Any]:
        """解析指定 DB 块的所有数据
        
        Args:
            db_key: DB 块配置键名 (如 'db6_slave_data')
            data: 从 PLC 读取的原始字节数据
            
        Returns:
            解析后的结构化数据字典
        """
        if db_key not in self.config:
            raise ValueError(f"未找到 DB 块配置: {db_key}")
        
        db_config = self.config[db_key]
        result = {
            'db_number': db_config['db_number'],
            'description': db_config['description'],
            'groups': {}
        }
        
        # 遍历所有分组 (如 weigh_sensor, flow_meter 等)
        for group_name, group_config in db_config.items():
            # 跳过元数据字段
            if group_name in ['db_number', 'description', 'total_size', 'enabled']:
                continue
            
            # 跳过未启用的分组
            if not group_config.get('enabled', True):
                continue
            
            group_data = {
                'description': group_config.get('description', ''),
                'fields': {}
            }
            
            # 解析分组中的所有字段
            for field_config in group_config.get('fields', []):
                field_name = field_config['name']
                try:
                    value = self._parse_field(data, field_config)
                    group_data['fields'][field_name] = {
                        'value': value,
                        'display_name': field_config['display_name'],
                        'unit': field_config['unit'],
                        'raw_offset': field_config['offset']
                    }
                except Exception as e:
                    print(f"⚠️  解析字段失败: {field_name}, 错误: {e}")
                    group_data['fields'][field_name] = {
                        'value': None,
                        'error': str(e)
                    }
            
            result['groups'][group_name] = group_data
        
        return result
    
    # ------------------------------------------------------------
    # 4. get_db_config() - 获取指定 DB 配置
    # ------------------------------------------------------------
    def get_db_config(self, db_key: str) -> Dict[str, Any]:
        """获取指定 DB 块的配置信息
        
        Args:
            db_key: DB 块配置键名
            
        Returns:
            DB 块配置字典
        """
        if db_key not in self.config:
            raise ValueError(f"未找到 DB 块配置: {db_key}")
        return self.config[db_key]
    
    # ------------------------------------------------------------
    # 5. list_available_dbs() - 列出所有可用的 DB 块
    # ------------------------------------------------------------
    def list_available_dbs(self) -> List[Dict[str, Any]]:
        """列出配置文件中所有的 DB 块
        
        Returns:
            DB 块列表 (包含 key, db_number, description, enabled)
        """
        dbs = []
        for key, config in self.config.items():
            if isinstance(config, dict) and 'db_number' in config:
                dbs.append({
                    'key': key,
                    'db_number': config['db_number'],
                    'description': config.get('description', ''),
                    'enabled': config.get('enabled', True)
                })
        return dbs
    
    # ------------------------------------------------------------
    # 6. format_output() - 格式化输出解析结果
    # ------------------------------------------------------------
    def format_output(self, parsed_data: Dict[str, Any]) -> str:
        """格式化输出解析后的数据 (用于调试)
        
        Args:
            parsed_data: parse_db_block() 返回的结果
            
        Returns:
            格式化的字符串
        """
        lines = []
        lines.append("=" * 70)
        lines.append(f"DB{parsed_data['db_number']}: {parsed_data['description']}")
        lines.append("=" * 70)
        
        for group_name, group_data in parsed_data['groups'].items():
            lines.append(f"\n【{group_data['description']}】")
            for field_name, field_data in group_data['fields'].items():
                if 'error' in field_data:
                    lines.append(f"  ❌ {field_data.get('display_name', field_name)}: 解析错误")
                else:
                    value = field_data['value']
                    unit = field_data['unit']
                    display_name = field_data['display_name']
                    
                    # 格式化数值
                    if isinstance(value, float):
                        value_str = f"{value:.2f}"
                    elif isinstance(value, list):
                        value_str = f"[{', '.join(str(v) for v in value)}]"
                    else:
                        value_str = str(value)
                    
                    lines.append(f"  {display_name}: {value_str} {unit}")
        
        return "\n".join(lines)


# ============================================================
# 使用示例
# ============================================================
if __name__ == "__main__":
    # 创建解析器
    parser = DynamicPLCParser()
    
    # 列出所有可用的 DB 块
    print("可用的 DB 块配置:")
    for db in parser.list_available_dbs():
        status = "✅ 启用" if db['enabled'] else "❌ 禁用"
        print(f"  DB{db['db_number']}: {db['description']} - {status}")
