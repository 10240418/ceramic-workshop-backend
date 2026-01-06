# ============================================================
# 文件说明: polling_service.py - 优化版数据轮询服务
# ============================================================
# 优化点:
#   1. PLC 长连接 (避免频繁连接/断开)
#   2. 批量写入 (30 次轮询缓存后批量写入)
#   3. 本地降级缓存 (InfluxDB 故障时写入 SQLite)
#   4. 自动重试机制 (缓存数据自动重试)
#   5. 内存缓存 (供 API 直接读取最新数据)
#   6. Mock模式支持 (使用模拟数据替代真实PLC)
# ============================================================

import asyncio
import yaml
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List, Tuple
from collections import deque

from config import get_settings
from app.core.timezone_utils import now_beijing, beijing_isoformat
from app.core.influxdb import build_point, write_points_batch, check_influx_health
from app.core.local_cache import get_local_cache, CachedPoint
from app.plc.plc_manager import get_plc_manager
from app.plc.parser_hopper import HopperParser
from app.plc.parser_roller_kiln import RollerKilnParser
from app.plc.parser_scr_fan import SCRFanParser
from app.tools import get_converter, CONVERTER_MAP

settings = get_settings()

# Mock数据生成器（延迟导入，仅在mock模式下使用）
_mock_generator = None

# 轮询任务句柄
_polling_task: Optional[asyncio.Task] = None
_retry_task: Optional[asyncio.Task] = None
_cleanup_task: Optional[asyncio.Task] = None  # 🔧 添加清理任务句柄
_is_running = False

# 解析器实例
_parsers: Dict[int, Any] = {}

# DB映射配置
_db_mappings: List[Dict[str, Any]] = []

# 设备状态DB配置 (DB3/DB7/DB11 - 原始字节数据，前端解析)
_device_status_db_configs: List[Dict[str, Any]] = []

# 历史重量缓存 (用于计算下料速度)
_weight_history: Dict[str, float] = {}

# ============================================================
# 最新数据缓存 (供 API 直接读取，避免查询数据库)
# ============================================================
import threading
_data_lock = threading.Lock()  # 🔧 添加数据访问锁
_latest_data: Dict[str, Any] = {}  # 最新的设备数据 {device_id: {...}}
_latest_timestamp: Optional[datetime] = None  # 最新数据时间戳

# ============================================================
# 设备状态位原始数据缓存 (供 API 返回给前端解析)
# ============================================================
# 格式: {"db3": {"db_number": 3, "db_name": "KilnState", "size": 148, "raw_data": bytes, "timestamp": str}, ...}
_device_status_raw: Dict[str, Dict[str, Any]] = {}

# ============================================================
# 批量写入缓存
# ============================================================
_point_buffer: deque = deque(maxlen=1000)  # 最大缓存 1000 个点
_buffer_count = 0
_batch_size = 20  # 20 次轮询后批量写入（每次~46点，20次=920点<1000）

# ============================================================
# 统计信息
# ============================================================
_stats = {
    "total_polls": 0,
    "successful_writes": 0,
    "failed_writes": 0,
    "cached_points": 0,
    "retry_success": 0,
    "last_write_time": None,
    "last_retry_time": None,
    "status_errors": 0,  # 状态错误计数
}


