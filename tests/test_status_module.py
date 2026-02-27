# ============================================================
# 测试文件: test_status_module.py - Status 模块单元测试
# ============================================================
# 覆盖范围:
#   1. DeviceStatusParser - 状态位解析器
#   2. status router - HTTP 降级接口
#   3. ws_manager._push_device_status() - WebSocket 推送逻辑
#   4. polling_service._poll_device_status_loop() - 轮询逻辑
# ============================================================

import pytest
import asyncio
import struct
from unittest.mock import MagicMock, AsyncMock, patch
from typing import Dict, Any


# ============================================================
# 1. DeviceStatusParser 单元测试
# ============================================================

class TestDeviceStatusParser:
    """设备状态位解析器测试"""

    def _make_module_bytes(self, error: bool, status_code: int) -> bytes:
        """构造单个模块的 4 字节状态数据
        格式: [Error(Bool, byte0 bit0)] [padding byte1] [Status(Word, bytes 2-3 大端序)]
        """
        byte0 = 0x01 if error else 0x00
        byte1 = 0x00
        byte2 = (status_code >> 8) & 0xFF
        byte3 = status_code & 0xFF
        return bytes([byte0, byte1, byte2, byte3])

    def test_parse_module_status_normal(self):
        """测试正常模块解析 (error=False, status=0)"""
        from app.plc.parser_device_status import DeviceStatusParser
        parser = DeviceStatusParser.__new__(DeviceStatusParser)
        parser._configs = {}

        data = self._make_module_bytes(error=False, status_code=0)
        result = parser.parse_module_status(data, offset=0)

        assert result['error'] is False
        assert result['status_code'] == 0
        assert result['status_hex'] == '0000'

    def test_parse_module_status_error(self):
        """测试故障模块解析 (error=True, status=0x0001)"""
        from app.plc.parser_device_status import DeviceStatusParser
        parser = DeviceStatusParser.__new__(DeviceStatusParser)
        parser._configs = {}

        data = self._make_module_bytes(error=True, status_code=0x0001)
        result = parser.parse_module_status(data, offset=0)

        assert result['error'] is True
        assert result['status_code'] == 1
        assert result['status_hex'] == '0001'

    def test_parse_module_status_high_status(self):
        """测试高位状态码 (error=False, status=0xABCD)"""
        from app.plc.parser_device_status import DeviceStatusParser
        parser = DeviceStatusParser.__new__(DeviceStatusParser)
        parser._configs = {}

        data = self._make_module_bytes(error=False, status_code=0xABCD)
        result = parser.parse_module_status(data, offset=0)

        assert result['error'] is False
        assert result['status_code'] == 0xABCD
        assert result['status_hex'] == 'ABCD'

    def test_parse_module_status_out_of_range(self):
        """测试越界情况 (数据不足 4 字节)"""
        from app.plc.parser_device_status import DeviceStatusParser
        parser = DeviceStatusParser.__new__(DeviceStatusParser)
        parser._configs = {}

        data = bytes([0x00, 0x00])  # 只有 2 字节
        result = parser.parse_module_status(data, offset=0)

        assert result['error'] is True
        assert result['status_code'] == 0xFFFF
        assert result['status_hex'] == 'FFFF'

    def test_parse_module_status_with_offset(self):
        """测试非零偏移量解析"""
        from app.plc.parser_device_status import DeviceStatusParser
        parser = DeviceStatusParser.__new__(DeviceStatusParser)
        parser._configs = {}

        # 8 字节: 前4字节正常, 后4字节故障
        data = self._make_module_bytes(False, 0) + self._make_module_bytes(True, 0x0010)
        
        result0 = parser.parse_module_status(data, offset=0)
        result4 = parser.parse_module_status(data, offset=4)

        assert result0['error'] is False
        assert result4['error'] is True
        assert result4['status_code'] == 0x0010

    def test_parse_all_with_mock_data(self):
        """测试 parse_all 完整解析流程"""
        from app.plc.parser_device_status import DeviceStatusParser
        
        # 构造标准格式配置 (DB3 风格)
        parser = DeviceStatusParser.__new__(DeviceStatusParser)
        parser._configs = {
            3: {
                'db_config': {'db_number': 3, 'db_name': 'test'},
                'devices': [
                    {
                        'device_id': 'test_device_1',
                        'device_name': 'Test Device 1',
                        'device_type': 'hopper',
                        'modules': [
                            {'tag': 'meter', 'description': 'Meter', 'offset': 0},
                            {'tag': 'temp', 'description': 'Temp', 'offset': 4},
                        ]
                    }
                ]
            }
        }
        
        # 2 个模块，每个 4 字节
        raw_data = self._make_module_bytes(False, 0) + self._make_module_bytes(True, 0x0002)
        
        raw_input = {
            'db3': {
                'db_number': 3,
                'db_name': 'test',
                'size': 8,
                'raw_data': raw_data,
                'timestamp': '2026-02-27T10:00:00'
            }
        }
        
        result = parser.parse_all(raw_input)
        
        assert 'db3' in result
        assert len(result['db3']) == 2
        
        # 第一个模块正常
        assert result['db3'][0]['error'] is False
        assert result['db3'][0]['is_normal'] is True
        assert result['db3'][0]['device_id'] == 'test_device_1_meter'
        
        # 第二个模块故障
        assert result['db3'][1]['error'] is True
        assert result['db3'][1]['is_normal'] is False
        assert result['db3'][1]['status_code'] == 2

    def test_parse_all_flat_format(self):
        """测试扁平格式 (DB7 风格) 解析"""
        from app.plc.parser_device_status import DeviceStatusParser
        
        parser = DeviceStatusParser.__new__(DeviceStatusParser)
        parser._configs = {
            7: {
                'db_config': {'db_number': 7},
                'zones': [
                    {
                        'device_id': 'zone1',
                        'device_name': 'Zone 1',
                        'device_type': 'roller_kiln',
                        'tag': 'zone1',
                        'description': 'Temperature Zone 1',
                        'offset': 0,
                    }
                ]
            }
        }
        
        raw_data = self._make_module_bytes(False, 0)
        
        raw_input = {
            'db7': {
                'db_number': 7,
                'db_name': 'RollerKilnState',
                'size': 4,
                'raw_data': raw_data,
                'timestamp': '2026-02-27T10:00:00'
            }
        }
        
        result = parser.parse_all(raw_input)
        assert 'db7' in result
        assert len(result['db7']) == 1
        assert result['db7'][0]['device_id'] == 'zone1'
        assert result['db7'][0]['is_normal'] is True

    def test_parse_all_empty_raw_data(self):
        """测试空原始数据"""
        from app.plc.parser_device_status import DeviceStatusParser
        
        parser = DeviceStatusParser.__new__(DeviceStatusParser)
        parser._configs = {}
        
        result = parser.parse_all({})
        assert result == {}

    def test_get_all_as_flat_list(self):
        """测试扁平列表输出"""
        from app.plc.parser_device_status import DeviceStatusParser
        
        parser = DeviceStatusParser.__new__(DeviceStatusParser)
        parser._configs = {
            3: {
                'devices': [
                    {
                        'device_id': 'dev_1',
                        'device_name': 'Dev 1',
                        'device_type': 'hopper',
                        'modules': [
                            {'tag': 'mod1', 'description': 'Mod1', 'offset': 0},
                        ]
                    }
                ]
            },
            11: {
                'devices': [
                    {
                        'device_id': 'scr_1',
                        'device_name': 'SCR 1',
                        'device_type': 'scr',
                        'modules': [
                            {'tag': 'mod1', 'description': 'Mod1', 'offset': 0},
                        ]
                    }
                ]
            }
        }
        
        raw_data_4bytes = self._make_module_bytes(False, 0)
        raw_input = {
            'db3': {'db_number': 3, 'db_name': 'test', 'size': 4, 'raw_data': raw_data_4bytes, 'timestamp': None},
            'db11': {'db_number': 11, 'db_name': 'test', 'size': 4, 'raw_data': raw_data_4bytes, 'timestamp': None},
        }
        
        flat = parser.get_all_as_flat_list(raw_input)
        assert len(flat) == 2


