# ============================================================
# 文件说明: polling_service.py - 优化版数据轮询服务
# ============================================================
# 优化点:
#   1. PLC 长连接 (避免频繁连接/断开)
#   2. 批量写入 (动态配置的.env次轮询缓存后批量写入)
#   3. 本地降级缓存 (InfluxDB 故障时写入 SQLite)
#   4. 自动重试机制 (缓存数据自动重试)
#   5. 内存缓存 (供 API 直接读取最新数据)
#   6. Mock模式支持 (使用模拟数据替代真实PLC)
# ============================================================

import asyncio
import logging
import yaml
from pathlib import Path
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any, List, Tuple
from collections import deque

from config import get_settings

logger = logging.getLogger(__name__)
from app.tools.timezone_tools import now_beijing, beijing_isoformat
from app.core.influxdb import build_point, write_points_batch, check_influx_health
from app.core.local_cache import get_local_cache, CachedPoint
from app.plc.plc_manager import get_plc_manager
from app.plc.parser_hopper import HopperParser
from app.plc.parser_roller_kiln import RollerKilnParser
from app.plc.parser_scr_fan import SCRFanParser
from app.tools import get_converter, CONVERTER_MAP
from app.services.roller_kiln_aggregator import get_aggregator
from app.services.alarm_checker import check_device_alarm

settings = get_settings()

# Mock数据生成器（延迟导入，仅在mock模式下使用）
_mock_generator = None

# 轮询任务句柄
_polling_task: Optional[asyncio.Task] = None
_realtime_polling_task: Optional[asyncio.Task] = None
_status_polling_task: Optional[asyncio.Task] = None
_retry_task: Optional[asyncio.Task] = None
_cleanup_task: Optional[asyncio.Task] = None  # [FIX] 添加清理任务句柄
_is_running = False

# 解析器实例
_parsers: Dict[int, Any] = {}

# DB映射配置
_db_mappings: List[Dict[str, Any]] = []

# 设备状态DB配置 (DB3/DB7/DB11 - 原始字节数据，前端解析)
_device_status_db_configs: List[Dict[str, Any]] = []

# 投料分析服务 (v5.0 滑动窗口, 由 push_sample 驱动)
from app.services.feeding_analysis_service import feeding_analysis_service

# ============================================================
# 最新数据缓存 (供 API 直接读取，避免查询数据库)
# ============================================================
import threading
_data_lock = threading.Lock()  # [FIX] 添加数据访问锁
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
_batch_size = 10  # 在 start_polling() 中由 settings.batch_write_size 初始化
                   # 每次轮询约47个数据点，10次批量写入约470点

# [FIX] [NEW] 后台写入任务控制
_write_queue: asyncio.Queue = None  # 写入队列（异步）
_write_task: Optional[asyncio.Task] = None  # 后台写入任务
_write_in_progress = False  # 是否正在写入
_mock_data_lock: Optional[asyncio.Lock] = None
_latest_mock_db_data: Optional[Dict[int, bytes]] = None

# WebSocket 事件通知: 两个独立事件，分别对应两个轮询频道
_realtime_updated_event: Optional[asyncio.Event] = None   # DB8/9/10 有新数据
_status_updated_event: Optional[asyncio.Event] = None     # DB3/7/11 有新数据


def get_realtime_updated_event() -> asyncio.Event:
    """实时数据更新事件 (realtime 频道的推送任务监听)"""
    global _realtime_updated_event
    if _realtime_updated_event is None:
        _realtime_updated_event = asyncio.Event()
    return _realtime_updated_event


def get_status_updated_event() -> asyncio.Event:
    """设备状态更新事件 (device_status 频道的推送任务监听)"""
    global _status_updated_event
    if _status_updated_event is None:
        _status_updated_event = asyncio.Event()
    return _status_updated_event


def get_data_updated_event() -> asyncio.Event:
    """兼容旧调用: 返回 realtime 事件（旧 _poll_data 路径使用）"""
    return get_realtime_updated_event()


