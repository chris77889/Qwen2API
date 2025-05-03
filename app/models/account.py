from pydantic import BaseModel, Field
from typing import Dict, List, Optional

class LoginRequest(BaseModel):
    """登录请求模型"""
    username: str = Field(..., description="用户名")
    password: str = Field(..., description="密码")

class AccountResponse(BaseModel):
    """账号信息响应模型"""
    username: str = Field(..., description="用户名")
    enabled: bool = Field(..., description="是否启用")
    expires_at: Optional[int] = Field(None, description="过期时间戳")

class AccountStatusUpdate(BaseModel):
    """账号状态更新请求模型"""
    enabled: bool = Field(..., description="是否启用")

class CommonCookiesUpdate(BaseModel):
    """通用 cookies 更新请求模型"""
    cookies: Dict[str, str] = Field(..., description="Cookie 字典")

class BaseResponse(BaseModel):
    """基础响应模型"""
    code: int = Field(200, description="状态码")
    message: str = Field("success", description="响应消息")
    data: Optional[dict] = Field(None, description="响应数据") 