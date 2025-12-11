# ============================================================
# 文件说明: polling_service.py - 数据轮询服务（动态配置）
# ============================================================
# 方法列表:
# 1. _load_db_mappings()    - 加载DB映射配置
# 2. start_polling()        - 启动数据轮询任务
# 3. stop_polling()         - 停止数据轮询任务
# 4. _poll_data()           - 轮询数据并写入数据库
# 5. _poll_db()             - 轮询单个DB块数据
# 6. _write_device_to_influx() - 写入设备数据到InfluxDB
# ============================================================

import asyncio
import yaml
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, Any, List, Tuple

from config import get_settings
from app.core.influxdb import write_point
from app.plc.s7_client import S7Client
from app.plc.parser_hopper import HopperParser
from app.plc.parser_roller_kiln import RollerKilnParser
from app.plc.parser_scr_fan import SCRFanParser
from app.tools import get_converter, CONVERTER_MAP

settings = get_settings()

# 轮询任务句柄
_polling_task: Optional[asyncio.Task] = None
_is_running = False

# 解析器实例
_parsers: Dict[int, Any] = {}

# DB映射配置
_db_mappings: List[Dict[str, Any]] = []

# 历史重量缓存 (用于计算下料速度)
# 格式: {"device_id:module_tag": previous_weight}
_weight_history: Dict[str, float] = {}


# ------------------------------------------------------------
# 1. _load_db_mappings() - 加载DB映射配置
# ------------------------------------------------------------
def _load_db_mappings() -> List[Tuple[int, int]]:
    """从配置文件加载DB映射
    
    Returns:
        List[Tuple[int, int]]: [(db_number, total_size), ...]
    """
    global _db_mappings
    
    config_path = Path("configs/db_mappings.yaml")
    
    if not config_path.exists():
        print(f"⚠️  配置文件不存在: {config_path}，使用默认配置")
        return [(6, 554)]
    
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)
        
        _db_mappings = config.get('db_mappings', [])
        
        # 只返回启用的DB块配置
        enabled_configs = [
            (mapping['db_number'], mapping['total_size'])
            for mapping in _db_mappings
            if mapping.get('enabled', True)
        ]
        
        print(f"✅ 加载DB映射配置: {len(enabled_configs)}个DB块")
        for db_num, size in enabled_configs:
            mapping = next(m for m in _db_mappings if m['db_number'] == db_num)
            print(f"   - DB{db_num}: {mapping['db_name']} ({size}字节)")
        
        return enabled_configs
    
    except Exception as e:
        print(f"❌ 加载DB映射配置失败: {e}，使用默认配置")
        return [(6, 554)]


# ------------------------------------------------------------
# 2. _init_parsers() - 初始化解析器（动态）
# ------------------------------------------------------------
def _init_parsers():
    """根据配置文件动态初始化解析器"""
    global _parsers, _db_mappings
    
    parser_classes = {
        'HopperParser': HopperParser,
        'RollerKilnParser': RollerKilnParser,
        'SCRFanParser': SCRFanParser
    }
    
    _parsers = {}
    
    for mapping in _db_mappings:
        if not mapping.get('enabled', True):
            continue
        
        db_number = mapping['db_number']
        parser_class_name = mapping.get('parser_class')
        
        if parser_class_name in parser_classes:
            _parsers[db_number] = parser_classes[parser_class_name]()
            print(f"   ✅ DB{db_number} -> {parser_class_name}")
        else:
            print(f"   ⚠️  未知的解析器类: {parser_class_name}")


# ------------------------------------------------------------
# 3. start_polling() - 启动数据轮询任务
# ------------------------------------------------------------
async def start_polling():
    """启动数据轮询任务（从配置文件动态加载）"""
    global _polling_task, _is_running
    
    if _is_running:
        return
    
    # 加载DB映射配置
    _load_db_mappings()
    
    # 动态初始化解析器
    print("📦 初始化解析器:")
    _init_parsers()
    
    _is_running = True
    _polling_task = asyncio.create_task(_poll_data())
    print(f"✅ Polling started (interval: {settings.plc_poll_interval}s)")


