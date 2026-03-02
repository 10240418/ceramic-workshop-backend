# ============================================================
# 测试文件: test_export_optimization.py - 导出服务查询优化单元测试
# ============================================================
# 覆盖范围:
#   1. _batch_query_daily_runtime()      - 批量运行时长查询
#   2. _batch_query_daily_first_last()   - 批量首尾读数查询
#   3. calculate_gas_consumption_by_day() - 燃气消耗按天统计
#   4. calculate_electricity_consumption_by_day() - 电量按天统计
#   5. calculate_all_devices_runtime_by_day() - 所有设备运行时长
#   6. _calc_runtime_count()              - daily_summary 运行时长计算
# ============================================================

import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch, PropertyMock
from typing import List, Any


# ============================================================
# Mock InfluxDB Record/Table 辅助类
# ============================================================

class MockRecord:
    """模拟 InfluxDB FluxRecord"""

    def __init__(self, time: datetime, value: Any, field: str = ""):
        self._time = time
        self._value = value
        self._field = field

    def get_time(self) -> datetime:
        return self._time

    def get_value(self) -> Any:
        return self._value

    def get_field(self) -> str:
        return self._field


class MockTable:
    """模拟 InfluxDB FluxTable"""

    def __init__(self, records: List[MockRecord]):
        self.records = records


# ============================================================
# 辅助函数
# ============================================================

def make_utc(year=2026, month=1, day=26, hour=0, minute=0, second=0):
    """创建 UTC 时间"""
    return datetime(year, month, day, hour, minute, second, tzinfo=timezone.utc)


def make_daily_count_tables(date_counts: dict) -> List[MockTable]:
    """构造 aggregateWindow count 返回结果
    
    Args:
        date_counts: {"2026-01-26": 10800, "2026-01-27": 5400}
    
    Returns:
        [MockTable([MockRecord(...), ...])]
    """
    records = []
    for date_str, count in date_counts.items():
        parts = date_str.split("-")
        ts = make_utc(int(parts[0]), int(parts[1]), int(parts[2]))
        records.append(MockRecord(time=ts, value=count))
    return [MockTable(records)]


def make_daily_value_tables(date_values: dict) -> List[MockTable]:
    """构造 aggregateWindow first/last 返回结果
    
    Args:
        date_values: {"2026-01-26": 1234.5, "2026-01-27": 1456.7}
    
    Returns:
        [MockTable([MockRecord(...), ...])]
    """
    records = []
    for date_str, value in date_values.items():
        parts = date_str.split("-")
        ts = make_utc(int(parts[0]), int(parts[1]), int(parts[2]))
        records.append(MockRecord(time=ts, value=value))
    return [MockTable(records)]


# ============================================================
# 1. DataExportService._batch_query_daily_runtime 测试
# ============================================================