# ------------------------------------------------------------
# 1. _load_db_mappings() - 加载DB映射配置
# ------------------------------------------------------------
def _load_db_mappings() -> List[Tuple[int, int]]:
    """从配置文件加载DB映射
    
    Returns:
        List[Tuple[int, int]]: [(db_number, total_size), ...]
    """
    global _db_mappings, _device_status_db_configs
    
    config_path = Path("configs/db_mappings.yaml")
    
    if not config_path.exists():
        print(f"⚠️  配置文件不存在: {config_path}，使用默认配置")
        return [(6, 554)]
    
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)
        
        _db_mappings = config.get('db_mappings', [])
        
        # 加载设备状态位配置 (DB3/DB7/DB11 - 原始数据，前端解析)
        device_status_config = config.get('device_status_config', {})
        if device_status_config.get('enabled', False):
            _device_status_db_configs = device_status_config.get('db_blocks', [])
            print(f"✅ 设备状态位监控已启用: {len(_device_status_db_configs)}个DB块")
            for db_cfg in _device_status_db_configs:
                print(f"   - DB{db_cfg['db_number']}: {db_cfg['db_name']} ({db_cfg['total_size']}字节)")
        
        # 加载轮询配置
        polling_config = config.get('polling_config', {})
        poll_interval = polling_config.get('poll_interval', 6)
        print(f"📊 轮询间隔: {poll_interval}秒")
        
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


# ============================================================
# 批量写入 & 本地缓存
# ============================================================
def _flush_buffer():
    """刷新缓存：批量写入 InfluxDB 或保存到本地"""
    global _buffer_count, _stats
    
    if len(_point_buffer) == 0:
        return
    
    # 转换为 Point 列表
    points = list(_point_buffer)
    _point_buffer.clear()
    _buffer_count = 0
    
    # 检查 InfluxDB 健康状态
    healthy, msg = check_influx_health()
    
    if healthy:
        # 尝试写入 InfluxDB
        success, err = write_points_batch(points)
        
        if success:
            _stats["successful_writes"] += len(points)
            _stats["last_write_time"] = beijing_isoformat()
            if not settings.verbose_polling_log:
                print(f"✅ 批量写入 {len(points)} 个数据点到 InfluxDB")
        else:
            print(f"❌ InfluxDB 写入失败: {err}，转存到本地缓存")
            _save_to_local_cache(points)
    else:
        # InfluxDB 不可用，保存到本地
        print(f"⚠️ InfluxDB 不可用 ({msg})，数据写入本地缓存")
        _save_to_local_cache(points)


def _save_to_local_cache(points: List):
    """保存数据点到本地 SQLite 缓存"""
    global _stats
    
    cache = get_local_cache()
    cached_points = []
    
    for point in points:
        # 提取 Point 对象的信息
        cached_point = CachedPoint(
            measurement=point._name,
            tags={k: v for k, v in point._tags.items()},
            fields={k: v for k, v in point._fields.items()},
            timestamp=point._time.isoformat() if point._time else beijing_isoformat()
        )
        cached_points.append(cached_point)
    
    saved_count = cache.save_points(cached_points)
    _stats["cached_points"] += saved_count
    _stats["failed_writes"] += len(points)
    
    print(f"💾 已保存 {saved_count} 个数据点到本地缓存")


# ============================================================
# 缓存重试任务
# ============================================================
async def _retry_cached_data():
    """定期重试本地缓存的数据"""
    global _stats
    
    cache = get_local_cache()
    retry_interval = 60  # 每 60 秒重试一次
    
    while _is_running:
        await asyncio.sleep(retry_interval)
        
        # 检查 InfluxDB 健康状态
        healthy, _ = check_influx_health()
        if not healthy:
            continue
        
        # 获取待重试数据
        pending = cache.get_pending_points(limit=100, max_retry=5)
        
        if not pending:
            continue
        
        print(f"🔄 开始重试 {len(pending)} 条缓存数据...")
        
        # 重新构建 Point 对象
        points = []
        ids = []
        
        for point_id, cached_point in pending:
            try:
                point = build_point(
                    cached_point.measurement,
                    cached_point.tags,
                    cached_point.fields,
                    datetime.fromisoformat(cached_point.timestamp)
                )
                if point:
                    points.append(point)
                    ids.append(point_id)
            except Exception as e:
                print(f"⚠️ 重建 Point 失败: {e}")
        
        if not points:
            continue
        
        # 批量写入
        success, err = write_points_batch(points)
        
        if success:
            cache.mark_success(ids)
            _stats["retry_success"] += len(points)
            _stats["last_retry_time"] = beijing_isoformat()
            print(f"✅ 重试成功: {len(points)} 条数据已写入 InfluxDB")
        else:
            cache.mark_retry(ids)
            print(f"❌ 重试失败: {err}")