# ============================================================
# 统计信息
# ============================================================
_stats = {
    "total_polls": 0,
    "realtime_polls": 0,
    "status_polls": 0,
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
    
    from config import get_runtime_base_dir
    config_path = get_runtime_base_dir() / "configs" / "db_mappings.yaml"
    
    if not config_path.exists():
        print(f"[WARN]  配置文件不存在: {config_path}，使用默认配置")
        return [(6, 554)]
    
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)
        
        _db_mappings = config.get('db_mappings', [])
        
        # 加载设备状态位配置 (DB3/DB7/DB11 - 原始数据，前端解析)
        device_status_config = config.get('device_status_config', {})
        if device_status_config.get('enabled', False):
            _device_status_db_configs = device_status_config.get('db_blocks', [])
            print(f"[INFO] 设备状态位监控已启用: {len(_device_status_db_configs)}个DB块")
            for db_cfg in _device_status_db_configs:
                print(f"   - DB{db_cfg['db_number']}: {db_cfg['db_name']} ({db_cfg['total_size']}字节)")
        
        # 加载轮询配置
        polling_config = config.get('polling_config', {})
        poll_interval = float(polling_config.get('poll_interval', 6))
        realtime_poll_interval = float(polling_config.get('realtime_poll_interval', poll_interval))
        status_poll_interval = float(polling_config.get('status_poll_interval', poll_interval))
        print(f"[DATA] 轮询间隔配置: realtime={realtime_poll_interval}s, status={status_poll_interval}s, 兼容poll_interval={poll_interval}s")
        
        # 只返回启用的DB块配置
        enabled_configs = [
            (mapping['db_number'], mapping['total_size'])
            for mapping in _db_mappings
            if mapping.get('enabled', True)
        ]
        
        print(f"[INFO] 加载DB映射配置: {len(enabled_configs)}个DB块")
        for db_num, size in enabled_configs:
            mapping = next(m for m in _db_mappings if m['db_number'] == db_num)
            print(f"   - DB{db_num}: {mapping['db_name']} ({size}字节)")
        
        return enabled_configs
    
    except Exception as e:
        print(f"[ERROR] 加载DB映射配置失败: {e}，使用默认配置")
        return [(6, 554)]


async def _next_mock_db_data(*, advance: bool, interval_s: float) -> Dict[int, bytes]:
    """线程安全获取 Mock DB 数据

    Args:
        advance: True=推进一帧（仅实时轮询调用），False=读取当前快照（状态轮询调用）
        interval_s: 推进帧使用的时间间隔（秒）
    """
    global _mock_generator, _mock_data_lock, _latest_mock_db_data

    if _mock_generator is None:
        from app.services.mock_service import MockService
        _mock_generator = MockService()

    if _mock_data_lock is None:
        _mock_data_lock = asyncio.Lock()

    async with _mock_data_lock:
        if advance:
            _latest_mock_db_data = _mock_generator.generate_all_db_data(
                advance=True,
                poll_interval_s=interval_s,
            )
            return _latest_mock_db_data

        if _latest_mock_db_data is None:
            _latest_mock_db_data = _mock_generator.generate_all_db_data(
                advance=True,
                poll_interval_s=interval_s,
            )
        return _latest_mock_db_data


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
            print(f"   [INFO] DB{db_number} -> {parser_class_name}")
        else:
            print(f"   [WARN]  未知的解析器类: {parser_class_name}")


# ============================================================
# 批量写入 & 本地缓存
# ============================================================
def _flush_buffer():
    """刷新缓存：将数据放入异步写入队列（不阻塞）"""
    global _buffer_count, _write_queue
    
    if len(_point_buffer) == 0:
        return
    
    # 转换为 Point 列表
    points = list(_point_buffer)
    _point_buffer.clear()
    _buffer_count = 0
    
    # [FIX] [CRITICAL] 将数据放入异步队列，不阻塞当前线程
    if _write_queue is not None:
        try:
            _write_queue.put_nowait(points)
            print(f"[SEND] 已将 {len(points)} 个数据点加入写入队列")
        except asyncio.QueueFull:
            print(f"[WARN] 写入队列已满，数据转存到本地缓存")
            _save_to_local_cache(points)
    else:
        # 队列未初始化，使用同步写入（降级）
        _sync_write_to_influx(points)


