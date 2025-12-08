# ============================================================
# 文件说明: response.py - 统一响应模型
# ============================================================
# 模型列表:
# 1. ApiResponse            - 通用API响应
# 2. PaginatedResponse      - 分页响应
# ============================================================

from pydantic import BaseModel, Field
from typing import TypeVar, Generic, Optional, List, Any

T = TypeVar('T')


# ------------------------------------------------------------
# 1. ApiResponse - 通用API响应
# ------------------------------------------------------------
class ApiResponse(BaseModel, Generic[T]):
    """通用API响应"""
    success: bool = Field(True, description="请求是否成功")
    data: Optional[T] = Field(None, description="响应数据")
    error: Optional[str] = Field(None, description="错误信息")
    
    @classmethod
    def ok(cls, data: T = None) -> "ApiResponse[T]":
        """成功响应"""
        return cls(success=True, data=data)
    
    @classmethod
    def fail(cls, error: str) -> "ApiResponse":
        """失败响应"""
        return cls(success=False, error=error)


# ------------------------------------------------------------
# 2. PaginatedResponse - 分页响应
# ------------------------------------------------------------
class Pagination(BaseModel):
    """分页信息"""
    page: int = Field(..., description="当前页码")
    page_size: int = Field(..., description="每页数量")
    total: int = Field(..., description="总数量")
    total_pages: int = Field(..., description="总页数")


class PaginatedResponse(BaseModel, Generic[T]):
    """分页响应"""
    success: bool = True
    data: List[T] = Field(default_factory=list)
    pagination: Pagination
