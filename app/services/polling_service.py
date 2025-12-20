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
        
        # 使用运行时配置的轮询间隔（支持热更新）
        from app.routers.config import get_runtime_plc_config
        plc_config = get_runtime_plc_config()
        await asyncio.sleep(plc_config["poll_interval"])


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
        # 使用运行时配置（支持热更新）
        from app.routers.config import get_runtime_plc_config
        plc_config = get_runtime_plc_config()
        
        plc = S7Client(
            ip=plc_config["ip_address"],
            rack=plc_config["rack"],
            slot=plc_config["slot"],
            timeout_ms=plc_config["timeout_ms"]
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
        
        # 详细输出每个设备的数据
        _print_devices_detail(devices, db_number)
    
    except Exception as e:
        print(f"❌ DB{db_number}轮询失败: {e}")


# ------------------------------------------------------------
# 辅助函数: 打印设备详细数据
# ------------------------------------------------------------
def _print_devices_detail(devices: List[Dict[str, Any]], db_number: int):
    """打印设备详细数据
    
    Args:
        devices: 设备数据列表
        db_number: DB块号
    """
    from config import get_settings
    settings = get_settings()
    
    # 检查是否启用详细日志
    if not getattr(settings, 'verbose_polling_log', True):
        print(f"✅ DB{db_number}: {len(devices)}个设备数据已写入")
        return
    
    print(f"\n{'='*60}")
    print(f"📊 DB{db_number} 轮询数据 ({len(devices)}个设备)")
    print(f"{'='*60}")
    
    for device in devices:
        device_id = device['device_id']
        device_type = device['device_type']
        
        print(f"\n  📦 {device_id} ({device_type})")
        print(f"  {'-'*50}")
        
        for module_tag, module_data in device['modules'].items():
            module_type = module_data['module_type']
            raw_fields = module_data['fields']
            
            # 获取转换后的数据用于显示
            if module_type in CONVERTER_MAP:
                converter = get_converter(module_type)
                
                if module_type == 'WeighSensor':
                    cache_key = f"{device_id}:{module_tag}"
                    previous_weight = _weight_history.get(cache_key)
                    fields = converter.convert(
                        raw_fields,
                        previous_weight=previous_weight,
                        interval=settings.plc_poll_interval
                    )
                else:
                    fields = converter.convert(raw_fields)
            else:
                fields = {k: v['value'] for k, v in raw_fields.items()}
            
            # 格式化输出
            _print_module_data(module_tag, module_type, fields)
    
    print(f"\n{'='*60}\n")


def _print_module_data(module_tag: str, module_type: str, fields: Dict[str, Any]):
    """格式化打印模块数据
    
    Args:
        module_tag: 模块标签
        module_type: 模块类型
        fields: 转换后的字段数据
    """
    # 模块类型图标
    icons = {
        'ElectricityMeter': '⚡',
        'TemperatureSensor': '🌡️',
        'WeighSensor': '⚖️',
        'GasMeter': '💨',
    }
    icon = icons.get(module_type, '📍')
    
    # 单位映射
    units = {
        'Pt': 'kW',
        'ImpEp': 'kWh',
        'Ua_0': 'V', 'Ua_1': 'V', 'Ua_2': 'V',
        'I_0': 'A', 'I_1': 'A', 'I_2': 'A',
        'temperature': '°C',
        'set_point': '°C',
        'weight': 'kg',
        'feed_rate': 'kg/h',
        'flow_rate': 'm³/h',
        'total_flow': 'm³',
    }
    
    print(f"    {icon} [{module_tag}] {module_type}:")
    
    # 按类型格式化输出
    if module_type == 'ElectricityMeter':
        # 电表数据: 功率、电能、电压、电流
        pt = fields.get('Pt', 0)
        ep = fields.get('ImpEp', 0)
        ua = [fields.get(f'Ua_{i}', 0) for i in range(3)]
        ia = [fields.get(f'I_{i}', 0) for i in range(3)]
        print(f"       功率: {pt:.2f}kW | 电能: {ep:.2f}kWh")
        print(f"       电压: {ua[0]:.1f}/{ua[1]:.1f}/{ua[2]:.1f} V")
        print(f"       电流: {ia[0]:.2f}/{ia[1]:.2f}/{ia[2]:.2f} A")
    
    elif module_type == 'TemperatureSensor':
        temp = fields.get('temperature', 0)
        sp = fields.get('set_point', 0)
        print(f"       温度: {temp:.1f}°C | 设定值: {sp:.1f}°C")
    
    elif module_type == 'WeighSensor':
        weight = fields.get('weight', 0)
        feed_rate = fields.get('feed_rate', 0)
        is_stable = fields.get('is_stable', False)
        is_overload = fields.get('is_overload', False)
        stable_str = "稳定" if is_stable else "动态"
        overload_str = " [超载!]" if is_overload else ""
        print(f"       重量: {weight:.3f}kg | 下料速率: {feed_rate:.2f}kg/h | {stable_str}{overload_str}")
    
    elif module_type == 'GasMeter':
        flow = fields.get('flow_rate', 0)
        total = fields.get('total_flow', 0)
        print(f"       流量: {flow:.2f}m³/h | 累计: {total:.2f}m³")
    
    else:
        # 通用输出
        for key, value in fields.items():
            unit = units.get(key, '')
            if isinstance(value, float):
                print(f"       {key}: {value:.2f}{unit}")
            else:
                print(f"       {key}: {value}{unit}")


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