def _sync_write_to_influx(points: List):
    """同步写入 InfluxDB（降级模式）"""
    global _stats
    
    healthy, msg = check_influx_health()
    
    if healthy:
        success, err = write_points_batch(points)
        if success:
            _stats["successful_writes"] += len(points)
            _stats["last_write_time"] = beijing_isoformat()
            print(f"[INFO] 批量写入 {len(points)} 个数据点到 InfluxDB")
        else:
            print(f"[ERROR] InfluxDB 写入失败: {err}，转存到本地缓存")
            _save_to_local_cache(points)
    else:
        print(f"[WARN] InfluxDB 不可用 ({msg})，数据写入本地缓存")
        _save_to_local_cache(points)


async def _background_writer():
    """[FIX] [NEW] 后台写入任务 - 异步处理写入队列，不阻塞 API"""
    global _stats, _write_in_progress, _write_queue
    
    print("[START] 后台写入任务已启动")
    
    while _is_running:
        try:
            # 等待队列中的数据（最多等待 1 秒，允许检查 _is_running）
            try:
                points = await asyncio.wait_for(_write_queue.get(), timeout=1.0)
            except asyncio.TimeoutError:
                continue
            
            if not points:
                continue
            
            _write_in_progress = True
            
            # 检查 InfluxDB 健康状态
            healthy, msg = check_influx_health()
            
            if healthy:
                # 尝试写入 InfluxDB
                success, err = write_points_batch(points)
                
                if success:
                    _stats["successful_writes"] += len(points)
                    _stats["last_write_time"] = beijing_isoformat()
                    print(f"[INFO] [后台] 批量写入 {len(points)} 个数据点到 InfluxDB")
                else:
                    print(f"[ERROR] [后台] InfluxDB 写入失败: {err}，转存到本地缓存")
                    _save_to_local_cache(points)
            else:
                # InfluxDB 不可用，保存到本地
                print(f"[WARN] [后台] InfluxDB 不可用 ({msg})，数据写入本地缓存")
                _save_to_local_cache(points)
            
            _write_in_progress = False
            _write_queue.task_done()
            
        except asyncio.CancelledError:
            print("[STOP] 后台写入任务已取消")
            break
        except Exception as e:
            print(f"[ERROR] [后台] 写入任务异常: {e}")
            _write_in_progress = False
            await asyncio.sleep(1)  # 出错后等待 1 秒再继续
    
    print("[STOP] 后台写入任务已停止")


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
    
    print(f"[CACHE] 已保存 {saved_count} 个数据点到本地缓存")


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
        
        print(f"[RETRY] 开始重试 {len(pending)} 条缓存数据...")
        
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
                print(f"[WARN] 重建 Point 失败: {e}")
        
        if not points:
            continue
        
        # 批量写入
        success, err = write_points_batch(points)
        
        if success:
            cache.mark_success(ids)
            _stats["retry_success"] += len(points)
            _stats["last_retry_time"] = beijing_isoformat()
            print(f"[INFO] 重试成功: {len(points)} 条数据已写入 InfluxDB")
        else:
            cache.mark_retry(ids)
            print(f"[ERROR] 重试失败: {err}")


# ============================================================
# [FIX] 定期清理任务（每小时执行）
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
            
            print(f"[CLEANUP] 定期清理完成 | 设备缓存: {len(_latest_data)}")
        except Exception as e:
            print(f"[WARN] 定期清理任务异常: {e}")




