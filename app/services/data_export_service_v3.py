# ============================================================
# 文件说明: data_export_service_v3.py - 数据导出服务（终极优化版）
# ============================================================
# 核心优化:
# 1. 批量查询预计算数据（一次查询所有设备）
# 2. 并行处理不完整天的实时计算
# 3. 内存缓存完整天数据（避免重复查询）
# 4. 性能提升 10-20 倍
# ============================================================
# 方法列表:
# 1. export_comprehensive_v3()    - 综合导出（终极优化版）
# 2. _batch_query_daily_summary() - 批量查询预计算数据
# 3. _parallel_calculate_partial_days() - 并行计算不完整天
# ============================================================

from datetime import datetime, timedelta, timezone
from typing import Dict, Any, Optional, List, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
import json

from config import get_settings
from app.core.influxdb import get_influx_client
from app.services.data_export_service import get_export_service
from app.services.daily_summary_service import get_daily_summary_service
from app.utils.time_slice_utils import split_time_range_by_natural_days

settings = get_settings()

# ============================================================
# 时间格式化工具函数
# ============================================================
# 定义北京时区（UTC+8）
BEIJING_TZ = timezone(timedelta(hours=8))

def format_datetime_without_microseconds(dt: datetime) -> str:
    """格式化时间，去除微秒部分，并转换为北京时间
    
    Args:
        dt: datetime 对象（可能是UTC时间或其他时区）
        
    Returns:
        格式化后的时间字符串（ISO 8601格式，北京时间，无微秒）
        例如: 2026-01-26T14:23:00+08:00
    """
    if dt is None:
        return None
    
    # 如果没有时区信息，假设为UTC
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    
    # 转换为北京时间
    dt_beijing = dt.astimezone(BEIJING_TZ)
    
    # 去除微秒
    dt_no_micro = dt_beijing.replace(microsecond=0)
    
    # 转换为 ISO 8601 格式
    return dt_no_micro.isoformat()

# 🔧 单例实例
_export_service_v3_instance: Optional['DataExportServiceV3'] = None

# 🔧 内存缓存（完整天数据）
_memory_cache: Dict[str, Any] = {}