class TestBatchQueryDailyRuntime:
    """测试批量运行时长查询"""

    def _create_service(self):
        """创建 DataExportService 实例 (mock InfluxDB)"""
        with patch("app.services.data_export_service.get_influx_client"):
            from app.services.data_export_service import DataExportService
            svc = DataExportService()
            svc._query_api = MagicMock()
            return svc

    def test_basic_runtime_calculation(self):
        """基本运行时长计算: count=10800 -> 18.0 小时"""
        svc = self._create_service()
        # 10800 个 6 秒间隔 = 10800 * 6 / 3600 = 18.0 小时
        svc._query_api.query.return_value = make_daily_count_tables({
            "2026-01-26": 10800,
        })

        result = svc._batch_query_daily_runtime(
            device_id="short_hopper_1",
            start_time=make_utc(2026, 1, 26),
            end_time=make_utc(2026, 1, 27),
        )

        assert "2026-01-26" in result
        assert result["2026-01-26"] == 18.0
        svc._query_api.query.assert_called_once()

    def test_multi_day_runtime(self):
        """多天运行时长: 3天数据"""
        svc = self._create_service()
        svc._query_api.query.return_value = make_daily_count_tables({
            "2026-01-26": 14400,  # 14400*6/3600 = 24.0h
            "2026-01-27": 7200,   # 7200*6/3600 = 12.0h
            "2026-01-28": 0,      # 0h (createEmpty=true)
        })

        result = svc._batch_query_daily_runtime(
            device_id="short_hopper_1",
            start_time=make_utc(2026, 1, 26),
            end_time=make_utc(2026, 1, 29),
        )

        assert result["2026-01-26"] == 24.0
        assert result["2026-01-27"] == 12.0
        assert result["2026-01-28"] == 0.0

    def test_empty_result(self):
        """空结果: InfluxDB 无数据"""
        svc = self._create_service()
        svc._query_api.query.return_value = []

        result = svc._batch_query_daily_runtime(
            device_id="short_hopper_1",
            start_time=make_utc(2026, 1, 26),
            end_time=make_utc(2026, 1, 27),
        )

        assert result == {}

    def test_query_exception(self):
        """查询异常: 返回空字典, 不崩溃"""
        svc = self._create_service()
        svc._query_api.query.side_effect = Exception("InfluxDB connection refused")

        result = svc._batch_query_daily_runtime(
            device_id="short_hopper_1",
            start_time=make_utc(2026, 1, 26),
            end_time=make_utc(2026, 1, 27),
        )

        assert result == {}

    def test_module_tag_filter(self):
        """module_tag 过滤: 辊道窑分区"""
        svc = self._create_service()
        svc._query_api.query.return_value = make_daily_count_tables({
            "2026-01-26": 5000,
        })

        result = svc._batch_query_daily_runtime(
            device_id="roller_kiln_1",
            start_time=make_utc(2026, 1, 26),
            end_time=make_utc(2026, 1, 27),
            module_tag="zone1_meter",
        )

        assert "2026-01-26" in result
        # 验证查询语句包含 module_tag
        query_str = svc._query_api.query.call_args[0][0]
        assert 'module_tag' in query_str
        assert 'zone1_meter' in query_str

    def test_custom_threshold(self):
        """自定义阈值: threshold=5.0"""
        svc = self._create_service()
        svc._query_api.query.return_value = make_daily_count_tables({
            "2026-01-26": 3600,
        })

        result = svc._batch_query_daily_runtime(
            device_id="fan_1",
            start_time=make_utc(2026, 1, 26),
            end_time=make_utc(2026, 1, 27),
            threshold=5.0,
        )

        # 3600 * 6 / 3600 = 6.0h
        assert result["2026-01-26"] == 6.0
        query_str = svc._query_api.query.call_args[0][0]
        assert "> 5.0" in query_str

    def test_none_count_treated_as_zero(self):
        """count 返回 None (createEmpty=true 时可能出现)"""
        svc = self._create_service()
        records = [MockRecord(time=make_utc(2026, 1, 26), value=None)]
        svc._query_api.query.return_value = [MockTable(records)]

        result = svc._batch_query_daily_runtime(
            device_id="short_hopper_1",
            start_time=make_utc(2026, 1, 26),
            end_time=make_utc(2026, 1, 27),
        )

        assert result["2026-01-26"] == 0.0


# ============================================================
# 2. DataExportService._batch_query_daily_first_last 测试
# ============================================================

