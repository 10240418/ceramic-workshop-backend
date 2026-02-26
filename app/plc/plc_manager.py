# ============================================================
# 文件说明: plc_manager.py - PLC 长连接管理器
# ============================================================
# 功能:
#   1. 维护 PLC 长连接（避免频繁连接/断开）
#   2. 自动重连机制
#   3. 连接健康检查
#   4. 线程安全读写
# ============================================================

import threading
import time
import logging
from typing import Optional, Tuple
from datetime import datetime, timezone

from config import get_settings
from app.plc.snap7_compat import ensure_snap7_version

settings = get_settings()
logger = logging.getLogger(__name__)

# 尝试导入 snap7
try:
    import snap7
    from snap7.util import get_real, get_int
    try:
        from snap7.type import Parameter as S7Parameter
    except Exception:
        S7Parameter = None
    SNAP7_AVAILABLE = True
except ImportError:
    snap7 = None
    S7Parameter = None
    SNAP7_AVAILABLE = False
    logger.warning("snap7 未安装，使用模拟模式")


class PLCManager:
    """PLC 长连接管理器（单例模式）"""
    
    _instance: Optional['PLCManager'] = None
    _lock = threading.Lock()
    
    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        
        self._initialized = True
        
        # 连接配置
        self._ip: str = settings.plc_ip
        self._rack: int = settings.plc_rack
        self._slot: int = settings.plc_slot
        self._timeout_ms: int = settings.plc_timeout
        
        # 连接状态
        self._client: Optional['snap7.client.Client'] = None
        self._connected: bool = False
        self._last_connect_time: Optional[datetime] = None
        self._last_read_time: Optional[datetime] = None
        self._connect_count: int = 0
        self._error_count: int = 0
        self._consecutive_error_count: int = 0  # [FIX] 连续错误计数
        self._last_error: str = ""
        
        # 线程锁
        self._rw_lock = threading.Lock()
        
        # 重连配置
        self._reconnect_interval: float = 5.0  # 重连间隔（秒）
        self._max_reconnect_attempts: int = 3  # 最大重连次数
        self._health_check_interval: float = 30.0  # 健康检查间隔
        self._max_consecutive_errors: int = 10  # [FIX] 连续错误达到此值则强制重连
        
        if SNAP7_AVAILABLE and not settings.mock_mode:
            valid, message = ensure_snap7_version()
            if not valid:
                self._last_error = message
                logger.error(f"[PLC] {message}")
            else:
                logger.info(f"[PLC] {message}")

        logger.info(f"[PLC] PLC Manager 初始化: {self._ip}:{self._rack}/{self._slot}")
    
    def update_config(self, ip: str = None, rack: int = None, slot: int = None, timeout_ms: int = None):
        """更新 PLC 连接配置（需要重连生效）"""
        with self._rw_lock:
            if ip:
                self._ip = ip
            if rack is not None:
                self._rack = rack
            if slot is not None:
                self._slot = slot
            if timeout_ms is not None:
                self._timeout_ms = timeout_ms
            
            # 断开旧连接
            self._disconnect_internal()
            logger.info(f"[PLC] PLC 配置已更新: {self._ip}:{self._rack}/{self._slot}")
    
    def connect(self) -> Tuple[bool, str]:
        """
        连接到 PLC（如果已连接则跳过）
        
        Returns:
            (success, error_message)
        """
        with self._rw_lock:
            return self._connect_internal()
    
    def _connect_internal(self) -> Tuple[bool, str]:
        """内部连接方法（不加锁）"""
        if self._connected and self._client:
            # 检查连接是否仍然有效
            try:
                if SNAP7_AVAILABLE and self._client.get_connected():
                    return (True, "")
            except Exception:
                pass
            self._connected = False
        
        if not SNAP7_AVAILABLE:
            # 模拟模式
            self._connected = True
            self._last_connect_time = datetime.now(timezone.utc)
            self._connect_count += 1
            return (True, "模拟模式")

        if not settings.mock_mode:
            valid, message = ensure_snap7_version()
            if not valid:
                self._error_count += 1
                self._last_error = message
                logger.error(f"[PLC] {message}")
                return (False, message)
        
        try:
            if self._client is None:
                self._client = snap7.client.Client()
            
            # 设置超时
            if S7Parameter is not None:
                self._client.set_param(S7Parameter.PingTimeout, self._timeout_ms)
            else:
                self._client.set_param(snap7.types.PingTimeout, self._timeout_ms)
            
            # 连接
            self._client.connect(self._ip, self._rack, self._slot)
            
            if not self._client.get_connected():
                self._error_count += 1
                self._last_error = "连接后状态检查失败"
                return (False, self._last_error)
            
            self._connected = True
            self._last_connect_time = datetime.now(timezone.utc)
            self._connect_count += 1
            self._error_count = 0
            logger.info(f"[PLC] PLC 已连接 ({self._ip}) [第 {self._connect_count} 次]")
            return (True, "")
        
        except Exception as e:
            self._connected = False
            self._error_count += 1
            self._last_error = str(e)
            logger.error(f"[PLC] PLC 连接失败: {e}", exc_info=True)
            return (False, self._last_error)
    
    def disconnect(self):
        """断开 PLC 连接"""
        with self._rw_lock:
            self._disconnect_internal()
    
    def _disconnect_internal(self):
        """内部断开方法（不加锁）"""
        if self._client:
            try:
                if SNAP7_AVAILABLE and self._client.get_connected():
                    self._client.disconnect()
            except Exception:
                pass
        self._connected = False
        logger.info("[PLC] PLC 已断开")
    
    def read_db(self, db_number: int, start: int, size: int) -> Tuple[bool, bytes, str]:
        """
        读取 DB 块数据（带自动重连）
        
        Args:
            db_number: DB 块号
            start: 起始偏移
            size: 读取字节数
        
        Returns:
            (success, data, error_message)
        """
        with self._rw_lock:
            # [FIX] 检查连续错误，强制重连
            if self._consecutive_error_count >= self._max_consecutive_errors:
                logger.warning(f"[PLC] 连续 {self._consecutive_error_count} 次错误，强制重连 PLC...")
                self._disconnect_internal()
                self._consecutive_error_count = 0
            
            # 确保连接
            if not self._connected:
                success, err = self._connect_internal()
                if not success:
                    self._consecutive_error_count += 1
                    return (False, b"", f"连接失败: {err}")
            
            # 模拟模式
            if not SNAP7_AVAILABLE:
                self._last_read_time = datetime.now(timezone.utc)
                self._consecutive_error_count = 0
                return (True, bytes(size), "模拟数据")
            
            # 读取数据（带重试）
            for attempt in range(self._max_reconnect_attempts):
                try:
                    data = self._client.db_read(db_number, start, size)
                    self._last_read_time = datetime.now(timezone.utc)
                    self._error_count = 0
                    self._consecutive_error_count = 0  # [FIX] 成功后重置
                    return (True, bytes(data), "")
                
                except Exception as e:
                    self._error_count += 1
                    self._consecutive_error_count += 1
                    self._last_error = str(e)
                    
                    # 尝试重连
                    if attempt < self._max_reconnect_attempts - 1:
                        logger.warning(f"[PLC] DB{db_number} 读取失败 (尝试 {attempt+1}/{self._max_reconnect_attempts}): {e}")
                        self._disconnect_internal()
                        time.sleep(0.5)
                        success, _ = self._connect_internal()
                        if not success:
                            continue
                    else:
                        logger.error(
                            f"[PLC] DB{db_number} 读取失败 (已重试 {self._max_reconnect_attempts} 次): {e}",
                            exc_info=True,
                        )
            
            return (False, b"", self._last_error)
    
    def is_connected(self) -> bool:
        """检查连接状态"""
        with self._rw_lock:
            if not self._connected:
                return False
            if not SNAP7_AVAILABLE:
                return True
            try:
                return self._client and self._client.get_connected()
            except Exception:
                return False
    
    def get_status(self, check_realtime: bool = True) -> dict:
        """获取连接状态信息
        
        Args:
            check_realtime: 是否实时检测 PLC 连接状态（默认 True）
                           如果为 False，只返回内部状态变量
        """
        with self._rw_lock:
            # 实时检测连接状态
            if check_realtime:
                actual_connected = self._check_connection_realtime()
            else:
                actual_connected = self._connected
            
            return {
                "connected": actual_connected,
                "internal_state": self._connected,  # 内部状态（调试用）
                "ip": self._ip,
                "rack": self._rack,
                "slot": self._slot,
                "connect_count": self._connect_count,
                "error_count": self._error_count,
                "last_error": self._last_error,
                "last_connect_time": self._last_connect_time.isoformat() if self._last_connect_time else None,
                "last_read_time": self._last_read_time.isoformat() if self._last_read_time else None,
                "snap7_available": SNAP7_AVAILABLE
            }
    
    def _check_connection_realtime(self) -> bool:
        """实时检测 PLC 连接状态（不加锁，内部调用）"""
        if not self._connected:
            return False
        
        if not SNAP7_AVAILABLE:
            return True  # 模拟模式
        
        try:
            if self._client and self._client.get_connected():
                return True
            else:
                # 连接已断开，更新内部状态
                self._connected = False
                self._last_error = "连接已断开（实时检测）"
                return False
        except Exception as e:
            # 检测过程出错，认为断开
            self._connected = False
            self._last_error = f"连接检测失败: {str(e)}"
            return False
    
    def health_check(self) -> Tuple[bool, str]:
        """
        健康检查（尝试读取少量数据）
        
        Returns:
            (healthy, message)
        """
        # 尝试读取 DB8 的前 4 字节
        success, _, err = self.read_db(8, 0, 4)
        if success:
            return (True, "PLC 响应正常")
        return (False, err)


# 全局单例
_plc_manager: Optional[PLCManager] = None


def get_plc_manager() -> PLCManager:
    """获取 PLC 管理器单例"""
    global _plc_manager
    if _plc_manager is None:
        _plc_manager = PLCManager()
    return _plc_manager


def reset_plc_manager() -> None:
    """重置 PLC 管理器（用于配置更新后）"""
    global _plc_manager
    if _plc_manager is not None:
        _plc_manager.disconnect()
        _plc_manager = None