async def _poll_realtime_data_loop():
    """轮询实时数据 DB8/DB9/DB10（独立任务）"""
    global _stats

    db_configs = _load_db_mappings()

    poll_count = 0

    plc = None if settings.mock_mode else get_plc_manager()

    while _is_running:
        poll_count += 1
        _stats["total_polls"] += 1
        _stats["realtime_polls"] += 1

        timestamp = now_beijing()
        realtime_interval = float(settings.realtime_poll_interval)
        try:
            from app.routers.config import get_runtime_plc_config
            plc_config = get_runtime_plc_config()
            realtime_interval = float(
                plc_config.get("realtime_poll_interval", plc_config.get("poll_interval", settings.realtime_poll_interval))
            )
        except Exception:
            pass

        try:
            all_devices = []

            if settings.mock_mode:
                mock_db_data = await _next_mock_db_data(advance=True, interval_s=realtime_interval)
                for db_num, size in db_configs:
                    db_data = mock_db_data.get(db_num)
                    if db_data is None:
                        continue

                    if db_num in _parsers:
                        devices = _parsers[db_num].parse_all(db_data)
                        all_devices.extend(devices)
                        for device in devices:
                            _update_latest_data(device, db_num, timestamp)
            else:
                for db_num, size in db_configs:
                    success, db_data, err = plc.read_db(db_num, 0, size)
                    if not success:
                        print(f"[ERROR] DB{db_num} 读取失败: {err}")
                        continue

                    if db_num in _parsers:
                        devices = _parsers[db_num].parse_all(db_data)
                        all_devices.extend(devices)
                        for device in devices:
                            _update_latest_data(device, db_num, timestamp)

            global _latest_timestamp, _buffer_count
            _latest_timestamp = timestamp

            # [TEST] 触发WebSocket推送事件
            get_realtime_updated_event().set()
            logger.info(f"[TEST][POLL→WS] 实时数据轮询完成 | 设备数={len(all_devices)} | 触发WebSocket推送事件")

            written_count = 0
            for device in all_devices:
                count = _add_device_to_buffer(
                    device,
                    all_devices[0].get('db_number', 8) if all_devices else 8,
                    timestamp,
                )
                written_count += count

                if device.get('device_id') == 'roller_kiln_1':
                    aggregator = get_aggregator()

                    total_point = aggregator.aggregate_zones(device, timestamp)
                    if total_point:
                        _point_buffer.append(total_point)
                        written_count += 1

                    total_cache = aggregator.aggregate_zones_for_cache(device, timestamp)
                    if total_cache:
                        with _data_lock:
                            _latest_data['roller_kiln_total'] = total_cache

            _buffer_count += 1

            buffer_usage = len(_point_buffer) / 1000
            if buffer_usage > 0.5:
                print(f"[WARN] 缓冲区使用率过高: {buffer_usage*100:.1f}% (将触发批量写入)")

            if _buffer_count >= _batch_size or len(_point_buffer) >= 500:
                _flush_buffer()

            if settings.verbose_polling_log or poll_count % 10 == 0:
                cache_stats = get_local_cache().get_stats()
                print(f"[DATA][realtime][poll #{poll_count}] "
                      f"设备: {len(all_devices)} | "
                      f"数据点: {written_count} | "
                      f"批次进度={_buffer_count}/{_batch_size}次 | "
                      f"缓冲点={len(_point_buffer)} | "
                      f"待重试={cache_stats['pending_count']}")

        except Exception as e:
            print(f"[ERROR][realtime][poll #{poll_count}] 轮询异常: {e}")
            import traceback
            traceback.print_exc()

        await asyncio.sleep(realtime_interval)