class TestBatchQueryDailyFirstLast:
    """测试批量首尾读数查询"""

    def _create_service(self):
        with patch("app.services.data_export_service.get_influx_client"):
            from app.services.data_export_service import DataExportService
            svc = DataExportService()
            svc._query_api = MagicMock()
            return svc

    def test_basic_first_last(self):
        """基本首尾读数: 单天"""
        svc = self._create_service()
        # query 被调用 2 次: first + last
        svc._query_api.query.side_effect = [
            make_daily_value_tables({"2026-01-26": 1000.0}),  # first
            make_daily_value_tables({"2026-01-26": 1200.0}),  # last
        ]

        result = svc._batch_query_daily_first_last(
            device_id="short_hopper_1",
            field="ImpEp",
            start_time=make_utc(2026, 1, 26),
            end_time=make_utc(2026, 1, 27),
        )

        assert "2026-01-26" in result
        first_val, last_val = result["2026-01-26"]
        assert first_val == 1000.0
        assert last_val == 1200.0
        assert svc._query_api.query.call_count == 2

    def test_multi_day_first_last(self):
        """多天首尾读数"""
        svc = self._create_service()
        svc._query_api.query.side_effect = [
            make_daily_value_tables({
                "2026-01-26": 1000.0,
                "2026-01-27": 1200.0,
            }),
            make_daily_value_tables({
                "2026-01-26": 1100.0,
                "2026-01-27": 1350.0,
            }),
        ]

        result = svc._batch_query_daily_first_last(
            device_id="scr_1",
            field="total_flow",
            start_time=make_utc(2026, 1, 26),
            end_time=make_utc(2026, 1, 28),
        )

        assert result["2026-01-26"] == (1000.0, 1100.0)
        assert result["2026-01-27"] == (1200.0, 1350.0)

    def test_empty_result(self):
        """空结果: 无数据"""
        svc = self._create_service()
        svc._query_api.query.side_effect = [[], []]

        result = svc._batch_query_daily_first_last(
            device_id="fan_1",
            field="ImpEp",
            start_time=make_utc(2026, 1, 26),
            end_time=make_utc(2026, 1, 27),
        )

        assert result == {}

    def test_partial_data(self):
        """部分数据: first 有值, last 无值"""
        svc = self._create_service()
        svc._query_api.query.side_effect = [
            make_daily_value_tables({"2026-01-26": 500.0}),  # first
            [],  # last 无数据
        ]

        result = svc._batch_query_daily_first_last(
            device_id="scr_1",
            field="ImpEp",
            start_time=make_utc(2026, 1, 26),
            end_time=make_utc(2026, 1, 27),
        )

        assert "2026-01-26" in result
        first_val, last_val = result["2026-01-26"]
        assert first_val == 500.0
        assert last_val is None

    def test_query_exception(self):
        """查询异常: 返回空字典"""
        svc = self._create_service()
        svc._query_api.query.side_effect = Exception("InfluxDB timeout")

        result = svc._batch_query_daily_first_last(
            device_id="scr_1",
            field="total_flow",
            start_time=make_utc(2026, 1, 26),
            end_time=make_utc(2026, 1, 27),
        )

        assert result == {}

    def test_module_tag_in_query(self):
        """验证 module_tag 出现在查询语句中"""
        svc = self._create_service()
        svc._query_api.query.side_effect = [
            make_daily_value_tables({"2026-01-26": 100.0}),
            make_daily_value_tables({"2026-01-26": 200.0}),
        ]

        svc._batch_query_daily_first_last(
            device_id="roller_kiln_1",
            field="ImpEp",
            start_time=make_utc(2026, 1, 26),
            end_time=make_utc(2026, 1, 27),
            module_tag="zone3_meter",
        )

        # 两次 query 调用的语句都应包含 module_tag
        for call_args in svc._query_api.query.call_args_list:
            query_str = call_args[0][0]
            assert 'zone3_meter' in query_str


# ============================================================
# 3. calculate_gas_consumption_by_day 测试
# ============================================================

