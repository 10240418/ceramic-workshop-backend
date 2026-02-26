# -*- mode: python ; coding: utf-8 -*-

import sys
from pathlib import Path


def find_snap7_dll():
    """查找 snap7.dll（支持 venv 与系统 Python）"""
    search_roots = []

    if getattr(sys, "prefix", None):
        search_roots.append(Path(sys.prefix))

    try:
        import site
        for p in site.getsitepackages():
            search_roots.append(Path(p))
    except Exception:
        pass

    try:
        user_site = Path(site.getusersitepackages())
        search_roots.append(user_site)
    except Exception:
        pass

    candidates = []
    for root in search_roots:
        candidates.extend(root.glob("**/snap7/lib/snap7.dll"))

    if not candidates:
        raise FileNotFoundError(
            "未找到 snap7.dll，请先安装 python-snap7==2.0.2 再打包"
        )

    return str(candidates[0])


snap7_dll = find_snap7_dll()


a = Analysis(
    ['scripts/tray_app.py'],  # [FIX] 入口改为托盘应用
    pathex=['.'],
    binaries=[(snap7_dll, 'snap7/lib')],
    datas=[
        ('configs', 'configs'),
        ('data', 'data'),
        ('.env', '.'),
        ('assets', 'assets'),  # 托盘图标
    ],
    hiddenimports=[
        # FastAPI / Uvicorn
        'uvicorn',
        'fastapi',
        # PyQt5 (系统托盘)
        'PyQt5',
        'PyQt5.QtCore',
        'PyQt5.QtGui',
        'PyQt5.QtWidgets',
        'PyQt5.QtNetwork',
        # psutil (进程管理)
        'psutil',
        # InfluxDB
        'influxdb_client',
        'influxdb_client.client',
        'influxdb_client.client.write_api',
        # Snap7 (PLC)
        'snap7',
        'snap7.client',
        'snap7.common',
        'snap7.util',
        'snap7.error',
        'snap7.type',
        # main.py 需要（被 tray_app 动态 import）
        'main',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['sqlalchemy'],
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='WorkshopBackend',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,             # 无控制台窗口，只有托盘图标
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,                 # 可在此指定 .ico 文件路径
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='WorkshopBackend',
)

# ============================================================
# 打包后处理：确保目录结构完整
# ============================================================
import shutil
from pathlib import Path

dist_dir = Path('dist/WorkshopBackend')

# 根目录保留可修改的配置文件
if Path('.env').exists():
    shutil.copy('.env', dist_dir / '.env')
    print('[打包] 已复制 .env 到根目录')

if Path('configs').exists():
    target = dist_dir / 'configs'
    if target.exists():
        shutil.rmtree(target)
    shutil.copytree('configs', target)
    print('[打包] 已复制 configs/ 到根目录')

(dist_dir / 'data').mkdir(exist_ok=True)
(dist_dir / 'logs').mkdir(exist_ok=True)
print('[打包] 已创建 data/ 和 logs/ 目录')

print('')
print('[打包完成] dist/WorkshopBackend/')
print('  WorkshopBackend.exe   <- 双击启动，系统托盘运行')
print('  .env                  <- 可修改配置')
print('  configs/              <- 可修改配置')
print('  logs/server.log       <- 运行日志（托盘双击打开）')