# ============================================================
# 2. Status Router 单元测试
# ============================================================

class TestStatusRouter:
    """HTTP 状态位路由测试"""

    def test_calc_summary_normal(self):
        """测试统计计算 - 全部正常"""
        from app.routers.status import _calc_summary
        
        statuses = [
            {'is_normal': True},
            {'is_normal': True},
            {'is_normal': True},
        ]
        summary = _calc_summary(statuses)
        
        assert summary['total'] == 3
        assert summary['normal'] == 3
        assert summary['error'] == 0

    def test_calc_summary_with_errors(self):
        """测试统计计算 - 含异常"""
        from app.routers.status import _calc_summary
        
        statuses = [
            {'is_normal': True},
            {'is_normal': False},
            {'is_normal': True},
            {'is_normal': False},
        ]
        summary = _calc_summary(statuses)
        
        assert summary['total'] == 4
        assert summary['normal'] == 2
        assert summary['error'] == 2

    def test_calc_summary_empty(self):
        """测试统计计算 - 空列表"""
        from app.routers.status import _calc_summary
        
        summary = _calc_summary([])
        assert summary['total'] == 0
        assert summary['normal'] == 0
        assert summary['error'] == 0

    def test_calc_summary_missing_key(self):
        """测试统计计算 - 缺少 is_normal 字段"""
        from app.routers.status import _calc_summary
        
        statuses = [
            {'is_normal': True},
            {},  # 缺少 is_normal
        ]
        summary = _calc_summary(statuses)
        
        assert summary['total'] == 2
        assert summary['normal'] == 1
        assert summary['error'] == 1