class TestGasConsumptionByDay:
    """测试燃气消耗按天统计 (refactored V1)"""

    def _create_service(self):
        with patch("app.services.data_export_service.get_influx_client"):
            from app.services.data_export_service import DataExportService
            svc = DataExportService()
            svc._query_api = MagicMock()
            return svc

    def test_single_device_single_day(self):
        """单设备单天"""
        svc = self._create_service()
        # _batch_query_daily_first_last 底层调用 2 次 query
        svc._query_api.query.side_effect = [
            make_daily_value_tables({"2026-01-26": 1000.0}),  # first
            make_daily_value_tables({"2026-01-26": 1250.0}),  # last
        ]

        result = svc.calculate_gas_consumption_by_day(
            device_ids=["scr_1"],
            start_time=make_utc(2026, 1, 26),
            end_time=make_utc(2026, 1, 27),
        )

        assert "scr_1" in result
        data = result["scr_1"]
        assert data["device_id"] == "scr_1"
        assert data["total_days"] == 1
        
        record = data["daily_records"][0]
        assert record["date"] == "2026-01-26"
        assert record["start_reading"] == 1000.0
        assert record["end_reading"] == 1250.0
        assert record["consumption"] == 250.0

    def test_negative_consumption_fallback(self):
        """负消耗处理: 仪表重置时使用 end_reading"""
        svc = self._create_service()
        svc._query_api.query.side_effect = [
            make_daily_value_tables({"2026-01-26": 9999.0}),  # first (旧表)
            make_daily_value_tables({"2026-01-26": 100.0}),   # last (重置后)
        ]

        result = svc.calculate_gas_consumption_by_day(
            device_ids=["scr_1"],
            start_time=make_utc(2026, 1, 26),
            end_time=make_utc(2026, 1, 27),
        )

        record = result["scr_1"]["daily_records"][0]
        # 100.0 - 9999.0 < 0, 所以 consumption = round(end_reading, 2) = 100.0
        assert record["consumption"] == 100.0

    def test_no_data_day(self):
        """无数据天: readings 为 None"""
        svc = self._create_service()
        # first/last 都无数据
        svc._query_api.query.side_effect = [[], []]

        result = svc.calculate_gas_consumption_by_day(
            device_ids=["scr_2"],
            start_time=make_utc(2026, 1, 26),
            end_time=make_utc(2026, 1, 27),
        )

        record = result["scr_2"]["daily_records"][0]
        assert record["start_reading"] is None
        assert record["end_reading"] is None
        assert record["consumption"] == 0.0

    def test_multi_device(self):
        """多设备: scr_1 + scr_2"""
        svc = self._create_service()
        # scr_1 的 first/last
        svc._query_api.query.side_effect = [
            make_daily_value_tables({"2026-01-26": 100.0}),
            make_daily_value_tables({"2026-01-26": 200.0}),
            # scr_2 的 first/last
            make_daily_value_tables({"2026-01-26": 500.0}),
            make_daily_value_tables({"2026-01-26": 800.0}),
        ]

        result = svc.calculate_gas_consumption_by_day(
            device_ids=["scr_1", "scr_2"],
            start_time=make_utc(2026, 1, 26),
            end_time=make_utc(2026, 1, 27),
        )

        assert result["scr_1"]["daily_records"][0]["consumption"] == 100.0
        assert result["scr_2"]["daily_records"][0]["consumption"] == 300.0


# ============================================================
# 4. calculate_electricity_consumption_by_day 测试
# ============================================================

class TestElectricityConsumptionByDay:
    """测试电量消耗按天统计 (refactored V1)"""

    def _create_service(self):
        with patch("app.services.data_export_service.get_influx_client"):
            from app.services.data_export_service import DataExportService
            svc = DataExportService()
            svc._query_api = MagicMock()
            return svc

    def test_single_day_with_runtime(self):
        """单天电量 + 运行时长"""
        svc = self._create_service()
        svc._query_api.query.side_effect = [
            # _batch_query_daily_first_last: first
            make_daily_value_tables({"2026-01-26": 5000.0}),
            # _batch_query_daily_first_last: last
            make_daily_value_tables({"2026-01-26": 5200.0}),
            # _batch_query_daily_runtime: count
            make_daily_count_tables({"2026-01-26": 10800}),  # 18.0h
        ]

        result = svc.calculate_electricity_consumption_by_day(
            device_id="short_hopper_1",
            device_type="hopper",
            start_time=make_utc(2026, 1, 26),
            end_time=make_utc(2026, 1, 27),
        )

        assert result["device_id"] == "short_hopper_1"
        assert result["device_type"] == "hopper"
        assert result["total_days"] == 1

        record = result["daily_records"][0]
        assert record["start_reading"] == 5000.0
        assert record["end_reading"] == 5200.0
        assert record["consumption"] == 200.0
        assert record["runtime_hours"] == 18.0

    def test_multi_day_electricity(self):
        """多天电量统计"""
        svc = self._create_service()
        svc._query_api.query.side_effect = [
            # first values
            make_daily_value_tables({
                "2026-01-26": 1000.0,
                "2026-01-27": 1100.0,
            }),
            # last values
            make_daily_value_tables({
                "2026-01-26": 1100.0,
                "2026-01-27": 1250.0,
            }),
            # runtime counts
            make_daily_count_tables({
                "2026-01-26": 7200,  # 12.0h
                "2026-01-27": 3600,  # 6.0h
            }),
        ]

        result = svc.calculate_electricity_consumption_by_day(
            device_id="fan_1",
            device_type="fan",
            start_time=make_utc(2026, 1, 26),
            end_time=make_utc(2026, 1, 28),
        )

        assert result["total_days"] == 2
        assert result["daily_records"][0]["consumption"] == 100.0
        assert result["daily_records"][0]["runtime_hours"] == 12.0
        assert result["daily_records"][1]["consumption"] == 150.0
        assert result["daily_records"][1]["runtime_hours"] == 6.0