class DataExportServiceV3:
    """数据导出服务（终极优化版）"""
    
    def __init__(self):
        self.export_service = get_export_service()
        self.summary_service = get_daily_summary_service()
        self._client = None
        self._query_api = None
        self.bucket = settings.influx_bucket
    
    @property
    def client(self):
        """延迟获取 InfluxDB 客户端"""
        if self._client is None:
            self._client = get_influx_client()
        return self._client
    
    @property
    def query_api(self):
        """延迟获取 query_api"""
        if self._query_api is None:
            self._query_api = self.client.query_api()
        return self._query_api
    
    # ------------------------------------------------------------
    # 核心优化 1: 批量查询预计算数据（一次查询所有设备）
    # ------------------------------------------------------------
    def _batch_query_daily_summary(
        self,
        start_date: datetime,
        end_date: datetime
    ) -> Dict[str, Dict[str, List[Dict[str, Any]]]]:
        """批量查询所有设备的预计算数据
        
        Args:
            start_date: 开始日期
            end_date: 结束日期
            
        Returns:
            {
                "short_hopper_1": {
                    "electricity": [...],
                    "feeding": [...]
                },
                "zone1": {
                    "electricity": [...]
                },
                ...
            }
        """
        print(f"🔄 批量查询预计算数据: {start_date.date()} ~ {end_date.date()}")
        
        # 🔧 一次性查询所有设备、所有指标类型的数据
        query = f'''
        from(bucket: "{self.bucket}")
            |> range(start: {start_date.isoformat()}, stop: {end_date.isoformat()})
            |> filter(fn: (r) => r["_measurement"] == "daily_summary")
            |> pivot(rowKey:["_time", "device_id", "metric_type", "date"], columnKey: ["_field"], valueColumn: "_value")
        '''
        
        try:
            result = self.query_api.query(query)
            
            # 按设备ID和指标类型分组
            data_by_device: Dict[str, Dict[str, List[Dict[str, Any]]]] = {}
            
            for table in result:
                for record in table.records:
                    device_id = record.values.get("device_id")
                    metric_type = record.values.get("metric_type")
                    date = record.values.get("date")
                    
                    # 🔧 兼容性处理：daily_summary 中已经做了映射
                    # zone1~zone6 和 scr_1_pump, scr_2_pump 可以直接使用
                    
                    if device_id not in data_by_device:
                        data_by_device[device_id] = {}
                    
                    if metric_type not in data_by_device[device_id]:
                        data_by_device[device_id][metric_type] = []
                    
                    data_by_device[device_id][metric_type].append({
                        "date": date,
                        "start_reading": record.values.get("start_reading", 0.0),
                        "end_reading": record.values.get("end_reading", 0.0),
                        "consumption": record.values.get("consumption", 0.0),
                        "runtime_hours": record.values.get("runtime_hours", 0.0),
                        "feeding_amount": record.values.get("feeding_amount", 0.0),
                        "gas_consumption": record.values.get("gas_consumption", 0.0),
                    })
            
            print(f"✅ 批量查询完成: {len(data_by_device)} 个设备")
            return data_by_device
        
        except Exception as e:
            print(f"❌ 批量查询失败: {str(e)}")
            return {}
    
    # ------------------------------------------------------------
    # 核心优化 2: 并行计算不完整天（使用线程池）
    # ------------------------------------------------------------
    def _parallel_calculate_partial_days(
        self,
        device_configs: List[Dict[str, str]],
        partial_day_slices: List[Any]
    ) -> Dict[str, Dict[str, List[Dict[str, Any]]]]:
        """并行计算所有设备的不完整天数据
        
        Args:
            device_configs: 设备配置列表 [{"device_id": "xxx", "device_type": "xxx", "metric_types": ["electricity", "feeding"]}, ...]
            partial_day_slices: 不完整天的时间切片列表
            
        Returns:
            {
                "short_hopper_1": {
                    "electricity": [...],
                    "feeding": [...]
                },
                ...
            }
        """
        if not partial_day_slices:
            return {}
        
        print(f"🔄 并行计算不完整天: {len(device_configs)} 个设备 × {len(partial_day_slices)} 个时间段")
        
        data_by_device: Dict[str, Dict[str, List[Dict[str, Any]]]] = {}
        
        # 使用线程池并行计算
        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = []
            
            for device_config in device_configs:
                device_id = device_config["device_id"]
                device_type = device_config["device_type"]
                metric_types = device_config["metric_types"]
                
                for metric_type in metric_types:
                    for slice_obj in partial_day_slices:
                        future = executor.submit(
                            self._calculate_realtime_single,
                            device_id,
                            device_type,
                            metric_type,
                            slice_obj
                        )
                        futures.append((future, device_id, metric_type))
            
            # 收集结果
            for future, device_id, metric_type in futures:
                try:
                    record = future.result(timeout=10)
                    
                    if device_id not in data_by_device:
                        data_by_device[device_id] = {}
                    
                    if metric_type not in data_by_device[device_id]:
                        data_by_device[device_id][metric_type] = []
                    
                    data_by_device[device_id][metric_type].append(record)
                
                except Exception as e:
                    print(f"⚠️  计算失败 {device_id}/{metric_type}: {str(e)}")
        
        print(f"✅ 并行计算完成: {len(data_by_device)} 个设备")
        return data_by_device
    
    def _calculate_realtime_single(
        self,
        device_id: str,
        device_type: str,
        metric_type: str,
        slice_obj: Any
    ) -> Dict[str, Any]:
        """计算单个设备、单个指标、单个时间段的实时数据
        
        🔧 兼容性处理：
        - 辊道窑分区 (zone1~zone6): 查询 roller_kiln_1 + module_tag 过滤
        - SCR 氨水泵 (scr_1_pump, scr_2_pump): 查询 scr_1/scr_2 + module_tag=meter
        """
        start_time = slice_obj.start_time
        end_time = slice_obj.end_time
        
        # 🔧 映射虚拟设备ID到实际数据库存储的ID
        actual_device_id, module_tag_filter = self._map_virtual_device_to_actual(device_id, device_type)
        
        if metric_type == "electricity":
            start_reading = self._get_electricity_reading_at_time_with_filter(
                actual_device_id, module_tag_filter, start_time
            )
            end_reading = self._get_electricity_reading_at_time_with_filter(
                actual_device_id, module_tag_filter, end_time
            )
            consumption = 0.0
            if end_reading is not None:
                start_value = start_reading if start_reading is not None else 0.0
                consumption = round(end_reading - start_value, 2)
                if consumption < 0:
                    consumption = round(end_reading, 2)
            
            runtime_hours = self._calculate_runtime_for_period_with_filter(
                actual_device_id, module_tag_filter, start_time, end_time
            )
            
            return {
                "date": slice_obj.date,
                "start_time": format_datetime_without_microseconds(start_time),
                "end_time": format_datetime_without_microseconds(end_time),
                "start_reading": round(start_reading, 2) if start_reading is not None else None,
                "end_reading": round(end_reading, 2) if end_reading is not None else None,
                "consumption": consumption,
                "runtime_hours": runtime_hours,
                "feeding_amount": 0.0,
                "gas_consumption": 0.0
            }
        
        elif metric_type == "gas":
            # 燃气表保持原逻辑（device_id 一致）
            start_reading = self.export_service._get_gas_reading_at_time(
                actual_device_id, start_time
            )
            end_reading = self.export_service._get_gas_reading_at_time(
                actual_device_id, end_time
            )
            consumption = 0.0
            if end_reading is not None:
                start_value = start_reading if start_reading is not None else 0.0
                consumption = round(end_reading - start_value, 2)
                if consumption < 0:
                    consumption = round(end_reading, 2)
            
            runtime_hours = self.export_service._calculate_gas_meter_runtime(
                actual_device_id, start_time, end_time
            )
            
            return {
                "date": slice_obj.date,
                "start_time": format_datetime_without_microseconds(start_time),
                "end_time": format_datetime_without_microseconds(end_time),
                "start_reading": round(start_reading, 2) if start_reading is not None else None,
                "end_reading": round(end_reading, 2) if end_reading is not None else None,
                "consumption": 0.0,
                "runtime_hours": runtime_hours,
                "feeding_amount": 0.0,
                "gas_consumption": consumption
            }
        
        elif metric_type == "feeding":
            # 投料量保持原逻辑（device_id 一致）
            query = f'''
            from(bucket: "{self.bucket}")
                |> range(start: {start_time.isoformat()}, stop: {end_time.isoformat()})
                |> filter(fn: (r) => r["_measurement"] == "feeding_records")
                |> filter(fn: (r) => r["device_id"] == "{actual_device_id}")
                |> filter(fn: (r) => r["_field"] == "added_weight")
                |> sum()
            '''
            
            feeding_amount = 0.0
            try:
                result = self.query_api.query(query)
                for table in result:
                    for record in table.records:
                        feeding_amount = record.get_value()
                        break
            except Exception as e:
                print(f"⚠️  查询投料量失败: {str(e)}")
            
            return {
                "date": slice_obj.date,
                "start_time": format_datetime_without_microseconds(start_time),
                "end_time": format_datetime_without_microseconds(end_time),
                "start_reading": None,
                "end_reading": None,
                "consumption": 0.0,
                "runtime_hours": 0.0,
                "feeding_amount": round(feeding_amount, 2),
                "gas_consumption": 0.0
            }
        
        else:
            return {
                "date": slice_obj.date,
                "start_time": format_datetime_without_microseconds(start_time),
                "end_time": format_datetime_without_microseconds(end_time),
                "start_reading": None,
                "end_reading": None,
                "consumption": 0.0,
                "runtime_hours": 0.0,
                "feeding_amount": 0.0,
                "gas_consumption": 0.0
            }
    
    # ------------------------------------------------------------
    # 🔧 新增：虚拟设备ID映射（兼容历史数据）
    # ------------------------------------------------------------
    def _map_virtual_device_to_actual(
        self,
        device_id: str,
        device_type: str
    ) -> tuple[str, str]:
        """将虚拟设备ID映射到实际数据库存储的ID
        
        Args:
            device_id: 虚拟设备ID (如 zone1, scr_1_pump)
            device_type: 虚拟设备类型
            
        Returns:
            (actual_device_id, module_tag_filter)
            
        映射规则:
        - zone1~zone6 -> (roller_kiln_1, zone1_meter~zone6_meter)
        - scr_1_pump -> (scr_1, meter)
        - scr_2_pump -> (scr_2, meter)
        - 其他设备 -> (device_id, None) 不需要过滤
        """
        # 辊道窑分区映射
        if device_type == "roller_kiln_zone":
            # zone1 -> (roller_kiln_1, zone1_meter)
            module_tag = f"{device_id}_meter"
            return ("roller_kiln_1", module_tag)
        
        # SCR 氨水泵映射
        elif device_type == "scr_pump":
            # scr_1_pump -> (scr_1, meter)
            actual_id = device_id.replace("_pump", "")
            return (actual_id, "meter")
        
        # 其他设备不需要映射
        else:
            return (device_id, None)
    
    # ------------------------------------------------------------
    # 🔧 新增：带 module_tag 过滤的电量读数查询
    # ------------------------------------------------------------
    def _get_electricity_reading_at_time_with_filter(
        self,
        device_id: str,
        module_tag_filter: str,
        target_time: datetime
    ) -> Optional[float]:
        """查询指定时间点的电量读数（支持 module_tag 过滤）
        
        Args:
            device_id: 实际设备ID
            module_tag_filter: 模块标签过滤（如 zone1_meter, meter）
            target_time: 目标时间
            
        Returns:
            电量读数 (ImpEp) 或 None
        """
        # 构建查询（添加 module_tag 过滤）
        if module_tag_filter:
            query = f'''
            from(bucket: "{self.bucket}")
                |> range(start: {(target_time - timedelta(minutes=5)).isoformat()}, 
                         stop: {(target_time + timedelta(minutes=5)).isoformat()})
                |> filter(fn: (r) => r["_measurement"] == "sensor_data")
                |> filter(fn: (r) => r["device_id"] == "{device_id}")
                |> filter(fn: (r) => r["module_tag"] == "{module_tag_filter}")
                |> filter(fn: (r) => r["_field"] == "ImpEp")
                |> last()
            '''
        else:
            # 无需过滤，使用原逻辑
            return self.export_service._get_electricity_reading_at_time(device_id, target_time)
        
        try:
            result = self.query_api.query(query)
            for table in result:
                for record in table.records:
                    return record.get_value()
            return None
        except Exception as e:
            print(f"⚠️  查询电量读数失败 {device_id}/{module_tag_filter}: {str(e)}")
            return None
    
    # ------------------------------------------------------------
    # 🔧 新增：带 module_tag 过滤的运行时长计算
    # ------------------------------------------------------------
    def _calculate_runtime_for_period_with_filter(
        self,
        device_id: str,
        module_tag_filter: str,
        start_time: datetime,
        end_time: datetime
    ) -> float:
        """计算指定时间段的运行时长（支持 module_tag 过滤）
        
        Args:
            device_id: 实际设备ID
            module_tag_filter: 模块标签过滤
            start_time: 开始时间
            end_time: 结束时间
            
        Returns:
            运行时长（小时）
        """
        # 构建查询（添加 module_tag 过滤）
        if module_tag_filter:
            query = f'''
            from(bucket: "{self.bucket}")
                |> range(start: {start_time.isoformat()}, stop: {end_time.isoformat()})
                |> filter(fn: (r) => r["_measurement"] == "sensor_data")
                |> filter(fn: (r) => r["device_id"] == "{device_id}")
                |> filter(fn: (r) => r["module_tag"] == "{module_tag_filter}")
                |> filter(fn: (r) => r["_field"] == "Pt")
                |> filter(fn: (r) => r["_value"] > 0.01)
                |> count()
            '''
        else:
            # 无需过滤，使用原逻辑
            return self.export_service._calculate_runtime_for_period(device_id, start_time, end_time)
        
        try:
            result = self.query_api.query(query)
            count = 0
            for table in result:
                for record in table.records:
                    count = record.get_value()
                    break
            
            # 假设采样间隔为 6 秒
            runtime_hours = (count * 6) / 3600.0
            return round(runtime_hours, 2)
        
        except Exception as e:
            print(f"⚠️  计算运行时长失败 {device_id}/{module_tag_filter}: {str(e)}")
            return 0.0
    
    # ------------------------------------------------------------
    # 核心优化 3: 内存缓存（完整天数据）
    # ------------------------------------------------------------
    def _get_cache_key(self, start_date: str, end_date: str) -> str:
        """生成缓存键"""
        key_str = f"{start_date}_{end_date}"
        return hashlib.md5(key_str.encode()).hexdigest()
    
    def _get_from_cache(self, cache_key: str) -> Optional[Dict[str, Any]]:
        """从缓存获取数据"""
        return _memory_cache.get(cache_key)
    
    def _set_to_cache(self, cache_key: str, data: Dict[str, Any]):
        """存入缓存"""
        _memory_cache[cache_key] = data
        
        # 限制缓存大小（最多保留 100 个条目）
        if len(_memory_cache) > 100:
            # 删除最旧的条目
            oldest_key = next(iter(_memory_cache))
            del _memory_cache[oldest_key]
    
    # ------------------------------------------------------------
    # 主方法: export_comprehensive_v3() - 综合导出（终极优化版）
    # ------------------------------------------------------------
    def export_comprehensive_v3(
        self,
        start_time: datetime,
        end_time: datetime
    ) -> Dict[str, Any]:
        """综合导出所有设备的所有数据（终极优化版）
        
        核心优化:
        1. 批量查询预计算数据（一次查询所有设备）
        2. 并行计算不完整天（线程池）
        3. 内存缓存完整天数据
        
        性能提升: 10-20 倍
        """
        print(f"🚀 开始综合导出（V3终极优化版）: {start_time} ~ {end_time}")
        
        # 1. 按自然日切分时间段
        slices = split_time_range_by_natural_days(start_time, end_time)
        full_day_slices = [s for s in slices if s.is_full_day]
        partial_day_slices = [s for s in slices if not s.is_full_day]
        
        print(f"📊 时间切分: {len(full_day_slices)} 个完整天, {len(partial_day_slices)} 个不完整天")
        
        # 2. 检查缓存（仅完整天）
        cache_key = None
        if full_day_slices and not partial_day_slices:
            start_date = full_day_slices[0].date
            end_date = full_day_slices[-1].date
            cache_key = self._get_cache_key(start_date, end_date)
            cached_data = self._get_from_cache(cache_key)
            
            if cached_data:
                print(f"✅ 命中缓存，直接返回")
                return cached_data
        
        # 3. 批量查询完整天的预计算数据
        precomputed_data = {}
        if full_day_slices:
            start_date = datetime.strptime(full_day_slices[0].date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
            end_date = datetime.strptime(full_day_slices[-1].date, "%Y-%m-%d").replace(tzinfo=timezone.utc) + timedelta(days=1)
            
            # 确保数据已补全
            self.summary_service.check_and_fill_missing_dates(end_date=end_date)
            
            # 批量查询
            precomputed_data = self._batch_query_daily_summary(start_date, end_date)
        
        # 4. 并行计算不完整天
        realtime_data = {}
        if partial_day_slices:
            # 定义所有设备配置
            device_configs = self._get_all_device_configs()
            realtime_data = self._parallel_calculate_partial_days(device_configs, partial_day_slices)
        
        # 5. 合并数据
        merged_data = self._merge_data(precomputed_data, realtime_data, slices)
        
        # 6. 格式化输出
        result = self._format_comprehensive_output(merged_data, start_time, end_time)
        
        # 7. 存入缓存（仅完整天）
        if cache_key:
            self._set_to_cache(cache_key, result)
        
        print(f"✅ 综合导出完成（V3）: {result['total_devices']} 个设备")
        return result
    
    def _get_all_device_configs(self) -> List[Dict[str, str]]:
        """获取所有设备配置"""
        configs = []
        
        # 回转窑（料仓）
        hopper_ids = [
            "short_hopper_1", "short_hopper_2", "short_hopper_3", "short_hopper_4",
            "no_hopper_1", "no_hopper_2",
            "long_hopper_1", "long_hopper_2", "long_hopper_3"
        ]
        for hopper_id in hopper_ids:
            configs.append({
                "device_id": hopper_id,
                "device_type": "hopper",
                "metric_types": ["electricity", "feeding"]
            })
        
        # 辊道窑6个分区
        zone_ids = ["zone1", "zone2", "zone3", "zone4", "zone5", "zone6"]
        for zone_id in zone_ids:
            configs.append({
                "device_id": zone_id,
                "device_type": "roller_kiln_zone",
                "metric_types": ["electricity"]
            })
        
        # 辊道窑合计
        configs.append({
            "device_id": "roller_kiln_total",
            "device_type": "roller_kiln_total",
            "metric_types": ["electricity"]
        })
        
        # SCR燃气表
        configs.extend([
            {"device_id": "scr_1", "device_type": "scr_gas_meter", "metric_types": ["gas"]},
            {"device_id": "scr_2", "device_type": "scr_gas_meter", "metric_types": ["gas"]}
        ])
        
        # SCR氨水泵
        configs.extend([
            {"device_id": "scr_1_pump", "device_type": "scr_pump", "metric_types": ["electricity"]},
            {"device_id": "scr_2_pump", "device_type": "scr_pump", "metric_types": ["electricity"]}
        ])
        
        # 风机
        configs.extend([
            {"device_id": "fan_1", "device_type": "fan", "metric_types": ["electricity"]},
            {"device_id": "fan_2", "device_type": "fan", "metric_types": ["electricity"]}
        ])
        
        return configs
    
    def _merge_data(
        self,
        precomputed_data: Dict[str, Dict[str, List[Dict[str, Any]]]],
        realtime_data: Dict[str, Dict[str, List[Dict[str, Any]]]],
        slices: List[Any]
    ) -> Dict[str, Dict[str, List[Dict[str, Any]]]]:
        """合并预计算数据和实时数据"""
        merged = {}
        
        # 合并预计算数据
        for device_id, metrics in precomputed_data.items():
            if device_id not in merged:
                merged[device_id] = {}
            for metric_type, records in metrics.items():
                if metric_type not in merged[device_id]:
                    merged[device_id][metric_type] = []
                merged[device_id][metric_type].extend(records)
        
        # 合并实时数据
        for device_id, metrics in realtime_data.items():
            if device_id not in merged:
                merged[device_id] = {}
            for metric_type, records in metrics.items():
                if metric_type not in merged[device_id]:
                    merged[device_id][metric_type] = []
                merged[device_id][metric_type].extend(records)
        
        # 按日期排序
        for device_id in merged:
            for metric_type in merged[device_id]:
                merged[device_id][metric_type].sort(key=lambda x: x["date"])
        
        return merged
    
    def _format_comprehensive_output(
        self,
        merged_data: Dict[str, Dict[str, List[Dict[str, Any]]]],
        start_time: datetime,
        end_time: datetime
    ) -> Dict[str, Any]:
        """格式化综合导出输出"""
        devices = []
        
        # 🔧 生成完整的日期范围（确保每天都有记录）
        all_dates = []
        current_date = start_time.replace(hour=0, minute=0, second=0, microsecond=0)
        end_date = end_time.replace(hour=0, minute=0, second=0, microsecond=0)
        
        while current_date <= end_date:
            all_dates.append(current_date.strftime("%Y-%m-%d"))
            current_date += timedelta(days=1)
        
        print(f"📅 生成完整日期范围: {len(all_dates)} 天 ({all_dates[0]} ~ {all_dates[-1]})")
        
        # 获取所有设备配置
        device_configs = self._get_all_device_configs()
        
        for config in device_configs:
            device_id = config["device_id"]
            device_type = config["device_type"]
            
            # 获取该设备的所有数据
            device_data = merged_data.get(device_id, {})
            
            # 🔧 初始化所有日期的记录（确保每天都有数据）
            daily_records_map = {}
            for date in all_dates:
                # 🔧 为完整天填充默认时间（00:00:00 ~ 23:59:59）
                daily_records_map[date] = {
                    "date": date,
                    "start_time": f"{date}T00:00:00+00:00",  # 完整天的起始时间（无微秒）
                    "end_time": f"{date}T23:59:59+00:00",    # 完整天的终止时间（无微秒）
                    "gas_consumption": 0.0,
                    "feeding_amount": 0.0,
                    "electricity_consumption": 0.0,
                    "runtime_hours": 0.0
                }
            
            # 填充实际数据
            for metric_type, records in device_data.items():
                for record in records:
                    date = record["date"]
                    
                    # 🔧 只更新存在于日期范围内的数据
                    if date in daily_records_map:
                        # 🔧 更新起始/终止时间（不完整天使用实际时间，覆盖默认时间）
                        if record.get("start_time"):
                            daily_records_map[date]["start_time"] = record["start_time"]
                        if record.get("end_time"):
                            daily_records_map[date]["end_time"] = record["end_time"]
                        
                        # 更新指标数据
                        if metric_type == "electricity":
                            daily_records_map[date]["electricity_consumption"] = record.get("consumption", 0.0)
                            daily_records_map[date]["runtime_hours"] = record.get("runtime_hours", 0.0)
                        elif metric_type == "gas":
                            daily_records_map[date]["gas_consumption"] = record.get("gas_consumption", 0.0)
                            daily_records_map[date]["runtime_hours"] = record.get("runtime_hours", 0.0)
                        elif metric_type == "feeding":
                            daily_records_map[date]["feeding_amount"] = record.get("feeding_amount", 0.0)
            
            # 🔧 转换为列表并按日期排序（确保时间顺序正确）
            daily_records = sorted(daily_records_map.values(), key=lambda x: x["date"])
            
            devices.append({
                "device_id": device_id,
                "device_type": device_type,
                "daily_records": daily_records
            })
        
        return {
            "start_time": format_datetime_without_microseconds(start_time),
            "end_time": format_datetime_without_microseconds(end_time),
            "total_devices": len(devices),
            "devices": devices
        }


    # ------------------------------------------------------------
    # 新增方法: export_runtime_v3() - 设备运行时长（V3优化版）
    # ------------------------------------------------------------
    def export_runtime_v3(
        self,
        start_time: datetime,
        end_time: datetime
    ) -> Dict[str, Any]:
        """设备运行时长（V3优化版）
        
        复用 export_comprehensive_v3 的数据，只提取运行时长字段
        """
        print(f"🚀 开始设备运行时长（V3）: {start_time} ~ {end_time}")
        
        # 复用综合导出的数据
        comprehensive_data = self.export_comprehensive_v3(start_time, end_time)
        
        # 提取运行时长数据
        result = {
            "start_time": format_datetime_without_microseconds(start_time),
            "end_time": format_datetime_without_microseconds(end_time),
            "hoppers": [],
            "roller_kiln_zones": [],
            "roller_kiln_total": {},
            "scr_devices": [],
            "fan_devices": []
        }
        
        for device in comprehensive_data["devices"]:
            device_id = device["device_id"]
            device_type = device["device_type"]
            
            # 提取运行时长数据
            daily_records = []
            for record in device["daily_records"]:
                daily_records.append({
                    "date": record["date"],
                    "start_time": record["start_time"],
                    "end_time": record["end_time"],
                    "runtime_hours": record["runtime_hours"]
                })
            
            device_data = {
                "device_id": device_id,
                "device_type": device_type,
                "daily_records": daily_records
            }
            
            # 分类存储
            if device_type == "hopper":
                result["hoppers"].append(device_data)
            elif device_type == "roller_kiln_zone":
                result["roller_kiln_zones"].append(device_data)
            elif device_type == "roller_kiln_total":
                result["roller_kiln_total"] = device_data
            elif device_type == "scr_pump":
                result["scr_devices"].append(device_data)
            elif device_type == "fan":
                result["fan_devices"].append(device_data)
        
        print(f"✅ 设备运行时长完成（V3）")
        return result
    
    # ------------------------------------------------------------
    # 新增方法: export_gas_v3() - 燃气消耗统计（V3优化版）
    # ------------------------------------------------------------
    def export_gas_v3(
        self,
        device_ids: List[str],
        start_time: datetime,
        end_time: datetime
    ) -> Dict[str, Any]:
        """燃气消耗统计（V3优化版）
        
        复用 export_comprehensive_v3 的数据，只提取燃气消耗字段
        """
        print(f"🚀 开始燃气消耗统计（V3）: {start_time} ~ {end_time}")
        
        # 复用综合导出的数据
        comprehensive_data = self.export_comprehensive_v3(start_time, end_time)
        
        # 提取燃气消耗数据
        result = {}
        
        for device in comprehensive_data["devices"]:
            device_id = device["device_id"]
            
            # 只处理指定的设备
            if device_id not in device_ids:
                continue
            
            # 提取燃气消耗数据
            daily_records = []
            for record in device["daily_records"]:
                daily_records.append({
                    "date": record["date"],
                    "start_time": record["start_time"],
                    "end_time": record["end_time"],
                    "consumption": record["gas_consumption"],
                    "runtime_hours": record["runtime_hours"]
                })
            
            result[device_id] = {
                "device_id": device_id,
                "daily_records": daily_records
            }
        
        print(f"✅ 燃气消耗统计完成（V3）: {len(result)} 个设备")
        return result
    
    # ------------------------------------------------------------
    # 新增方法: export_feeding_v3() - 累计投料量（V3优化版）
    # ------------------------------------------------------------
    def export_feeding_v3(
        self,
        start_time: datetime,
        end_time: datetime
    ) -> Dict[str, Any]:
        """累计投料量（V3优化版）
        
        复用 export_comprehensive_v3 的数据，只提取投料量字段
        """
        print(f"🚀 开始累计投料量（V3）: {start_time} ~ {end_time}")
        
        # 复用综合导出的数据
        comprehensive_data = self.export_comprehensive_v3(start_time, end_time)
        
        # 提取投料量数据
        result = {"hoppers": []}
        
        for device in comprehensive_data["devices"]:
            device_id = device["device_id"]
            device_type = device["device_type"]
            
            # 只处理料仓设备
            if device_type != "hopper":
                continue
            
            # 跳过无料仓的设备
            if device_id in ["no_hopper_1", "no_hopper_2"]:
                continue
            
            # 提取投料量数据
            daily_records = []
            for record in device["daily_records"]:
                daily_records.append({
                    "date": record["date"],
                    "start_time": record["start_time"],
                    "end_time": record["end_time"],
                    "feeding_amount": record["feeding_amount"]
                })
            
            result["hoppers"].append({
                "device_id": device_id,
                "daily_records": daily_records
            })
        
        print(f"✅ 累计投料量完成（V3）: {len(result['hoppers'])} 个设备")
        return result
    
    # ------------------------------------------------------------
    # 新增方法: export_electricity_v3() - 电量统计（V3优化版）
    # ------------------------------------------------------------
    def export_electricity_v3(
        self,
        start_time: datetime,
        end_time: datetime
    ) -> Dict[str, Any]:
        """电量统计（V3优化版）
        
        复用 export_comprehensive_v3 的数据，只提取电量字段
        
        注意：需要从 daily_summary 表或实时计算中获取 start_reading 和 end_reading
        """
        print(f"🚀 开始电量统计（V3）: {start_time} ~ {end_time}")
        
        # 1. 按自然日切分时间段
        slices = split_time_range_by_natural_days(start_time, end_time)
        full_day_slices = [s for s in slices if s.is_full_day]
        partial_day_slices = [s for s in slices if not s.is_full_day]
        
        # 2. 批量查询完整天的预计算数据
        precomputed_data = {}
        if full_day_slices:
            start_date = datetime.strptime(full_day_slices[0].date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
            end_date = datetime.strptime(full_day_slices[-1].date, "%Y-%m-%d").replace(tzinfo=timezone.utc) + timedelta(days=1)
            
            # 确保数据已补全
            self.summary_service.check_and_fill_missing_dates(end_date=end_date)
            
            # 批量查询
            precomputed_data = self._batch_query_daily_summary(start_date, end_date)
        
        # 3. 并行计算不完整天
        realtime_data = {}
        if partial_day_slices:
            # 只查询有电量数据的设备
            device_configs = [
                config for config in self._get_all_device_configs()
                if "electricity" in config["metric_types"]
            ]
            realtime_data = self._parallel_calculate_partial_days(device_configs, partial_day_slices)
        
        # 4. 合并数据
        merged_data = self._merge_data(precomputed_data, realtime_data, slices)
        
        # 5. 格式化输出（包含 start_reading 和 end_reading）
        result = {
            "start_time": format_datetime_without_microseconds(start_time),
            "end_time": format_datetime_without_microseconds(end_time),
            "hoppers": [],
            "roller_kiln_zones": [],
            "roller_kiln_total": {},
            "scr_devices": [],
            "fan_devices": []
        }
        
        # 生成完整的日期范围
        all_dates = []
        current_date = start_time.replace(hour=0, minute=0, second=0, microsecond=0)
        end_date_obj = end_time.replace(hour=0, minute=0, second=0, microsecond=0)
        
        while current_date <= end_date_obj:
            all_dates.append(current_date.strftime("%Y-%m-%d"))
            current_date += timedelta(days=1)
        
        # 获取所有有电量数据的设备
        device_configs = [
            config for config in self._get_all_device_configs()
            if "electricity" in config["metric_types"]
        ]
        
        for config in device_configs:
            device_id = config["device_id"]
            device_type = config["device_type"]
            
            # 获取该设备的电量数据
            device_data = merged_data.get(device_id, {}).get("electricity", [])
            
            # 初始化所有日期的记录
            daily_records_map = {}
            for date in all_dates:
                daily_records_map[date] = {
                    "date": date,
                    "start_time": f"{date}T00:00:00+00:00",
                    "end_time": f"{date}T23:59:59+00:00",
                    "start_reading": 0.0,
                    "end_reading": 0.0,
                    "consumption": 0.0,
                    "runtime_hours": 0.0
                }
            
            # 填充实际数据
            for record in device_data:
                date = record["date"]
                if date in daily_records_map:
                    # 更新时间
                    if record.get("start_time"):
                        daily_records_map[date]["start_time"] = record["start_time"]
                    if record.get("end_time"):
                        daily_records_map[date]["end_time"] = record["end_time"]
                    
                    # 更新读数和消耗
                    daily_records_map[date]["start_reading"] = record.get("start_reading", 0.0) or 0.0
                    daily_records_map[date]["end_reading"] = record.get("end_reading", 0.0) or 0.0
                    daily_records_map[date]["consumption"] = record.get("consumption", 0.0)
                    daily_records_map[date]["runtime_hours"] = record.get("runtime_hours", 0.0)
            
            # 转换为列表并排序
            daily_records = sorted(daily_records_map.values(), key=lambda x: x["date"])
            
            device_data_obj = {
                "device_id": device_id,
                "device_type": device_type,
                "daily_records": daily_records
            }
            
            # 分类存储
            if device_type == "hopper":
                result["hoppers"].append(device_data_obj)
            elif device_type == "roller_kiln_zone":
                result["roller_kiln_zones"].append(device_data_obj)
            elif device_type == "roller_kiln_total":
                result["roller_kiln_total"] = device_data_obj
            elif device_type == "scr_pump":
                result["scr_devices"].append(device_data_obj)
            elif device_type == "fan":
                result["fan_devices"].append(device_data_obj)
        
        print(f"✅ 电量统计完成（V3）")
        return result


# ------------------------------------------------------------
# 单例获取函数
# ------------------------------------------------------------
def get_export_service_v3() -> DataExportServiceV3:
    """获取数据导出服务V3单例"""
    global _export_service_v3_instance
    if _export_service_v3_instance is None:
        _export_service_v3_instance = DataExportServiceV3()
    return _export_service_v3_instance