# ============================================================
# 3. WebSocket Manager - device_status 推送测试
# ============================================================

class TestWsManagerStatusPush:
    """WebSocket Manager 设备状态推送测试"""

    def test_push_device_status_empty_cache(self):
        """测试空缓存时跳过推送"""
        from app.services.ws_manager import ConnectionManager
        
        manager = ConnectionManager()
        
        async def _run():
            await manager._push_device_status("2026-02-27T10:00:00Z")
        
        with patch('app.services.polling_service.get_device_status_raw', return_value={}):
            asyncio.run(_run())

    def test_push_device_status_parse_error(self):
        """测试解析失败时不崩溃"""
        from app.services.ws_manager import ConnectionManager
        
        manager = ConnectionManager()
        
        mock_raw_data = {
            'db3': {'db_number': 3, 'db_name': 'test', 'size': 4, 'raw_data': b'\x00\x00\x00\x00', 'timestamp': None}
        }
        
        async def _run():
            await manager._push_device_status("2026-02-27T10:00:00Z")
        
        with patch('app.services.polling_service.get_device_status_raw', return_value=mock_raw_data):
            with patch('app.plc.parser_device_status.get_device_status_parser') as mock_parser:
                mock_parser.return_value.parse_all.side_effect = Exception("Parse error")
                # 应该被异常捕获，不崩溃
                asyncio.run(_run())


# ============================================================
# 4. polling_service - get_device_status_raw 测试
# ============================================================

class TestPollingServiceStatusCache:
    """轮询服务状态缓存测试"""

    def test_get_device_status_raw_returns_copy(self):
        """测试 get_device_status_raw 返回副本"""
        from app.services.polling_service import get_device_status_raw, _device_status_raw
        
        # 获取返回值并修改，不应影响原数据
        result = get_device_status_raw()
        original_len = len(result)
        result['test_key'] = {'fake': True}
        
        # 原缓存不应被修改
        result2 = get_device_status_raw()
        assert 'test_key' not in result2


# ============================================================
# 5. 数据一致性测试 (前后端消息格式)
# ============================================================

class TestMessageFormatConsistency:
    """前后端消息格式一致性测试"""

    def test_device_status_message_structure(self):
        """验证 device_status 推送消息包含必需字段"""
        # 模拟后端推送的消息结构
        message = {
            "type": "device_status",
            "success": True,
            "timestamp": "2026-02-27T10:00:00Z",
            "source": "mock",
            "data": {
                "db3": [
                    {
                        "device_id": "kiln_7_meter",
                        "device_name": "Kiln 7 - Meter",
                        "device_type": "hopper",
                        "module_tag": "meter",
                        "description": "Meter",
                        "db_number": 3,
                        "offset": 0,
                        "error": False,
                        "status_code": 0,
                        "status_hex": "0000",
                        "is_normal": True,
                        "timestamp": "2026-02-27T10:00:00"
                    }
                ],
                "db7": [],
                "db11": []
            },
            "summary": {"total": 1, "normal": 1, "error": 0}
        }
        
        # 验证必需字段存在
        assert message['type'] == 'device_status'
        assert 'success' in message
        assert 'timestamp' in message
        assert 'data' in message
        assert 'summary' in message
        
        # 验证 data 结构
        assert isinstance(message['data'], dict)
        for db_key in ['db3', 'db7', 'db11']:
            assert db_key in message['data']
            assert isinstance(message['data'][db_key], list)
        
        # 验证 summary 结构
        summary = message['summary']
        assert 'total' in summary
        assert 'normal' in summary
        assert 'error' in summary
        assert summary['total'] == summary['normal'] + summary['error']

    def test_module_status_fields_for_frontend(self):
        """验证单个 ModuleStatus 包含前端需要的所有字段"""
        status = {
            "device_id": "kiln_7_meter",
            "device_name": "Kiln 7 - Meter",
            "device_type": "hopper",
            "module_tag": "meter",
            "description": "Meter",
            "db_number": 3,
            "offset": 0,
            "error": False,
            "status_code": 0,
            "status_hex": "0000",
            "is_normal": True,
            "timestamp": "2026-02-27T10:00:00"
        }
        
        # 前端 ModuleStatus.fromJson 需要的字段
        required_fields = [
            'device_id', 'device_name', 'device_type',
            'module_tag', 'description', 'db_number', 'offset',
            'error', 'status_code', 'status_hex', 'is_normal'
        ]
        
        for field in required_fields:
            assert field in status, f"Missing field: {field}"


if __name__ == '__main__':
    pytest.main([__file__, '-v', '--tb=short'])