# ============================================================
# 5. calculate_all_devices_runtime_by_day 测试
# ============================================================

class TestAllDevicesRuntimeByDay:
    """测试所有设备运行时长按天统计"""

    def _create_service(self):
        with patch("app.services.data_export_service.get_influx_client"):
            from app.services.data_export_service import DataExportService
            svc = DataExportService()
            svc._query_api = MagicMock()
            return svc

    def test_output_structure(self):
        """验证输出结构: 所有 5 个设备组"""
        svc = self._create_service()
        # 9 hoppers + 6 zones + 2 SCR + 2 fans = 19 次 _batch_query_daily_runtime 调用
        svc._query_api.query.return_value = make_daily_count_tables({
            "2026-01-26": 7200,
        })

        result = svc.calculate_all_devices_runtime_by_day(
            start_time=make_utc(2026, 1, 26),
            end_time=make_utc(2026, 1, 27),
        )

        # 验证结构完整性
        assert "hoppers" in result
        assert "roller_kiln_zones" in result
        assert "roller_kiln_total" in result
        assert "scr_devices" in result
        assert "fan_devices" in result

        # 验证设备数量
        assert len(result["hoppers"]) == 9
        assert len(result["roller_kiln_zones"]) == 6
        assert len(result["scr_devices"]) == 2
        assert len(result["fan_devices"]) == 2

    def test_hopper_runtime_values(self):
        """验证料仓运行时长数据"""
        svc = self._create_service()
        # 所有 query 调用返回相同结果 (简化测试)
        svc._query_api.query.return_value = make_daily_count_tables({
            "2026-01-26": 10800,  # 18h
        })

        result = svc.calculate_all_devices_runtime_by_day(
            start_time=make_utc(2026, 1, 26),
            end_time=make_utc(2026, 1, 27),
        )

        for hopper in result["hoppers"]:
            assert hopper["device_type"] == "hopper"
            assert hopper["total_days"] == 1
            record = hopper["daily_records"][0]
            assert record["runtime_hours"] == 18.0

    def test_query_count_optimized(self):
        """验证查询次数: 9+6+2+2=19 次 query (非 19*N 次)"""
        svc = self._create_service()
        svc._query_api.query.return_value = make_daily_count_tables({
            "2026-01-26": 100,
            "2026-01-27": 200,
            "2026-01-28": 300,
        })

        svc.calculate_all_devices_runtime_by_day(
            start_time=make_utc(2026, 1, 26),
            end_time=make_utc(2026, 1, 29),  # 3 天
        )

        # 19 个设备, 每个 1 次查询 = 19 次
        # 旧版本: 19 * 3天 = 57 次
        assert svc._query_api.query.call_count == 19

    def test_roller_kiln_total_average(self):
        """辊道窑合计: 6个温区平均"""
        svc = self._create_service()
        call_count = [0]
        
        def mock_query(query_str):
            call_count[0] += 1
            # 前 9 次是 hoppers, 10-15 是 zones, 16-17 SCR, 18-19 fans
            if 10 <= call_count[0] <= 15:
                # zone 查询: 返回不同运行时长
                zone_idx = call_count[0] - 10
                hours_map = {
                    0: 12000,  # zone1: 20h
                    1: 10800,  # zone2: 18h
                    2: 10800,  # zone3: 18h
                    3: 14400,  # zone4: 24h
                    4: 7200,   # zone5: 12h
                    5: 7200,   # zone6: 12h
                }
                count = hours_map.get(zone_idx, 0)
                return make_daily_count_tables({"2026-01-26": count})
            return make_daily_count_tables({"2026-01-26": 0})
        
        svc._query_api.query.side_effect = mock_query

        result = svc.calculate_all_devices_runtime_by_day(
            start_time=make_utc(2026, 1, 26),
            end_time=make_utc(2026, 1, 27),
        )

        # zone 运行时长: 20, 18, 18, 24, 12, 12 -> 平均 = 17.33
        total_record = result["roller_kiln_total"]["daily_records"][0]
        assert total_record["runtime_hours"] == pytest.approx(17.33, abs=0.01)


# ============================================================
# 6. DailySummaryService._calc_runtime_count 测试
# ============================================================

