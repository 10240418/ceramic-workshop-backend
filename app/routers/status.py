# 设备状态位API路由 (后端解析版)

import logging
from fastapi import APIRouter
from typing import Dict, Any, List

from app.services.polling_service import get_device_status_raw
from app.plc.parser_device_status import get_device_status_parser

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/status", tags=["设备状态位"])


def _calc_summary(statuses: List[Dict]) -> Dict[str, int]:
    """计算统计信息"""
    total = len(statuses)
    normal = sum(1 for s in statuses if s.get('is_normal', False))
    return {"total": total, "normal": normal, "error": total - normal}


@router.get("")
async def get_all_device_status():
    """获取所有设备状态位数据 (按DB分组)"""
    try:
        raw_data = get_device_status_raw()
        if not raw_data:
            return {"success": True, "data": {"db3": [], "db7": [], "db11": []}, 
                    "summary": {"total": 0, "normal": 0, "error": 0}, "error": None}
        
        parser = get_device_status_parser()
        parsed_data = parser.parse_all(raw_data)
        
        all_statuses = [s for db_list in parsed_data.values() for s in db_list]
        return {"success": True, "data": parsed_data, 
                "summary": _calc_summary(all_statuses), "error": None}
    except Exception as e:
        logger.error("[Status] get all device status failed: %s", e, exc_info=True)
        return {"success": False, "data": None, "summary": None, "error": str(e)}


@router.get("/flat")
async def get_all_device_status_flat():
    """获取所有设备状态位数据 (扁平列表)"""
    try:
        raw_data = get_device_status_raw()
        if not raw_data:
            return {"success": True, "data": [], 
                    "summary": {"total": 0, "normal": 0, "error": 0}, "error": None}
        
        parser = get_device_status_parser()
        all_statuses = parser.get_all_as_flat_list(raw_data)
        return {"success": True, "data": all_statuses, 
                "summary": _calc_summary(all_statuses), "error": None}
    except Exception as e:
        logger.error("[Status] get flat device status failed: %s", e, exc_info=True)
        return {"success": False, "data": None, "summary": None, "error": str(e)}


@router.get("/db/{db_number}")
async def get_single_db_status(db_number: int):
    """获取单个DB块的状态位数据"""
    try:
        raw_data = get_device_status_raw()
        db_key = f"db{db_number}"
        
        if db_key not in raw_data:
            return {"success": False, "data": None, "db_info": None, 
                    "summary": None, "error": f"DB{db_number} 不存在或未启用"}
        
        db_info = raw_data[db_key]
        parser = get_device_status_parser()
        statuses = parser.parse_db(db_number, db_info.get('raw_data', b''), db_info.get('timestamp'))
        
        return {"success": True, "data": statuses,
                "db_info": {"db_number": db_info['db_number'], "db_name": db_info['db_name']},
                "summary": _calc_summary(statuses), "error": None}
    except Exception as e:
        logger.error("[Status] get DB status failed: %s", e, exc_info=True)
        return {"success": False, "data": None, "db_info": None, "summary": None, "error": str(e)}