# ============================================================
# 🔧 定期清理任务（每小时执行）
# ============================================================
async def _periodic_cleanup():
    """定期清理过期缓存和执行内存维护"""
    cleanup_interval = 3600  # 每小时清理一次
    
    while _is_running:
        await asyncio.sleep(cleanup_interval)
        
        try:
            # 清理本地缓存中超过7天的失败记录
            cache = get_local_cache()
            cache.cleanup_old(days=7)
            
            # 记录当前内存使用情况（仅用于调试）
            import gc
            gc.collect()  # 强制垃圾回收
            
            print(f"🧹 定期清理完成 | 设备缓存: {len(_latest_data)} | 重量历史: {len(_weight_history)}")
        except Exception as e:
            print(f"⚠️ 定期清理任务异常: {e}")


# ============================================================
# 主轮询循环
# ============================================================
async def _poll_data():
    """轮询DB块数据并写入InfluxDB（动态配置）
    
    支持两种模式:
    - 正常模式: 从真实PLC读取数据
    - Mock模式: 使用MockDataGenerator生成模拟数据
    """
    global _buffer_count, _stats, _latest_data, _latest_timestamp, _mock_generator, _device_status_raw
    
    # 从配置文件加载DB块配置
    db_configs = _load_db_mappings()
    
    poll_count = 0
    
    # 根据模式初始化数据源
    if settings.mock_mode:
        # Mock模式：使用模拟数据生成器
        import sys
        sys.path.insert(0, str(Path(__file__).parent.parent.parent / "tests" / "mock"))
        from mock_data_generator import MockDataGenerator
        _mock_generator = MockDataGenerator()
        print("🎭 Mock模式已启用 - 使用模拟数据")
        plc = None
    else:
        # 正常模式：使用真实PLC
        plc = get_plc_manager()
    
    while _is_running:
        poll_count += 1
        timestamp = now_beijing()
        _stats["total_polls"] += 1
        
        try:
            # ============================================================
            # Step 1: 读取设备状态位 DB3/DB7/DB11 (原始数据，前端解析)
            # ============================================================
            if settings.mock_mode and _mock_generator:
                # Mock模式：从生成器获取状态位数据
                mock_db_data = _mock_generator.generate_all_db_data()
                
                # 更新设备状态位原始数据缓存
                for db_cfg in _device_status_db_configs:
                    db_num = db_cfg['db_number']
                    db_name = db_cfg['db_name']
                    db_size = db_cfg['total_size']
                    
                    raw_data = mock_db_data.get(db_num)
                    if raw_data:
                        _device_status_raw[f"db{db_num}"] = {
                            "db_number": db_num,
                            "db_name": db_name,
                            "size": db_size,
                            "raw_data": raw_data[:db_size] if len(raw_data) >= db_size else raw_data,
                            "timestamp": timestamp.isoformat()
                        }
                    
                # 保存mock_db_data供Step 2使用（避免重复生成）
                _current_mock_db_data = mock_db_data
            elif not settings.mock_mode and plc:
                # 正常模式：从PLC读取设备状态位 DB3/DB7/DB11
                for db_cfg in _device_status_db_configs:
                    db_num = db_cfg['db_number']
                    db_name = db_cfg['db_name']
                    db_size = db_cfg['total_size']
                    
                    success, raw_data, err = plc.read_db(db_num, 0, db_size)
                    if success and raw_data:
                        _device_status_raw[f"db{db_num}"] = {
                            "db_number": db_num,
                            "db_name": db_name,
                            "size": db_size,
                            "raw_data": raw_data,
                            "timestamp": timestamp.isoformat()
                        }
                    elif not success and poll_count % 10 == 1:
                        print(f"⚠️ 设备状态块 DB{db_num} 读取失败: {err}")
                
                _current_mock_db_data = None
            else:
                _current_mock_db_data = None
            
            # ============================================================
            # Step 2: 读取所有 DB 块数据
            # ============================================================
            all_devices = []
            
            if settings.mock_mode and _mock_generator:
                # Mock模式：使用Step 1已生成的数据（避免重复调用generate_all_db_data）
                mock_db_data = _current_mock_db_data if _current_mock_db_data else _mock_generator.generate_all_db_data()
                
                for db_num, size in db_configs:
                    db_data = mock_db_data.get(db_num)
                    if db_data is None:
                        continue
                    
                    # 解析设备数据
                    if db_num in _parsers:
                        devices = _parsers[db_num].parse_all(db_data)
                        all_devices.extend(devices)
                        
                        # 更新内存缓存
                        for device in devices:
                            _update_latest_data(device, db_num, timestamp)
            else:
                # 正常模式：从PLC读取数据
                for db_num, size in db_configs:
                    # 使用长连接读取
                    success, db_data, err = plc.read_db(db_num, 0, size)
                    
                    if not success:
                        print(f"❌ DB{db_num} 读取失败: {err}")
                        continue
                    
                    # 解析设备数据
                    if db_num in _parsers:
                        devices = _parsers[db_num].parse_all(db_data)
                        all_devices.extend(devices)
                        
                        # 更新内存缓存
                        for device in devices:
                            _update_latest_data(device, db_num, timestamp)
            
            # 更新时间戳
            _latest_timestamp = timestamp
            
            # 将数据加入写入缓冲区
            written_count = 0
            for device in all_devices:
                count = _add_device_to_buffer(device, all_devices[0].get('db_number', 8) if all_devices else 8, timestamp)
                written_count += count
            
            # 检查是否需要批量写入
            _buffer_count += 1
            
            # 缓冲区满告警 (达到80%容量)
            buffer_usage = len(_point_buffer) / 1000
            if buffer_usage > 0.8:
                print(f"⚠️ 缓冲区使用率过高: {buffer_usage*100:.1f}% (将触发批量写入)")
            
            # 触发批量写入：达到批次数或缓冲区>800个点
            if _buffer_count >= _batch_size or len(_point_buffer) >= 800:
                _flush_buffer()
            
            # 日志输出
            if settings.verbose_polling_log or poll_count % 10 == 0:
                cache_stats = get_local_cache().get_stats()
                print(f"📊 [poll #{poll_count}] "
                      f"设备: {len(all_devices)} | "
                      f"数据点: {written_count} | "
                      f"缓冲区={len(_point_buffer)}/{_batch_size} | "
                      f"待重试={cache_stats['pending_count']}")
        
        except Exception as e:
            print(f"❌ [poll #{poll_count}] 轮询异常: {e}")
            import traceback
            traceback.print_exc()
        
        # 使用运行时配置的轮询间隔（支持热更新）
        try:
            from app.routers.config import get_runtime_plc_config
            plc_config = get_runtime_plc_config()
            await asyncio.sleep(plc_config["poll_interval"])
        except:
            await asyncio.sleep(settings.plc_poll_interval)