class TestCalcRuntimeCount:
    """测试 daily_summary 运行时长计算"""

    def _create_service(self):
        with patch("app.services.daily_summary_service.get_influx_client"):
            from app.services.daily_summary_service import DailySummaryService
            svc = DailySummaryService()
            svc._client = MagicMock()
            return svc

    def test_basic_runtime_count(self):
        """基本计算: 600 个点 * 6s = 1.0 小时"""
        svc = self._create_service()
        mock_query_api = MagicMock()
        svc._client.query_api.return_value = mock_query_api

        records = [MockRecord(time=make_utc(), value=600)]
        mock_query_api.query.return_value = [MockTable(records)]

        result = svc._calc_runtime_count(
            device_id="short_hopper_1",
            day_start=make_utc(2026, 1, 26),
            day_end=make_utc(2026, 1, 27),
        )

        # 600 * 6 / 3600 = 1.0
        assert result == 1.0

    def test_full_day_runtime(self):
        """全天运行: 14400 个点 = 24.0 小时"""
        svc = self._create_service()
        mock_query_api = MagicMock()
        svc._client.query_api.return_value = mock_query_api

        records = [MockRecord(time=make_utc(), value=14400)]
        mock_query_api.query.return_value = [MockTable(records)]

        result = svc._calc_runtime_count(
            device_id="scr_1",
            day_start=make_utc(2026, 1, 26),
            day_end=make_utc(2026, 1, 27),
        )

        assert result == 24.0

    def test_zero_runtime(self):
        """零运行时长: 设备关闭"""
        svc = self._create_service()
        mock_query_api = MagicMock()
        svc._client.query_api.return_value = mock_query_api

        records = [MockRecord(time=make_utc(), value=0)]
        mock_query_api.query.return_value = [MockTable(records)]

        result = svc._calc_runtime_count(
            device_id="fan_1",
            day_start=make_utc(2026, 1, 26),
            day_end=make_utc(2026, 1, 27),
        )

        assert result == 0.0

    def test_query_exception_returns_zero(self):
        """查询异常: 返回 0.0, 不崩溃"""
        svc = self._create_service()
        mock_query_api = MagicMock()
        svc._client.query_api.return_value = mock_query_api
        mock_query_api.query.side_effect = Exception("network error")

        result = svc._calc_runtime_count(
            device_id="short_hopper_1",
            day_start=make_utc(2026, 1, 26),
            day_end=make_utc(2026, 1, 27),
        )

        assert result == 0.0

    def test_extra_filter_in_query(self):
        """extra_filter 参数: 辊道窑分区过滤"""
        svc = self._create_service()
        mock_query_api = MagicMock()
        svc._client.query_api.return_value = mock_query_api

        records = [MockRecord(time=make_utc(), value=3600)]
        mock_query_api.query.return_value = [MockTable(records)]

        extra_filter = '|> filter(fn: (r) => r["sensor_type"] == "zone1_meter")'
        result = svc._calc_runtime_count(
            device_id="roller_kiln_1",
            day_start=make_utc(2026, 1, 26),
            day_end=make_utc(2026, 1, 27),
            extra_filter=extra_filter,
        )

        # 3600 * 6 / 3600 = 6.0h
        assert result == 6.0
        # 验证 extra_filter 出现在查询中
        query_str = mock_query_api.query.call_args[0][0]
        assert 'zone1_meter' in query_str

    def test_custom_field_and_threshold(self):
        """自定义 field 和 threshold"""
        svc = self._create_service()
        mock_query_api = MagicMock()
        svc._client.query_api.return_value = mock_query_api

        records = [MockRecord(time=make_utc(), value=1800)]
        mock_query_api.query.return_value = [MockTable(records)]

        result = svc._calc_runtime_count(
            device_id="scr_1",
            day_start=make_utc(2026, 1, 26),
            day_end=make_utc(2026, 1, 27),
            field="flow_rate",
            threshold=0.5,
        )

        # 1800 * 6 / 3600 = 3.0h
        assert result == 3.0
        query_str = mock_query_api.query.call_args[0][0]
        assert 'flow_rate' in query_str
        assert '0.5' in query_str

    def test_none_value_treated_as_zero(self):
        """count 返回 None: 视为 0"""
        svc = self._create_service()
        mock_query_api = MagicMock()
        svc._client.query_api.return_value = mock_query_api

        records = [MockRecord(time=make_utc(), value=None)]
        mock_query_api.query.return_value = [MockTable(records)]

        result = svc._calc_runtime_count(
            device_id="short_hopper_1",
            day_start=make_utc(2026, 1, 26),
            day_end=make_utc(2026, 1, 27),
        )

        assert result == 0.0

    def test_empty_result_zero(self):
        """空结果集: 返回 0"""
        svc = self._create_service()
        mock_query_api = MagicMock()
        svc._client.query_api.return_value = mock_query_api
        mock_query_api.query.return_value = []

        result = svc._calc_runtime_count(
            device_id="short_hopper_1",
            day_start=make_utc(2026, 1, 26),
            day_end=make_utc(2026, 1, 27),
        )

        assert result == 0.0


