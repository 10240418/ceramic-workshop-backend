# ============================================================
# 文件说明: tray_app.py - 磨料车间后端系统托盘应用
# ============================================================
# 功能:
# 1. 系统托盘图标（绿=运行，红=停止）
# 2. 右键菜单：启动/停止/强制停止/打开日志/退出
# 3. 日志窗口：实时追踪 logs/server.log
# 4. 单例保护：防止重复启动
# 5. 打包后作为 PyInstaller 入口，内嵌 uvicorn 线程运行 FastAPI
# ============================================================

import os
import sys
import threading
import time
from pathlib import Path
from typing import Optional

import psutil
import uvicorn
from PyQt5.QtCore import QTimer, Qt
from PyQt5.QtGui import QColor, QFont, QIcon, QPainter, QPixmap
from PyQt5.QtNetwork import QLocalServer, QLocalSocket
from PyQt5.QtWidgets import (
    QAction,
    QApplication,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QStatusBar,
    QSystemTrayIcon,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

# ============================================================
# [FIX] PyInstaller frozen exe: sys.stdout/stderr 可能为 None
# ============================================================
if sys.stdout is None:
    sys.stdout = open(os.devnull, "w", encoding="utf-8")
if sys.stderr is None:
    sys.stderr = open(os.devnull, "w", encoding="utf-8")

# 检测是否在打包环境中运行
IS_FROZEN = getattr(sys, "frozen", False)

# 获取工作目录（打包后为 exe 所在目录，开发模式为项目根目录）
if IS_FROZEN:
    WORKDIR = Path(sys.executable).parent
else:
    WORKDIR = Path(__file__).resolve().parents[1]

# 将项目根目录加入 sys.path（确保能 import main, config 等）
if str(WORKDIR) not in sys.path:
    sys.path.insert(0, str(WORKDIR))

# 切换到工作目录
os.chdir(str(WORKDIR))

try:
    from config import get_settings
    _settings = get_settings()
    HOST = _settings.server_host
    PORT = int(_settings.server_port)
except Exception:
    HOST = os.getenv("SERVER_HOST", "0.0.0.0")
    PORT = int(os.getenv("SERVER_PORT", "8080"))

LOG_DIR = WORKDIR / "logs"
LOG_FILE = LOG_DIR / "server.log"

# 应用标识
APP_TITLE = "磨料车间监控系统"

# [FIX] 图标路径：打包后在 _internal/assets/，开发模式在 assets/
if IS_FROZEN:
    # 打包后：WorkshopBackend.exe 所在目录/_internal/assets/logo.png
    APP_ICON_PATH = WORKDIR / "_internal" / "assets" / "logo.png"
else:
    # 开发模式：项目根目录/assets/logo.png
    APP_ICON_PATH = WORKDIR / "assets" / "logo.png"

SINGLE_INSTANCE_KEY = "workshop-backend-tray-app"

# 优雅停止超时（秒）
STOP_TIMEOUT = 10


# ============================================================
# 1. ServerController - 管理 uvicorn 线程
# ============================================================
class ServerController:
    """后端服务控制器，在线程中运行 uvicorn FastAPI 服务。"""

    def __init__(self) -> None:
        self._server_thread: Optional[threading.Thread] = None
        self._uvicorn_server: Optional[uvicorn.Server] = None
        self._thread_error: Optional[str] = None
        LOG_DIR.mkdir(parents=True, exist_ok=True)

    # ---------- 公共属性 ----------

    @property
    def is_running(self) -> bool:
        """服务线程存活 且 端口已被监听，则认为正在运行。"""
        if self._server_thread is None or not self._server_thread.is_alive():
            return False
        return self._is_port_in_use(PORT)

    @property
    def pid(self) -> int:
        """返回当前进程 PID（打包模式下 uvicorn 跑在本进程内）。"""
        return os.getpid()

    # ---------- 公共方法 ----------

    def start(self) -> str:
        """启动 uvicorn 服务线程。"""
        if self.is_running:
            return f"服务已在运行 (PID {self.pid})"

        # 如果端口被其他进程占用，先清理
        if self._is_port_in_use(PORT):
            kill_msg = self._kill_port_owner(PORT)
            if kill_msg:
                return kill_msg
            time.sleep(1)
            if self._is_port_in_use(PORT):
                return f"端口 {PORT} 仍被占用，无法启动服务"

        return self._start_in_thread()

    def stop(self) -> str:
        """优雅停止 uvicorn 服务线程。"""
        if not self.is_running:
            return "服务未运行"
        pid = self.pid
        try:
            self._stop_uvicorn()
            return f"服务已停止 (PID {pid})"
        except Exception as exc:
            return f"停止失败: {exc}"

    def force_stop_all(self) -> str:
        """强制杀死本进程所有子进程 + 占用端口的进程。"""
        killed = []
        # 1. 停止 uvicorn 线程
        if self._uvicorn_server is not None:
            self._uvicorn_server.should_exit = True
        # 2. 杀死占用端口的所有进程（包括子进程）
        try:
            for conn in psutil.net_connections(kind="inet"):
                if conn.laddr.port == PORT and conn.status == "LISTEN":
                    try:
                        proc = psutil.Process(conn.pid)
                        for child in proc.children(recursive=True):
                            try:
                                child.kill()
                                killed.append(f"{child.pid}({child.name()})")
                            except Exception:
                                pass
                        proc.kill()
                        killed.append(f"{conn.pid}({proc.name()})")
                    except Exception:
                        pass
        except Exception:
            pass
        self._release()
        if killed:
            return f"已强制停止: {', '.join(killed)}"
        return "已停止所有进程"

    def status_text(self) -> str:
        """人类可读的服务状态。"""
        if not self.is_running:
            return "服务未运行"
        try:
            proc_info = psutil.Process(self.pid)
            return f"服务运行中 (PID {self.pid}) | {proc_info.status()}"
        except Exception:
            return f"服务运行中 (PID {self.pid})"

    # ---------- 私有方法 ----------

    @staticmethod
    def _is_port_in_use(port: int) -> bool:
        try:
            for conn in psutil.net_connections(kind="inet"):
                if conn.laddr.port == port and conn.status == "LISTEN":
                    return True
        except Exception:
            pass
        return False

    @staticmethod
    def _kill_port_owner(port: int) -> Optional[str]:
        try:
            for conn in psutil.net_connections(kind="inet"):
                if conn.laddr.port == port and conn.status == "LISTEN":
                    proc = psutil.Process(conn.pid)
                    for child in proc.children(recursive=True):
                        try:
                            child.kill()
                        except Exception:
                            pass
                    proc.kill()
            return None
        except psutil.AccessDenied:
            return f"无权限清理端口 {port}，请以管理员身份运行"
        except Exception as exc:
            return f"清理端口失败: {exc}"

    def _setup_file_logging(self) -> None:
        """将 print() 与 logging 模块全部重定向到 logs/server.log 文件。

        轮转策略: 50MB 上限, 保留 3 个备份 (总计 ~200MB)
        """
        import logging
        import io

        LOG_DIR.mkdir(parents=True, exist_ok=True)

        MAX_LOG_SIZE = 50 * 1024 * 1024  # 50 MB
        BACKUP_COUNT = 3

        # 1. 自轮转文件流: 按大小自动轮转, 替代无限增长的 open()
        class _RotatingLogFile:
            """按大小自动轮转的日志文件写入器"""

            def __init__(self, path: Path, max_bytes: int, backup_count: int):
                self._path = path
                self._max = max_bytes
                self._backups = backup_count
                self._fh = open(path, "a", encoding="utf-8", buffering=1)
                try:
                    self._size = path.stat().st_size
                except OSError:
                    self._size = 0

            def write(self, s: str) -> int:
                if not s:
                    return 0
                n = len(s.encode("utf-8", errors="replace"))
                if self._size + n > self._max:
                    self._rotate()
                self._fh.write(s)
                self._fh.flush()
                self._size += n
                return len(s)

            def flush(self):
                self._fh.flush()

            def close(self):
                try:
                    self._fh.close()
                except Exception:
                    pass

            def _rotate(self):
                self._fh.close()
                # server.log.3 -> 删除, .2 -> .3, .1 -> .2, server.log -> .1
                for i in range(self._backups, 0, -1):
                    src = self._path.with_name(f"{self._path.name}.{i}")
                    if i == self._backups:
                        try:
                            src.unlink(missing_ok=True)
                        except Exception:
                            pass
                    else:
                        dst = self._path.with_name(f"{self._path.name}.{i + 1}")
                        try:
                            if src.exists():
                                src.rename(dst)
                        except Exception:
                            pass
                try:
                    backup_1 = self._path.with_name(f"{self._path.name}.1")
                    if self._path.exists():
                        self._path.rename(backup_1)
                except Exception:
                    pass
                self._fh = open(self._path, "w", encoding="utf-8", buffering=1)
                self._size = 0

        self._log_fh = _RotatingLogFile(LOG_FILE, MAX_LOG_SIZE, BACKUP_COUNT)

        # 2. Tee 流: 同时写轮转日志文件和原始 stdout/stderr (开发模式下终端可见)
        class _TeeStream(io.TextIOBase):
            def __init__(self, file_stream, original):
                self._f = file_stream
                self._orig = original

            def write(self, s: str) -> int:
                if s:
                    self._f.write(s)
                    if self._orig and not self._orig.closed:
                        try:
                            self._orig.write(s)
                            self._orig.flush()
                        except Exception:
                            pass
                return len(s)

            def flush(self):
                self._f.flush()

        # 3. 重定向 sys.stdout / sys.stderr, 捕获所有输出
        sys.stdout = _TeeStream(self._log_fh, sys.__stdout__)
        sys.stderr = _TeeStream(self._log_fh, sys.__stderr__)

        # 4. logging 模块: 临时 handler (main.py setup_logging 会替换)
        handler = logging.FileHandler(LOG_FILE, mode="a", encoding="utf-8")
        handler.setLevel(logging.INFO)
        handler.setFormatter(
            logging.Formatter(
                "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S",
            )
        )
        root = logging.getLogger()
        root.setLevel(logging.INFO)
        for h in root.handlers[:]:
            root.removeHandler(h)
        root.addHandler(handler)
        # uvicorn 日志统一走 root, 不再单独 addHandler
        for name in ("uvicorn", "uvicorn.error", "uvicorn.access", "fastapi"):
            lg = logging.getLogger(name)
            lg.setLevel(logging.INFO)
            lg.handlers = []
            lg.propagate = True

    def _start_in_thread(self) -> str:
        """在守护线程中启动 uvicorn。"""
        self._thread_error = None
        self._setup_file_logging()

        # [FIX] 每次启动前清除配置缓存，确保重新读取 .env
        # 原因: get_settings() 有 @lru_cache，修改 .env 后 stop→start 否则读不到新值
        try:
            from config import get_settings as _gs
            _gs.cache_clear()
            # 同时清除已缓存的 main 模块，避免 FastAPI app 持有旧 settings 引用
            import sys as _sys
            for _mod in list(_sys.modules.keys()):
                if _mod == "main" or _mod.startswith("app."):
                    del _sys.modules[_mod]
        except Exception:
            pass

        try:
            from main import app as fastapi_app
        except Exception as exc:
            import traceback
            return f"无法加载 FastAPI 应用: {exc}\n{traceback.format_exc()}"

        # [FIX] uvicorn 日志统一走 root logger, 使用统一格式输出
        # uvicorn/uvicorn.access 设置 propagate=True, 不再使用独立 handler
        # 这样所有日志在 server.log 中格式一致:
        # "2026-02-28 00:15:28 | INFO | uvicorn.access | 127.0.0.1 - GET /api/... 200"
        log_config = {
            "version": 1,
            "disable_existing_loggers": False,
            "formatters": {
                "default": {
                    "()": "uvicorn.logging.DefaultFormatter",
                    "fmt": "%(levelprefix)s %(message)s",
                    "use_colors": False,
                },
            },
            "handlers": {
                "default": {"formatter": "default", "class": "logging.StreamHandler", "stream": "ext://sys.stderr"},
            },
            "loggers": {
                "uvicorn": {"handlers": ["default"], "level": "INFO", "propagate": False},
                "uvicorn.error": {"level": "INFO"},
                "uvicorn.access": {"handlers": [], "level": "INFO", "propagate": True},
            },
        }

        config = uvicorn.Config(
            fastapi_app,
            host=str(HOST),
            port=PORT,
            log_level="info",
            log_config=log_config,
            access_log=True,
            timeout_keep_alive=75,
        )
        self._uvicorn_server = uvicorn.Server(config)

        def _run():
            try:
                self._uvicorn_server.run()
            except Exception as exc:
                import traceback
                self._thread_error = f"{exc}\n{traceback.format_exc()}"

        self._server_thread = threading.Thread(target=_run, daemon=True, name="uvicorn-server")
        self._server_thread.start()

        # 等待最多 10 秒，通过端口监听判断启动成功
        for _ in range(100):
            time.sleep(0.1)
            if self._thread_error:
                return f"服务启动失败: {self._thread_error}"
            if not self._server_thread.is_alive():
                return "服务启动失败: 线程已提前退出"
            if self._is_port_in_use(PORT):
                return f"服务已启动 (PID {self.pid})"
        return "服务启动超时，请查看日志"

    def _stop_uvicorn(self) -> None:
        if self._uvicorn_server is not None:
            self._uvicorn_server.should_exit = True
        if self._server_thread is not None:
            self._server_thread.join(timeout=STOP_TIMEOUT)
        self._release()

    def _release(self) -> None:
        self._server_thread = None
        self._uvicorn_server = None
        # 恢复原始 stdout/stderr, 关闭日志文件句柄
        try:
            if sys.stdout is not sys.__stdout__:
                sys.stdout = sys.__stdout__
            if sys.stderr is not sys.__stderr__:
                sys.stderr = sys.__stderr__
        except Exception:
            pass
        try:
            if hasattr(self, '_log_fh') and self._log_fh:
                self._log_fh.close()
                self._log_fh = None
        except Exception:
            pass


# ============================================================
# 2. LogWindow - 日志查看主窗口
# ============================================================
class LogWindow(QMainWindow):
    """实时追踪 logs/server.log 的日志查看窗口。"""

    TAIL_BYTES = 2 * 1024 * 1024  # 初始只加载最后 2MB

    def __init__(self, controller: ServerController) -> None:
        super().__init__()
        self.controller = controller
        self._offset = 0

        self.setWindowTitle(f"{APP_TITLE} - 日志")
        self.resize(980, 640)
        self._set_window_icon()

        # 日志文本框
        self._editor = QPlainTextEdit(self)
        self._editor.setReadOnly(True)
        self._editor.setLineWrapMode(QPlainTextEdit.NoWrap)
        self._editor.setFont(QFont("Consolas", 10))
        self._editor.setMaximumBlockCount(8000)

        # 工具栏按钮
        self._btn_start = QPushButton("启动服务")
        self._btn_stop = QPushButton("停止服务")
        self._btn_force = QPushButton("强制停止")
        self._btn_clear = QPushButton("清空日志")
        self._btn_start.clicked.connect(self._on_start)
        self._btn_stop.clicked.connect(self._on_stop)
        self._btn_force.clicked.connect(self._on_force_stop)
        self._btn_clear.clicked.connect(self._on_clear_log)

        toolbar = QToolBar()
        for btn in (self._btn_start, self._btn_stop, self._btn_force, self._btn_clear):
            toolbar.addWidget(btn)
        self.addToolBar(toolbar)

        central = QWidget()
        layout = QVBoxLayout(central)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.addWidget(self._editor)
        self.setCentralWidget(central)

        self._status_bar = QStatusBar()
        self.setStatusBar(self._status_bar)

        # 定时读日志
        self._log_timer = QTimer(self)
        self._log_timer.timeout.connect(self._read_new_lines)
        self._log_timer.start(800)

        # 定时刷新状态栏
        self._status_timer = QTimer(self)
        self._status_timer.timeout.connect(self._update_status)
        self._status_timer.start(2000)

        LOG_DIR.mkdir(parents=True, exist_ok=True)
        LOG_FILE.touch(exist_ok=True)
        self._load_tail()
        self._update_status()

    def _set_window_icon(self) -> None:
        if APP_ICON_PATH.exists():
            self.setWindowIcon(QIcon(str(APP_ICON_PATH)))

    def _load_tail(self) -> None:
        try:
            size = LOG_FILE.stat().st_size
            read_size = min(self.TAIL_BYTES, size)
            with LOG_FILE.open("rb") as fh:
                fh.seek(size - read_size)
                data = fh.read(read_size)
            text = data.decode("utf-8", errors="ignore")
            if size > read_size:
                idx = text.find("\n")
                if idx != -1:
                    text = text[idx + 1:]
            if text:
                self._editor.setPlainText(text)
                self._editor.moveCursor(self._editor.textCursor().End)
            self._offset = size
        except Exception as exc:
            self._append(f"[ERROR] 读取日志失败: {exc}\n")

    def _read_new_lines(self) -> None:
        try:
            size = LOG_FILE.stat().st_size
            if size < self._offset:
                self._offset = 0
            if size == self._offset:
                return
            with LOG_FILE.open("r", encoding="utf-8", errors="ignore") as fh:
                fh.seek(self._offset)
                data = fh.read()
                self._offset = fh.tell()
            if data:
                self._append(data)
        except Exception as exc:
            self._append(f"[ERROR] 读取失败: {exc}\n")

    def _append(self, text: str) -> None:
        self._editor.moveCursor(self._editor.textCursor().End)
        self._editor.insertPlainText(text)
        self._editor.moveCursor(self._editor.textCursor().End)

    def _update_status(self, extra: Optional[str] = None) -> None:
        msg = self.controller.status_text()
        if extra:
            msg = f"{msg} | {extra}"
        self._status_bar.showMessage(msg)

    def _on_start(self) -> None:
        self._update_status(self.controller.start())

    def _on_stop(self) -> None:
        self._update_status(self.controller.stop())

    def _on_force_stop(self) -> None:
        reply = QMessageBox.question(
            self,
            "确认强制停止",
            "将强制杀死所有相关进程，是否继续？",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply == QMessageBox.Yes:
            self._update_status(self.controller.force_stop_all())

    def _on_clear_log(self) -> None:
        reply = QMessageBox.question(
            self,
            "确认清空",
            "确定要清空日志文件吗？",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return
        try:
            self._editor.clear()
            LOG_FILE.write_text("", encoding="utf-8")
            self._offset = 0
            self._update_status("日志已清空")
        except Exception as exc:
            QMessageBox.critical(self, "错误", f"清空失败: {exc}")


# ============================================================
# 3. TrayApp - 系统托盘图标
# ============================================================
class TrayApp(QSystemTrayIcon):
    """系统托盘图标 + 右键菜单 + 状态轮询。"""

    _COLOR_RUNNING = QColor(34, 197, 94)   # 绿色
    _COLOR_STOPPED = QColor(239, 68, 68)   # 红色

    def __init__(self, controller: ServerController, parent=None) -> None:
        super().__init__(parent)
        self.controller = controller
        self._log_window: Optional[LogWindow] = None
        self._last_running: Optional[bool] = None
        self._action_start: Optional[QAction] = None
        self._action_stop: Optional[QAction] = None
        self._auto_restart_count = 0  # 自动重启计数器
        self._user_stopped = False    # 甮止用户主动停止后自动重启
        self._max_auto_restart = 10   # 最大自动重启次数

        self.setToolTip(APP_TITLE)
        self._update_icon()
        self._build_menu()
        self.activated.connect(self._on_activated)

        self._poll_timer = QTimer(self)
        self._poll_timer.timeout.connect(self._on_poll)
        self._poll_timer.start(2000)

    # ---------- 图标 ----------

    def _make_icon(self, running: bool) -> QIcon:
        """托盘图标: LXGX Logo 为主体，右下角覆盖状态指示点。"""
        size = 64
        pixmap = QPixmap(size, size)
        pixmap.fill(Qt.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing)

        if APP_ICON_PATH.exists():
            src = QPixmap(str(APP_ICON_PATH))
            if not src.isNull():
                # Logo 占满整个画布（保留透明背景）
                logo_sz = int(size * 0.82)
                off = (size - logo_sz) // 2
                scaled = src.scaled(logo_sz, logo_sz, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                painter.drawPixmap(off, off, scaled)
        else:
            # 备用：无 Logo 时画蓝色圆形
            painter.setBrush(QColor(0, 74, 173))
            painter.setPen(Qt.NoPen)
            painter.drawEllipse(4, 4, size - 8, size - 8)

        # 右下角状态指示点 (绿=运行, 红=停止)
        dot_size = 18
        dot_x = size - dot_size - 1
        dot_y = size - dot_size - 1
        dot_color = self._COLOR_RUNNING if running else self._COLOR_STOPPED
        # 白色描边增加可读性
        painter.setBrush(QColor(255, 255, 255))
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(dot_x - 2, dot_y - 2, dot_size + 4, dot_size + 4)
        painter.setBrush(dot_color)
        painter.drawEllipse(dot_x, dot_y, dot_size, dot_size)

        painter.end()
        return QIcon(pixmap)

    def _update_icon(self) -> None:
        running = self.controller.is_running
        self.setIcon(self._make_icon(running))
        self._last_running = running

    # ---------- 菜单 ----------

    def _build_menu(self) -> None:
        menu = QMenu()
        act_status = QAction("服务状态", self)
        self._action_start = QAction("启动服务", self)
        self._action_stop = QAction("停止服务", self)
        act_force = QAction("强制停止所有进程", self)
        act_log = QAction("打开日志窗口", self)
        act_quit = QAction("退出程序", self)

        act_status.triggered.connect(self._on_status)
        self._action_start.triggered.connect(self._on_start)
        self._action_stop.triggered.connect(self._on_stop)
        act_force.triggered.connect(self._on_force_stop)
        act_log.triggered.connect(self._on_log)
        act_quit.triggered.connect(self._on_quit)

        menu.addAction(act_status)
        menu.addAction(self._action_start)
        menu.addAction(self._action_stop)
        menu.addAction(act_force)
        menu.addAction(act_log)
        menu.addSeparator()
        menu.addAction(act_quit)
        self.setContextMenu(menu)
        self._refresh_menu()

    def _refresh_menu(self) -> None:
        running = self.controller.is_running
        if self._action_start:
            self._action_start.setEnabled(not running)
        if self._action_stop:
            self._action_stop.setEnabled(running)

    # ---------- 槽函数 ----------

    def _on_poll(self) -> None:
        running = self.controller.is_running
        if running != self._last_running:
            self._update_icon()
            self._refresh_menu()

            # [WATCHDOG] 服务从运行变为停止，且不是用户主动停止的 -> 意外崩溃
            if self._last_running is True and not running and not self._user_stopped:
                self._handle_unexpected_death()

    def _on_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason == QSystemTrayIcon.DoubleClick:
            self._on_log()

    def _on_status(self) -> None:
        self.showMessage(APP_TITLE, self.controller.status_text(), QSystemTrayIcon.Information, 5000)

    def _on_start(self) -> None:
        self._user_stopped = False  # 重置标记
        msg = self.controller.start()
        self.showMessage(APP_TITLE, msg, QSystemTrayIcon.Information, 4000)
        self._update_icon()
        self._refresh_menu()

    def _on_stop(self) -> None:
        self._user_stopped = True  # 标记为用户主动停止
        msg = self.controller.stop()
        self.showMessage(APP_TITLE, msg, QSystemTrayIcon.Information, 4000)
        self._update_icon()
        self._refresh_menu()

    def _on_force_stop(self) -> None:
        reply = QMessageBox.question(
            None, "确认强制停止",
            "将强制杀死所有相关进程，是否继续？",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )
        if reply == QMessageBox.Yes:
            msg = self.controller.force_stop_all()
            self.showMessage(APP_TITLE, msg, QSystemTrayIcon.Information, 4000)
            self._update_icon()
            self._refresh_menu()

    def _on_log(self) -> None:
        if self._log_window is None or not self._log_window.isVisible():
            self._log_window = LogWindow(self.controller)
        self._log_window.show()
        self._log_window.raise_()
        self._log_window.activateWindow()

    def _on_quit(self) -> None:
        reply = QMessageBox.question(
            None, "确认退出",
            "退出程序将停止后台服务，是否继续？",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return
        self._user_stopped = True  # 防止退出时触发 watchdog
        if self._log_window:
            self._log_window.close()
        self.controller.stop()
        QApplication.instance().quit()

    # ---------- Watchdog: 自动重启 ----------

    def _handle_unexpected_death(self) -> None:
        """[WATCHDOG] 检测到服务意外死亡，自动重启"""
        self._auto_restart_count += 1
        import logging
        _logger = logging.getLogger(__name__)

        if self._auto_restart_count > self._max_auto_restart:
            msg = f"[WATCHDOG] 服务已崩溃 {self._auto_restart_count} 次，停止自动重启"
            _logger.error(msg)
            self.showMessage(APP_TITLE, msg, QSystemTrayIcon.Critical, 10000)
            return

        msg = f"[WATCHDOG] 服务意外停止, 第 {self._auto_restart_count} 次自动重启..."
        _logger.warning(msg)
        self.showMessage(APP_TITLE, msg, QSystemTrayIcon.Warning, 5000)

        # 延迟 3 秒后重启，避免快速循环崩溃
        QTimer.singleShot(3000, self._do_auto_restart)

    def _do_auto_restart(self) -> None:
        """[WATCHDOG] 执行自动重启"""
        import logging
        _logger = logging.getLogger(__name__)

        restart_msg = self.controller.start()
        _logger.info(f"[WATCHDOG] 重启结果: {restart_msg}")

        if self.controller.is_running:
            self._auto_restart_count = 0  # 重启成功，重置计数器
            self.showMessage(APP_TITLE, f"[WATCHDOG] 服务已自动恢复: {restart_msg}", QSystemTrayIcon.Information, 5000)
        else:
            self.showMessage(APP_TITLE, f"[WATCHDOG] 重启失败: {restart_msg}", QSystemTrayIcon.Critical, 5000)

        self._update_icon()
        self._refresh_menu()


# ============================================================
# 4. SingleInstanceApp - 单例保护
# ============================================================
class SingleInstanceApp:
    """确保只有一个程序实例运行。"""

    def __init__(self, key: str) -> None:
        self._key = key
        self._server: Optional[QLocalServer] = None
        self._is_running = False
        self._check()

    def _check(self) -> None:
        sock = QLocalSocket()
        sock.connectToServer(self._key)
        if sock.waitForConnected(500):
            sock.write(b"activate")
            sock.waitForBytesWritten(1000)
            sock.disconnectFromServer()
            self._is_running = True
        else:
            self._is_running = False
            self._server = QLocalServer()
            QLocalServer.removeServer(self._key)
            self._server.listen(self._key)

    @property
    def is_running(self) -> bool:
        return self._is_running

    def set_activation_callback(self, cb) -> None:
        if self._server:
            def _on_conn():
                client = self._server.nextPendingConnection()
                if client:
                    client.waitForReadyRead(500)
                    client.close()
                    cb()
            self._server.newConnection.connect(_on_conn)


# ============================================================
# 5. 入口
# ============================================================
def run_tray_app() -> None:
    """启动托盘应用主循环。"""
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)

    # 单例检查
    single = SingleInstanceApp(SINGLE_INSTANCE_KEY)
    if single.is_running:
        QMessageBox.information(None, APP_TITLE, "程序已在运行中")
        sys.exit(0)

    if not QSystemTrayIcon.isSystemTrayAvailable():
        QMessageBox.critical(None, "错误", "当前系统不支持托盘图标")
        sys.exit(1)

    controller = ServerController()
    tray = TrayApp(controller)
    single.set_activation_callback(tray._on_log)

    tray.show()

    # 自动启动服务
    start_msg = controller.start()
    import logging
    logging.getLogger(__name__).info(f"自动启动服务: {start_msg}")

    # 自动打开日志窗口
    tray._on_log()

    sys.exit(app.exec_())


if __name__ == "__main__":
    run_tray_app()