# ============================================================
# 更新内存缓存（供 API 直接读取）
# ============================================================
def _update_latest_data(device_data: Dict[str, Any], db_number: int, timestamp: datetime):
    """更新内存缓存中的最新数据
    
    Args:
        device_data: 解析后的设备数据
        db_number: DB块号
        timestamp: 时间戳
    """
    global _latest_data, _weight_history
    
    device_id = device_data['device_id']
    device_type = device_data['device_type']
    
    # 转换所有模块数据
    modules_data = {}
    
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
            elif module_type == 'ElectricityMeter':
                # 电表模块：实时缓存包含三相电流（用于API返回）
                is_roller_kiln = device_type == 'roller_kiln'
                fields = converter.convert(raw_fields, is_roller_kiln=is_roller_kiln)
            else:
                fields = converter.convert(raw_fields)
        else:
            # 未知模块类型，直接提取原始值
            fields = {}
            for field_name, field_info in raw_fields.items():
                fields[field_name] = field_info['value']
        
        modules_data[module_tag] = {
            "module_type": module_type,
            "fields": fields
        }
    
    # 更新内存缓存
    with _data_lock:  # 🔧 线程安全写入
        _latest_data[device_id] = {
            "device_id": device_id,
            "device_type": device_type,
            "db_number": str(db_number),
            "timestamp": timestamp.isoformat(),
            "modules": modules_data
        }