# ============================================================
# 7. Flux 查询语句验证
# ============================================================

class TestFluxQueryContent:
    """验证生成的 Flux 查询语句内容正确"""

    def _create_export_service(self):
        with patch("app.services.data_export_service.get_influx_client"):
            from app.services.data_export_service import DataExportService
            svc = DataExportService()
            svc._query_api = MagicMock()
            svc._query_api.query.return_value = []
            return svc

    def test_runtime_query_uses_sensor_data(self):
        """运行时长查询使用 sensor_data measurement"""
        svc = self._create_export_service()
        svc._batch_query_daily_runtime("short_hopper_1", make_utc(2026, 1, 26), make_utc(2026, 1, 27))

        query_str = svc._query_api.query.call_args[0][0]
        assert 'sensor_data' in query_str
        assert 'aggregateWindow' in query_str
        assert 'fn: count' in query_str
        assert 'createEmpty: true' in query_str
        assert 'timeSrc: "_start"' in query_str

    def test_first_last_query_uses_sensor_data(self):
        """首尾读数查询使用 sensor_data measurement"""
        svc = self._create_export_service()
        svc._query_api.query.return_value = []
        svc._batch_query_daily_first_last("scr_1", "total_flow", make_utc(2026, 1, 26), make_utc(2026, 1, 27))

        calls = svc._query_api.query.call_args_list
        assert len(calls) == 2

        first_query = calls[0][0][0]
        last_query = calls[1][0][0]

        assert 'fn: first' in first_query
        assert 'fn: last' in last_query
        assert 'createEmpty: false' in first_query
        assert 'createEmpty: false' in last_query

    def test_runtime_query_default_threshold(self):
        """运行时长默认阈值 1.0 (C3 修复后)"""
        svc = self._create_export_service()
        svc._batch_query_daily_runtime("short_hopper_1", make_utc(2026, 1, 26), make_utc(2026, 1, 27))

        query_str = svc._query_api.query.call_args[0][0]
        assert '> 1.0' in query_str

    def test_runtime_query_date_alignment(self):
        """验证时间范围对齐到 UTC 日边界"""
        svc = self._create_export_service()
        # start_time 带有时分秒
        start = make_utc(2026, 1, 26, 8, 30, 15)
        end = make_utc(2026, 1, 28, 16, 45, 0)

        svc._batch_query_daily_runtime("short_hopper_1", start, end)

        query_str = svc._query_api.query.call_args[0][0]
        # 应对齐到 2026-01-26T00:00:00 和 2026-01-29T00:00:00
        assert '2026-01-26T00:00:00' in query_str
        assert '2026-01-29T00:00:00' in query_str

    def test_daily_summary_runtime_uses_module_data(self):
        """daily_summary 的 _calc_runtime_count 使用 module_data measurement"""
        with patch("app.services.daily_summary_service.get_influx_client"):
            from app.services.daily_summary_service import DailySummaryService
            svc = DailySummaryService()
            svc._client = MagicMock()
            mock_query_api = MagicMock()
            svc._client.query_api.return_value = mock_query_api
            mock_query_api.query.return_value = []

            svc._calc_runtime_count("short_hopper_1", make_utc(2026, 1, 26), make_utc(2026, 1, 27))

            query_str = mock_query_api.query.call_args[0][0]
            assert 'module_data' in query_str
            assert 'count()' in query_str
            # daily_summary 使用 RUNTIME_POWER_THRESHOLD = 1.0
            assert '> 1.0' in query_str
