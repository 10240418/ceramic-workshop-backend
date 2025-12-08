# ============================================================
# 文件说明: s7_client.py - Siemens S7-1200 PLC 通信客户端
# ============================================================
# 方法列表:
# 1. connect()              - 连接到PLC
# 2. disconnect()           - 断开PLC连接
# 3. read_db_block()        - 读取整个DB块数据
# 4. is_connected()         - 检查连接状态
# ============================================================

import snap7
from snap7.util import get_real, get_int, get_dint, get_bool
from typing import Optional
from config import get_settings


# ------------------------------------------------------------
# S7Client - S7 PLC 客户端
# ------------------------------------------------------------
class S7Client:
    """Siemens S7-1200 PLC 客户端"""
    
    def __init__(self, ip: str, rack: int = 0, slot: int = 1, timeout_ms: int = 5000):
        """
        初始化S7客户端
        
        Args:
            ip: PLC IP地址
            rack: 机架号 (S7-1200固定为0)
            slot: 插槽号 (S7-1200固定为1)
            timeout_ms: 超时时间 (毫秒)
        """
        self.ip = ip
        self.rack = rack
        self.slot = slot
        self.timeout_ms = timeout_ms
        self.client: Optional[snap7.client.Client] = None
    
    # ------------------------------------------------------------
    # 1. connect() - 连接到PLC
    # ------------------------------------------------------------
    def connect(self) -> bool:
        """
        连接到PLC
        
        Returns:
            bool: 连接成功返回True
        
        Raises:
            ConnectionError: 连接失败时抛出
        """
        try:
            if self.client is None:
                self.client = snap7.client.Client()
            
            self.client.connect(self.ip, self.rack, self.slot)
            
            if not self.client.get_connected():
                raise ConnectionError(f"无法连接到PLC {self.ip}")
            
            return True
            
        except Exception as e:
            raise ConnectionError(f"PLC连接失败: {e}")
    
    # ------------------------------------------------------------
    # 2. disconnect() - 断开PLC连接
    # ------------------------------------------------------------
    def disconnect(self) -> None:
        """断开PLC连接"""
        if self.client and self.client.get_connected():
            self.client.disconnect()
    
    # ------------------------------------------------------------
    # 3. read_db_block() - 读取整个DB块数据
    # ------------------------------------------------------------
    def read_db_block(self, db_number: int, start: int, size: int) -> bytes:
        """
        读取整个DB块数据 (批量读取以提高效率)
        
        Args:
            db_number: DB块编号
            start: 起始字节地址
            size: 读取字节数
        
        Returns:
            bytes: 读取的字节数据
        
        Raises:
            ConnectionError: PLC未连接
            Exception: 读取失败
        """
        if not self.client or not self.client.get_connected():
            raise ConnectionError("PLC未连接")
        
        try:
            return self.client.db_read(db_number, start, size)
        except Exception as e:
            raise Exception(f"读取DB{db_number}失败: {e}")
    
    # ------------------------------------------------------------
    # 4. is_connected() - 检查连接状态
    # ------------------------------------------------------------
    def is_connected(self) -> bool:
        """检查PLC是否已连接"""
        return self.client is not None and self.client.get_connected()


# ------------------------------------------------------------
# 全局客户端实例
# ------------------------------------------------------------
_s7_client: Optional[S7Client] = None


def get_s7_client() -> S7Client:
    """获取S7客户端单例"""
    global _s7_client
    if _s7_client is None:
        settings = get_settings()
        _s7_client = S7Client(
            ip=settings.plc_ip,
            rack=settings.plc_rack,
            slot=settings.plc_slot,
            timeout_ms=settings.plc_timeout  # config.py uses plc_timeout not plc_timeout_ms
        )
    return _s7_client