async def _poll_device_status_loop():
    """轮询设备状态位 DB3/DB7/DB11（独立任务）"""
    global _stats, _device_status_raw

    poll_count = 0

    plc = None if settings.mock_mode else get_plc_manager()

    while _is_running:
        poll_count += 1
        _stats["status_polls"] += 1

        timestamp = now_beijing()
        status_interval = float(settings.status_poll_interval)
        try:
            from app.routers.config import get_runtime_plc_config
            plc_config = get_runtime_plc_config()
            status_interval = float(
                plc_config.get("status_poll_interval", plc_config.get("poll_interval", settings.status_poll_interval))
            )
        except Exception:
            pass

        try:
            if settings.mock_mode:
                mock_db_data = await _next_mock_db_data(advance=False, interval_s=status_interval)
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
                            "timestamp": timestamp.isoformat(),
                        }
            elif not settings.mock_mode and plc:
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
                            "timestamp": timestamp.isoformat(),
                        }
                    elif not success and poll_count % 10 == 1:
                        print(f"[WARN] 设备状态块 DB{db_num} 读取失败: {err}")

            get_status_updated_event().set()

            if settings.verbose_polling_log or poll_count % 20 == 0:
                print(f"[DATA][status][poll #{poll_count}] 状态块缓存: {len(_device_status_raw)}")

        except Exception as e:
            _stats["status_errors"] += 1
            print(f"[ERROR][status][poll #{poll_count}] 状态位轮询异常: {e}")
            import traceback
            traceback.print_exc()

        await asyncio.sleep(status_interval)


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
    global _latest_data
    
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
            
            if module_type == 'WeighSensor':
                # 称重模块: 只做重量转换, feed_rate 由 feeding_analysis_service 负责
                fields = converter.convert(raw_fields)
                
                # 推送到投料分析服务 (驱动滑动窗口 + 上料检测)
                weight_val = fields.get('weight', 0.0)
                if weight_val > 0 and "no_hopper" not in device_id:
                    feeding_analysis_service.push_sample(device_id, weight_val, timestamp)
                
                # 将 feeding_analysis_service 的显示下料速度注入到 fields 中
                # 供 WS 推送和 API 使用, 保持前端数据结构兼容
                if "no_hopper" not in device_id:
                    fields["feed_rate"] = feeding_analysis_service.get_display_feed_rate(device_id)
            elif module_type == 'ElectricityMeter':
                # [FIX] 电表模块：实时缓存包含三相电流（用于API返回）
                is_roller_kiln = device_type == 'roller_kiln'
                is_scr = device_type == 'scr'  # [FIX] 检测是否为SCR设备（氨水泵）
                fields = converter.convert(raw_fields, is_roller_kiln=is_roller_kiln, is_scr=is_scr)
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
    with _data_lock:  # [FIX] 线程安全写入
        _latest_data[device_id] = {
            "device_id": device_id,
            "device_type": device_type,
            "db_number": str(db_number),
            "timestamp": timestamp.isoformat(),
            "modules": modules_data
        }

    # 报警检查 (在锁外执行，避免 I/O 阻塞)
    check_device_alarm(device_id, device_type, modules_data, timestamp)


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
    global _point_buffer
    
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
            
            if module_type == 'WeighSensor':
                # 称重模块: 只做重量转换 (feed_rate 不存 sensor_data)
                fields = converter.convert(raw_fields)
            elif module_type == 'ElectricityMeter':
                # [FIX] 电表模块：写入数据库时不存储三相电流
                is_roller_kiln = device_type == 'roller_kiln'
                is_scr = device_type == 'scr'  # [FIX] 检测是否为SCR设备
                fields = converter.convert_for_storage(raw_fields, is_roller_kiln=is_roller_kiln, is_scr=is_scr)
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
    global _polling_task, _realtime_polling_task, _status_polling_task, _retry_task, _is_running, _batch_size, _write_queue, _write_task, _mock_data_lock, _latest_mock_db_data
    
    if _is_running:
        print("[WARN] 轮询服务已在运行")
        return
    
    # 加载DB映射配置
    _load_db_mappings()
    
    # 动态初始化解析器
    print("[POLL][INIT] 初始化解析器")
    _init_parsers()
    
    # 加载批量写入配置
    configured_batch_size = int(getattr(settings, 'batch_write_size', 10))
    _batch_size = max(1, min(100, configured_batch_size))
    
    _is_running = True
    _mock_data_lock = asyncio.Lock()
    _latest_mock_db_data = None
    
    # [FIX] [NEW] 初始化异步写入队列（最多缓存 10 批数据）
    _write_queue = asyncio.Queue(maxsize=10)
    
    # 根据模式启动
    if settings.mock_mode:
        print("[模拟] Mock模式 - 跳过PLC连接")
    else:
        # 启动 PLC 长连接
        plc = get_plc_manager()
        success, err = plc.connect()
        if success:
            print(f"[INFO] PLC 长连接已建立")
        else:
            print(f"[WARN] PLC 连接失败: {err}，将在轮询时重试")
    
    # [FIX] [NEW] 启动后台写入任务（关键：不阻塞 API）
    _write_task = asyncio.create_task(_background_writer())
    
    # 启动轮询任务（双任务：实时数据 + 状态位）
    _realtime_polling_task = asyncio.create_task(_poll_realtime_data_loop())
    _status_polling_task = asyncio.create_task(_poll_device_status_loop())
    _polling_task = _realtime_polling_task
    _retry_task = asyncio.create_task(_retry_cached_data())
    _cleanup_task = asyncio.create_task(_periodic_cleanup())  # [FIX] 启动定期清理任务
    
    mode_str = "Mock模式" if settings.mock_mode else "正常模式"
    print(f"[INFO] 轮询服务已启动 ({mode_str}, 实时间隔: {settings.realtime_poll_interval}s, 状态间隔: {settings.status_poll_interval}s, 批量: {_batch_size}次)")
    print(f"[START] 后台写入模式已启用 - API 请求不会被阻塞")


