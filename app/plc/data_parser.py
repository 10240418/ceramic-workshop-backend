# ============================================================
# 文件说明: data_parser.py - PLC数据解析器 (Big Endian)
# ============================================================
# 方法列表:
# 1. parse_real()           - 解析REAL (32位浮点数)
# 2. parse_int()            - 解析INT (16位有符号整数)
# 3. parse_dint()           - 解析DINT (32位有符号整数)
# 4. parse_bool()           - 解析BOOL (位)
# 5. parse_word()           - 解析WORD (16位无符号整数)
# 6. parse_dword()          - 解析DWORD (32位无符号整数)
# 7. parse_sensor_value_simple() - 简化版解析 (YAML配置)
# ============================================================

import snap7.util as s7util
from typing import Any


# ------------------------------------------------------------
# 1. parse_real() - 解析REAL (32位浮点数)
# ------------------------------------------------------------
def parse_real(data: bytes, offset: int) -> float:
    """
    解析S7 REAL类型 (Big Endian 4字节浮点数)
    
    Args:
        data: 字节数组
        offset: 字节偏移量
    
    Returns:
        float: 解析后的浮点数
    """
    return s7util.get_real(data, offset)


# ------------------------------------------------------------
# 2. parse_int() - 解析INT (16位有符号整数)
# ------------------------------------------------------------
def parse_int(data: bytes, offset: int) -> int:
    """
    解析S7 INT类型 (Big Endian 2字节有符号整数)
    
    Args:
        data: 字节数组
        offset: 字节偏移量
    
    Returns:
        int: 解析后的整数
    """
    return s7util.get_int(data, offset)


# ------------------------------------------------------------
# 3. parse_dint() - 解析DINT (32位有符号整数)
# ------------------------------------------------------------
def parse_dint(data: bytes, offset: int) -> int:
    """
    解析S7 DINT类型 (Big Endian 4字节有符号整数)
    
    Args:
        data: 字节数组
        offset: 字节偏移量
    
    Returns:
        int: 解析后的整数
    """
    return s7util.get_dint(data, offset)


# ------------------------------------------------------------
# 4. parse_bool() - 解析BOOL (位)
# ------------------------------------------------------------
def parse_bool(data: bytes, byte_offset: int, bit_offset: int) -> bool:
    """
    解析S7 BOOL类型 (特定位)
    
    Args:
        data: 字节数组
        byte_offset: 字节偏移量
        bit_offset: 位偏移量 (0-7)
    
    Returns:
        bool: 解析后的布尔值
    """
    return s7util.get_bool(data, byte_offset, bit_offset)


# ------------------------------------------------------------
# 5. parse_word() - 解析WORD (16位无符号整数)
# ------------------------------------------------------------
def parse_word(data: bytes, offset: int) -> int:
    """
    解析S7 WORD类型 (Big Endian 2字节无符号整数)
    
    Args:
        data: 字节数组
        offset: 字节偏移量
    
    Returns:
        int: 解析后的无符号整数
    """
    return s7util.get_word(data, offset)


# ------------------------------------------------------------
# 6. parse_dword() - 解析DWORD (32位无符号整数)
# ------------------------------------------------------------
def parse_dword(data: bytes, offset: int) -> int:
    """
    解析S7 DWORD类型 (Big Endian 4字节无符号整数)
    
    Args:
        data: 字节数组
        offset: 字节偏移量
    
    Returns:
        int: 解析后的无符号整数
    """
    return s7util.get_dword(data, offset)


# ------------------------------------------------------------
# 7. parse_sensor_value_simple() - 简化版解析 (YAML配置)
# ------------------------------------------------------------
def parse_sensor_value_simple(data: bytes, data_type: str, scale: float = 1.0) -> float:
    """
    简化版数据解析函数 (用于YAML配置)
    
    Args:
        data: 字节数组
        data_type: 数据类型 ('REAL', 'INT', 'DINT', 'WORD', 'DWORD', 'BOOL')
        scale: 缩放系数 (默认1.0)
    
    Returns:
        float: 解析后的数值 (应用缩放系数)
    """
    raw_value: Any
    
    if data_type == 'REAL':
        raw_value = parse_real(data, 0)
    elif data_type == 'INT':
        raw_value = parse_int(data, 0)
    elif data_type == 'DINT':
        raw_value = parse_dint(data, 0)
    elif data_type == 'WORD':
        raw_value = parse_word(data, 0)
    elif data_type == 'DWORD':
        raw_value = parse_dword(data, 0)
    elif data_type == 'BOOL':
        raw_value = 1.0 if parse_bool(data, 0, 0) else 0.0
    else:
        raise ValueError(f"不支持的数据类型: {data_type}")
    
    # 应用缩放系数
    return float(raw_value) * scale
