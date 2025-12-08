# ============================================================
# 文件说明: plc_service.py - PLC通信服务 (生产模式)
# ============================================================
# 方法列表:
# 1. read_roller_kiln_data()    - 读取辊道窑数据
# 2. read_rotary_kiln_data()    - 读取回转窑数据
# 3. read_scr_data()            - 读取SCR设备数据
# 4. _load_configs()            - [私有] 加载YAML配置
# 5. _read_device_data()        - [私有] 读取设备数据
# ============================================================

from typing import Dict, Any
from datetime import datetime
from pathlib import Path
import yaml
from app.plc.s7_client import get_s7_client
from app.plc.data_parser import parse_sensor_value_simple
from config import get_settings


# ------------------------------------------------------------
# PLCService - PLC通信服务
# ------------------------------------------------------------
class PLCService:
    """PLC通信服务 (用于生产环境，使用YAML配置)"""
    
    def __init__(self):
        self.client = get_s7_client()
        self.sensors_config = None
        self.devices_config = None
        self._load_configs()
    
    # ------------------------------------------------------------
    # 4. _load_configs() - [私有] 加载YAML配置
    # ------------------------------------------------------------
    def _load_configs(self):
        """加载传感器和设备配置"""
        settings = get_settings()
        
        # 加载传感器配置
        sensors_path = Path(settings.config_dir) / "sensors.yaml"
        with open(sensors_path, 'r', encoding='utf-8') as f:
            self.sensors_config = yaml.safe_load(f)
        
        # 加载设备配置
        devices_path = Path(settings.config_dir) / "devices.yaml"
        with open(devices_path, 'r', encoding='utf-8') as f:
            self.devices_config = yaml.safe_load(f)
    
    # ------------------------------------------------------------
    # 1. read_roller_kiln_data() - 读取辊道窑数据
    # ------------------------------------------------------------
    def read_roller_kiln_data(self) -> Dict[str, Any]:
        """
        读取辊道窑实时数据
        
        Returns:
            Dict: 包含温度、能耗等数据的字典
        """
        # 获取第一个启用的辊道窑配置
        for kiln in self.devices_config.get('roller_kilns', []):
            if kiln.get('enabled', False):
                return self._read_device_data(
                    db_number=kiln['db_number'],
                    template=self.sensors_config.get('roller_kiln_template', {})
                )
        
        return {"timestamp": datetime.now(), "error": "No enabled roller kiln found"}
    
    # ------------------------------------------------------------
    # 2. read_rotary_kiln_data() - 读取回转窑数据
    # ------------------------------------------------------------
    def read_rotary_kiln_data(self, device_id: int) -> Dict[str, Any]:
        """
        读取回转窑实时数据
        
        Args:
            device_id: 设备编号 (1-7)
        
        Returns:
            Dict: 包含温度、能耗、下料、料仓等数据的字典
        """
        # 查找设备配置
        for kiln in self.devices_config.get('rotary_kilns', []):
            if kiln['id'] == device_id and kiln.get('enabled', False):
                return self._read_device_data(
                    db_number=kiln['db_number'],
                    template=self.sensors_config.get('rotary_kiln_template', {})
                )
        
        return {"timestamp": datetime.now(), "error": f"Rotary kiln {device_id} not found or disabled"}
    
    # ------------------------------------------------------------
    # 3. read_scr_data() - 读取SCR设备数据
    # ------------------------------------------------------------
    def read_scr_data(self, device_id: int) -> Dict[str, Any]:
        """
        读取SCR设备实时数据
        
        Args:
            device_id: 设备编号 (1-2)
        
        Returns:
            Dict: 包含风机、氨水泵、燃气管路等数据的字典
        """
        # 查找设备配置
        for scr in self.devices_config.get('scr_equipment', []):
            if scr['id'] == device_id and scr.get('enabled', False):
                return self._read_device_data(
                    db_number=scr['db_number'],
                    template=self.sensors_config.get('scr_template', {})
                )
        
        return {"timestamp": datetime.now(), "error": f"SCR equipment {device_id} not found or disabled"}
    
    # ------------------------------------------------------------
    # 5. _read_device_data() - [私有] 读取设备数据
    # ------------------------------------------------------------
    def _read_device_data(self, db_number: int, template: Dict) -> Dict[str, Any]:
        """
        根据模板配置读取设备数据
        
        Args:
            db_number: PLC DB块编号
            template: 传感器模板配置
        
        Returns:
            Dict: 包含所有传感器数据的字典
        """
        if not self.client.is_connected():
            self.client.connect()
        
        result = {"timestamp": datetime.now()}
        
        # 读取温度数据
        if 'temperature_zones' in template:
            zones = []
            for zone in template['temperature_zones']:
                offset = zone['db_offset']
                data = self.client.read_db_block(db_number, offset, 2)  # WORD = 2 bytes
                value = parse_sensor_value_simple(data, zone['data_type'], zone.get('scale', 1))
                zones.append({
                    "zone_id": zone['zone_id'],
                    "temperature": value
                })
            result['zones'] = zones
        
        # 读取能耗数据
        if 'energy' in template:
            energy = template['energy']
            for key, config in energy.items():
                offset = config['db_offset']
                size = 2 if config['data_type'] == 'WORD' else 4
                data = self.client.read_db_block(db_number, offset, size)
                value = parse_sensor_value_simple(data, config['data_type'], config.get('scale', 1))
                result[key] = value
        
        # 读取下料系统数据
        if 'feed_system' in template:
            feed = template['feed_system']
            for key, config in feed.items():
                offset = config['db_offset']
                size = 2 if config['data_type'] == 'WORD' else 4
                data = self.client.read_db_block(db_number, offset, size)
                value = parse_sensor_value_simple(data, config['data_type'], config.get('scale', 1))
                result[key] = value
        
        return result