# ------------------------------------------------------------
# 4. stop_polling() - 停止数据轮询任务
# ------------------------------------------------------------
async def stop_polling():
    """停止数据轮询任务"""
    global _polling_task, _realtime_polling_task, _status_polling_task, _retry_task, _cleanup_task, _write_task, _is_running, _write_queue
    
    _is_running = False
    
    # 刷新缓冲区（将剩余数据放入队列）
    print("[WAIT] 正在刷新缓冲区...")
    _flush_buffer()
    
    # [FIX] [NEW] 等待写入队列处理完成（最多等待 10 秒）
    if _write_queue is not None:
        try:
            await asyncio.wait_for(_write_queue.join(), timeout=10.0)
            print("[INFO] 写入队列已清空")
        except asyncio.TimeoutError:
            print("[WARN] 写入队列清空超时，部分数据可能丢失")
    
    # [FIX] 取消所有任务，添加超时保护
    tasks_to_cancel = [
        ("realtime_polling", _realtime_polling_task),
        ("status_polling", _status_polling_task),
        ("retry", _retry_task), 
        ("cleanup", _cleanup_task),
        ("writer", _write_task)  # [FIX] [NEW] 后台写入任务
    ]
    
    for task_name, task in tasks_to_cancel:
        if task:
            task.cancel()
            try:
                await asyncio.wait_for(task, timeout=5.0)  # [FIX] 最多等待5秒
            except asyncio.CancelledError:
                pass
            except asyncio.TimeoutError:
                print(f"[WARN] {task_name} 任务取消超时，强制终止")
    
    _polling_task = None
    _realtime_polling_task = None
    _status_polling_task = None
    _retry_task = None
    _cleanup_task = None
    _write_task = None  # [FIX] [NEW] 重置写入任务句柄
    _write_queue = None  # [FIX] [NEW] 重置写入队列
    
    # 断开 PLC 长连接
    plc = get_plc_manager()
    plc.disconnect()
    
    print("[POLL][STOP] 轮询服务已停止")


# ============================================================
# API 查询函数（供 Router 使用）
# ============================================================
def get_latest_data() -> Dict[str, Any]:
    """获取所有设备的最新数据（从内存缓存）
    
    Returns:
        {device_id: {device_id, device_type, timestamp, modules: {...}}}
    """
    with _data_lock:  # [FIX] 线程安全读取
        return _latest_data.copy()


def get_latest_device_data(device_id: str) -> Optional[Dict[str, Any]]:
    """获取单个设备的最新数据（从内存缓存）
    
    Args:
        device_id: 设备ID
    
    Returns:
        设备数据或 None
    """
    with _data_lock:  # [FIX] 线程安全读取
        return _latest_data.get(device_id)


def get_latest_devices_by_type(device_type: str) -> List[Dict[str, Any]]:
    """获取指定类型的所有设备最新数据
    
    Args:
        device_type: 设备类型 (short_hopper, long_hopper, etc.)
    
    Returns:
        设备数据列表
    """
    with _data_lock:  # [FIX] 线程安全读取
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