# ------------------------------------------------------------
# 4. stop_polling() - 停止数据轮询任务
# ------------------------------------------------------------
async def stop_polling():
    """停止数据轮询任务"""
    global _polling_task, _is_running
    
    _is_running = False
    if _polling_task:
        _polling_task.cancel()
        try:
            await _polling_task
        except asyncio.CancelledError:
            pass
    print("⏹️ Polling stopped")


# ------------------------------------------------------------
# 5. _poll_data() - 轮询数据并写入数据库
# ------------------------------------------------------------
async def _poll_data():
    """轮询DB块数据并写入InfluxDB（动态配置）"""
    # 从配置文件加载DB块配置
    db_configs = _load_db_mappings()
    
    while _is_running:
        try:
            timestamp = datetime.now()
            
            # 并行读取DB块
            await asyncio.gather(
                *[_poll_db(db_num, size, timestamp) for db_num, size in db_configs],
                return_exceptions=True
            )
            
        except Exception as e:
            print(f"❌ Polling error: {e}")
        
        await asyncio.sleep(settings.plc_poll_interval)


# ------------------------------------------------------------
# 6. _poll_db() - 轮询单个DB块数据
# ------------------------------------------------------------
async def _poll_db(db_number: int, total_size: int, timestamp: datetime):
    """轮询单个DB块数据
    
    Args:
        db_number: DB块号 (动态配置)
        total_size: DB块大小
        timestamp: 时间戳
    """
    try:
        plc = S7Client(
            ip=settings.plc_ip,
            rack=settings.plc_rack,
            slot=settings.plc_slot,
            timeout_ms=settings.plc_timeout
        )
        plc.connect()
        
        # 读取DB块数据
        db_data = plc.read_db_block(db_number, 0, total_size)
        
        # 解析所有设备 (统一返回List格式)
        devices = _parsers[db_number].parse_all(db_data)
        
        # 写入InfluxDB
        for device in devices:
            _write_device_to_influx(device, db_number, timestamp)
        
        plc.disconnect()
        print(f"✅ DB{db_number}: {len(devices)}个设备数据已写入")
    
    except Exception as e:
        print(f"❌ DB{db_number}轮询失败: {e}")


# ------------------------------------------------------------
# 7. _write_device_to_influx() - 写入设备数据到InfluxDB
# ------------------------------------------------------------
def _write_device_to_influx(device_data: Dict[str, Any], db_number: int, timestamp: datetime):
    """写入设备数据到InfluxDB（使用转换器）
    
    统一写入格式:
    - measurement: sensor_data
    - tags: device_id, device_type, module_type, module_tag, db_number
    - fields: 转换后的精简字段
    
    Args:
        device_data: 解析后的设备数据
        db_number: DB块号
        timestamp: 时间戳
    """
    global _weight_history
    
    device_id = device_data['device_id']
    device_type = device_data['device_type']
    
    # 遍历所有模块
    for module_tag, module_data in device_data['modules'].items():
        module_type = module_data['module_type']
        raw_fields = module_data['fields']
        
        # 使用转换器转换数据
        if module_type in CONVERTER_MAP:
            converter = get_converter(module_type)
            
            # 称重模块需要传入历史数据
            if module_type == 'WeighSensor':
                cache_key = f"{device_id}:{module_tag}"
                previous_weight = _weight_history.get(cache_key)
                
                fields = converter.convert(
                    raw_fields,
                    previous_weight=previous_weight,
                    interval=settings.plc_poll_interval
                )
                
                # 更新历史缓存
                _weight_history[cache_key] = fields.get('weight', 0.0)
            else:
                fields = converter.convert(raw_fields)
        else:
            # 未知模块类型，直接提取原始值
            fields = {}
            for field_name, field_info in raw_fields.items():
                fields[field_name] = field_info['value']
        
        # 跳过空字段
        if not fields:
            continue
        
        # 写入InfluxDB
        write_point(
            measurement="sensor_data",
            tags={
                "device_id": device_id,
                "device_type": device_type,
                "module_type": module_type,
                "module_tag": module_tag,
                "db_number": str(db_number)
            },
            fields=fields,
            timestamp=timestamp
        )

