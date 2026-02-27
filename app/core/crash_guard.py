# ============================================================
# 文件说明: crash_guard.py - 进程崩溃防护与诊断
# ============================================================
# 功能:
# 1. install() - 安装全局崩溃防护（信号处理 + 异常钩子）
# 2. _crash_log() - 写入崩溃日志到 logs/crash.log
# 3. safe_import_influxdb() - 安全导入 influxdb_client（防 numpy 卡死）
# ============================================================

import sys
import os
import signal
import logging
import threading
import traceback
from pathlib import Path
from datetime import datetime

logger = logging.getLogger(__name__)

# 崩溃日志路径
_CRASH_LOG = Path(__file__).resolve().parents[2] / "logs" / "crash.log"


# ------------------------------------------------------------
# 1. _crash_log() - 写入崩溃日志
# ------------------------------------------------------------
def _crash_log(category: str, message: str) -> None:
    """写入崩溃日志到 logs/crash.log（独立于 logging 模块，保证写入）"""
    try:
        _CRASH_LOG.parent.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        entry = f"[{timestamp}] [{category}] {message}\n"
        with open(_CRASH_LOG, "a", encoding="utf-8") as f:
            f.write(entry)
        # 同时尝试 print 到控制台
        print(entry.rstrip(), file=sys.__stderr__ or sys.stderr)
    except Exception:
        pass


# ------------------------------------------------------------
# 2. install() - 安装全局崩溃防护
# ------------------------------------------------------------
def install() -> None:
    """安装全局崩溃防护钩子，在进程启动最早期调用

    包含:
    - sys.excepthook: 捕获主线程未捕获异常
    - threading.excepthook: 捕获子线程未捕获异常
    - signal handlers: 捕获 SIGTERM / SIGINT / SIGBREAK (Windows)
    - atexit: 记录正常退出
    """

    # --- 2.1 主线程未捕获异常 ---
    _original_excepthook = sys.excepthook

    def _excepthook(exc_type, exc_value, exc_tb):
        tb_str = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
        _crash_log("UNCAUGHT_EXCEPTION", f"{exc_type.__name__}: {exc_value}\n{tb_str}")
        logger.critical(f"[CRASH] 未捕获异常: {exc_type.__name__}: {exc_value}", exc_info=(exc_type, exc_value, exc_tb))
        # 调用原始钩子
        _original_excepthook(exc_type, exc_value, exc_tb)

    sys.excepthook = _excepthook

    # --- 2.2 子线程未捕获异常 ---
    def _thread_excepthook(args):
        tb_str = "".join(traceback.format_exception(args.exc_type, args.exc_value, args.exc_traceback))
        thread_name = args.thread.name if args.thread else "unknown"
        _crash_log("THREAD_CRASH", f"Thread={thread_name} | {args.exc_type.__name__}: {args.exc_value}\n{tb_str}")
        logger.critical(f"[CRASH] 线程 {thread_name} 崩溃: {args.exc_type.__name__}: {args.exc_value}")

    threading.excepthook = _thread_excepthook

    # --- 2.3 信号处理 ---
    def _make_signal_handler(sig_name: str):
        def handler(signum, frame):
            stack = "".join(traceback.format_stack(frame)) if frame else "N/A"
            _crash_log("SIGNAL", f"收到信号 {sig_name} (signum={signum})\n调用栈:\n{stack}")
            logger.warning(f"[SIGNAL] 收到 {sig_name}，进程即将退出")
            # 对 SIGINT 抛出 KeyboardInterrupt 让 uvicorn 优雅关闭
            if signum == signal.SIGINT:
                raise KeyboardInterrupt
            sys.exit(128 + signum)
        return handler

    # SIGTERM: 外部 kill / docker stop
    signal.signal(signal.SIGTERM, _make_signal_handler("SIGTERM"))

    # SIGINT: Ctrl+C
    signal.signal(signal.SIGINT, _make_signal_handler("SIGINT"))

    # Windows 专用: SIGBREAK (Ctrl+Break / 控制台关闭)
    if hasattr(signal, "SIGBREAK"):
        signal.signal(signal.SIGBREAK, _make_signal_handler("SIGBREAK"))

    # --- 2.4 atexit: 正常退出记录 ---
    import atexit

    def _on_exit():
        _crash_log("EXIT", f"进程正常退出 (PID={os.getpid()})")

    atexit.register(_on_exit)

    _crash_log("STARTUP", f"崩溃防护已安装 (PID={os.getpid()})")


# ------------------------------------------------------------
# 3. safe_import_influxdb() - 安全导入 influxdb_client
# ------------------------------------------------------------
def safe_import_influxdb(timeout_sec: int = 30) -> bool:
    """在超时保护下尝试导入 influxdb_client (含 numpy)

    如果导入卡死（numpy .pyc 损坏等），会:
    1. 清理 numpy 的 __pycache__ 目录
    2. 返回 False 提示需要重试

    Args:
        timeout_sec: 导入超时秒数

    Returns:
        True=导入成功, False=导入超时/失败
    """
    import_result = {"success": False, "error": None}

    def _do_import():
        try:
            import importlib
            # 先测试 numpy
            importlib.import_module("numpy")
            # 再测试 influxdb_client
            importlib.import_module("influxdb_client")
            import_result["success"] = True
        except Exception as e:
            import_result["error"] = str(e)

    t = threading.Thread(target=_do_import, daemon=True, name="import-guard")
    t.start()
    t.join(timeout=timeout_sec)

    if t.is_alive():
        # 导入卡死，尝试清理 numpy __pycache__
        _crash_log("IMPORT_HANG", f"influxdb_client/numpy 导入超时 ({timeout_sec}s)")
        _cleanup_numpy_pycache()
        return False

    if not import_result["success"]:
        _crash_log("IMPORT_ERROR", f"influxdb_client 导入失败: {import_result['error']}")
        return False

    return True


def _cleanup_numpy_pycache() -> None:
    """清理 numpy 的 __pycache__ 目录，解决 .pyc 损坏导致的导入卡死"""
    try:
        import numpy
        numpy_dir = Path(numpy.__file__).parent
    except Exception:
        # numpy 连导入都失败，尝试从 site-packages 查找
        for p in sys.path:
            candidate = Path(p) / "numpy"
            if candidate.is_dir():
                numpy_dir = candidate
                break
        else:
            _crash_log("CLEANUP", "无法定位 numpy 目录，跳过清理")
            return

    pycache_dirs = list(numpy_dir.rglob("__pycache__"))
    cleaned = 0
    for cache_dir in pycache_dirs:
        try:
            for pyc_file in cache_dir.glob("*.pyc"):
                pyc_file.unlink()
                cleaned += 1
        except Exception:
            pass

    _crash_log("CLEANUP", f"已清理 numpy __pycache__: {cleaned} 个 .pyc 文件 ({len(pycache_dirs)} 个目录)")
