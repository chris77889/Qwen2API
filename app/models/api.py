"""
API数据模型
"""
from typing import List, Dict, Any, Optional, Union
from pydantic import BaseModel, Field


class Message(BaseModel):
    """聊天消息模型"""
    role: str = Field(..., description="消息角色")
    content: Union[str, List[Dict[str, Any]]] = Field(..., description="消息内容")
    chat_type: Optional[str] = Field(None, description="聊天类型")
    extra: Optional[Dict[str, Any]] = Field(None, description="额外信息")
    feature_config: Optional[Dict[str, Any]] = Field(None, description="特性配置")


class ChatRequest(BaseModel):
    """聊天请求模型"""
    model: str = Field(..., description="模型名称")
    messages: List[Message] = Field(..., description="消息列表")
    stream: Optional[bool] = Field(None, description="是否使用流式响应")
    chat_type: Optional[str] = Field(None, description="聊天类型")
    id: Optional[str] = Field(None, description="请求ID")


class ImageRequest(BaseModel):
    """图像生成请求模型"""
    model: str = Field(..., description="模型名称")
    prompt: str = Field(..., description="提示词")
    n: int = Field(1, description="生成数量")
    size: str = Field("1024*1024", description="图像尺寸")


class TokenCreate(BaseModel):
    """Token创建模型"""
    token: str = Field(..., description="API Token")
    description: str = Field("", description="Token描述")
    enabled: bool = Field(True, description="是否启用")


class TokenUpdate(BaseModel):
    """Token更新模型"""
    description: Optional[str] = Field(None, description="Token描述")
    enabled: Optional[bool] = Field(None, description="是否启用")


class AccountCreate(BaseModel):
    """账户创建模型"""
    token: str = Field(..., description="账户Token")
    username: str = Field("", description="用户名")
    password: str = Field("", description="密码")
    cookie: str = Field("", description="Cookie")
    enabled: bool = Field(True, description="是否启用")


class AccountUpdate(BaseModel):
    """账户更新模型"""
    username: Optional[str] = Field(None, description="用户名")
    password: Optional[str] = Field(None, description="密码")
    cookie: Optional[str] = Field(None, description="Cookie")
    enabled: Optional[bool] = Field(None, description="是否启用")


class VideoRequest(BaseModel):
    """视频生成请求模型"""
    model: str = Field(..., description="模型名称")
    prompt: str = Field(..., description="提示词")
    n: int = Field(1, description="生成数量")
    size: str = Field("1280x720", description="视频尺寸") 