def _update_status_cache(status_data: bytes, status_parser):
    """更新状态位内存缓存
    
    Args:
        status_data: 状态DB块的原始字节数据
        status_parser: 状态解析器实例
    """
    global _latest_status
    
    # 获取所有设备的状态
    success_list, error_list = status_parser.check_all_status(status_data)
    
    # 合并成功和错误列表，更新缓存
    all_status = success_list + error_list
    
    for status in all_status:
        device_id = status['device_id']
        _latest_status[device_id] = {
            "device_id": device_id,
            "device_type": status['device_type'],
            "description": status.get('description', ''),
            "done": status['done'],
            "busy": status['busy'],
            "error": status['error'],
            "status_code": status['status_code'],
            "timestamp": now_beijing().isoformat()
        }


# ============================================================
# 将设备数据加入写入缓冲区
# ============================================================
def _add_device_to_buffer(device_data: Dict[str, Any], db_number: int, timestamp: datetime) -> int:
    """将设备数据加入写入缓冲区
    
    Args:
        device_data: 解析后的设备数据
        db_number: DB块号
        timestamp: 时间戳
    
    Returns:
        添加的数据点数量
    """
    global _weight_history
    
    device_id = device_data['device_id']
    device_type = device_data['device_type']
    point_count = 0
    
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
            elif module_type == 'ElectricityMeter':
                # 电表模块：写入数据库时不存储三相电流
                is_roller_kiln = device_type == 'roller_kiln'
                fields = converter.convert_for_storage(raw_fields, is_roller_kiln=is_roller_kiln)
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
        
        # 构建 Point 对象
        point = build_point(
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
        
        if point:
            _point_buffer.append(point)
            point_count += 1
    
    return point_count


# ------------------------------------------------------------
# 3. start_polling() - 启动数据轮询任务
# ------------------------------------------------------------
async def start_polling():
    """启动数据轮询任务（从配置文件动态加载）"""
    global _polling_task, _retry_task, _is_running, _batch_size
    
    if _is_running:
        print("⚠️ 轮询服务已在运行")
        return
    
    # 加载DB映射配置
    _load_db_mappings()
    
    # 动态初始化解析器
    print("📦 初始化解析器:")
    _init_parsers()
    
    # 加载批量写入配置
    _batch_size = getattr(settings, 'batch_write_size', 30)
    
    _is_running = True
    
    # 根据模式启动
    if settings.mock_mode:
        print("🎭 Mock模式 - 跳过PLC连接")
    else:
        # 启动 PLC 长连接
        plc = get_plc_manager()
        success, err = plc.connect()
        if success:
            print(f"✅ PLC 长连接已建立")
        else:
            print(f"⚠️ PLC 连接失败: {err}，将在轮询时重试")
    
    # 启动轮询任务
    _polling_task = asyncio.create_task(_poll_data())
    _retry_task = asyncio.create_task(_retry_cached_data())
    _cleanup_task = asyncio.create_task(_periodic_cleanup())  # 🔧 启动定期清理任务
    
    mode_str = "Mock模式" if settings.mock_mode else "正常模式"
    print(f"✅ 轮询服务已启动 ({mode_str}, 间隔: {settings.plc_poll_interval}s, 批量: {_batch_size}次)")


# ------------------------------------------------------------
# 4. stop_polling() - 停止数据轮询任务
# ------------------------------------------------------------
async def stop_polling():
    """停止数据轮询任务"""
    global _polling_task, _retry_task, _cleanup_task, _is_running
    
    _is_running = False
    
    # 刷新缓冲区
    print("⏳ 正在刷新缓冲区...")
    _flush_buffer()
    
    # 🔧 取消所有任务，添加超时保护
    for task_name, task in [("polling", _polling_task), ("retry", _retry_task), ("cleanup", _cleanup_task)]:
        if task:
            task.cancel()
            try:
                await asyncio.wait_for(task, timeout=5.0)  # 🔧 最多等待5秒
            except asyncio.CancelledError:
                pass
            except asyncio.TimeoutError:
                print(f"⚠️ {task_name} 任务取消超时，强制终止")
    
    _polling_task = None
    _retry_task = None
    _cleanup_task = None  # 🔧 重置清理任务句柄
    
    # 断开 PLC 长连接
    plc = get_plc_manager()
    plc.disconnect()
    
    print("⏹️ 轮询服务已停止")


# ============================================================
# API 查询函数（供 Router 使用）
# ============================================================
def get_latest_data() -> Dict[str, Any]:
    """获取所有设备的最新数据（从内存缓存）
    
    Returns:
        {device_id: {device_id, device_type, timestamp, modules: {...}}}
    """
    with _data_lock:  # 🔧 线程安全读取
        return _latest_data.copy()


def get_latest_device_data(device_id: str) -> Optional[Dict[str, Any]]:
    """获取单个设备的最新数据（从内存缓存）
    
    Args:
        device_id: 设备ID
    
    Returns:
        设备数据或 None
    """
    with _data_lock:  # 🔧 线程安全读取
        return _latest_data.get(device_id)


def get_latest_devices_by_type(device_type: str) -> List[Dict[str, Any]]:
    """获取指定类型的所有设备最新数据
    
    Args:
        device_type: 设备类型 (short_hopper, long_hopper, etc.)
    
    Returns:
        设备数据列表
    """
    with _data_lock:  # 🔧 线程安全读取
        return [
            data for data in _latest_data.values()
            if data.get('device_type') == device_type
        ]


def get_device_status_raw() -> Dict[str, Dict[str, Any]]:
    """获取设备状态位的原始字节数据 (供前端解析)
    
    后端只负责读取和缓存原始数据，前端根据配置文件解析具体状态
    
    Returns:
        {
            "db3": {"db_number": 3, "db_name": "KilnState", "size": 148, "raw_data": bytes, "timestamp": str},
            "db7": {"db_number": 7, "db_name": "RollerKilnState", "size": 72, "raw_data": bytes, "timestamp": str},
            "db11": {"db_number": 11, "db_name": "SCRDeviceState", "size": 40, "raw_data": bytes, "timestamp": str}
        }
    """
    return _device_status_raw.copy()

def get_latest_timestamp() -> Optional[str]:
    """获取最新数据的时间戳"""
    return _latest_timestamp.isoformat() if _latest_timestamp else None


def is_polling_running() -> bool:
    """检查轮询服务是否在运行"""
    return _is_running


def get_polling_stats() -> Dict[str, Any]:
    """获取轮询统计信息"""
    cache_stats = get_local_cache().get_stats()
    plc_status = get_plc_manager().get_status()
    
    return {
        **_stats,
        "buffer_size": len(_point_buffer),
        "batch_size": _batch_size,
        "devices_in_cache": len(_latest_data),
        "latest_timestamp": get_latest_timestamp(),
        "cache_stats": cache_stats,
        "plc_status": plc_status
    }
