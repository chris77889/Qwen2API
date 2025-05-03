"""
API数据模型
"""
from typing import List, Dict, Any, Optional, Union
from pydantic import BaseModel, Field


class Message(BaseModel):
    """聊天消息模型"""
    role: str = Field(..., description="消息角色")
    content: Union[str, List[Dict[str, Any]]] = Field(..., description="消息内容")
    extra: Optional[Dict[str, Any]] = Field(None, description="额外信息")
    feature_config: Optional[Dict[str, Any]] = Field(None, description="特性配置")


class ChatRequest(BaseModel):
    """聊天请求模型"""
    model: str = Field(..., description="模型名称")
    messages: List[Message] = Field(..., description="消息列表")
    stream: Optional[bool] = Field(None, description="是否使用流式响应")
    id: Optional[str] = Field(None, description="请求ID")
    temperature: Optional[float] = Field(None, description="采样温度，控制输出的随机性，取值范围0-2，值越大随机性越强")


class ImageRequest(BaseModel):
    """图像生成请求模型"""
    model: str = Field(..., description="模型名称")
    prompt: str = Field(..., description="提示词")
    n: int = Field(1, description="生成数量")
    size: str = Field("1024*1024", description="图像尺寸")

class VideoRequest(BaseModel):
    """视频生成请求模型"""
    model: str = Field(..., description="模型名称")
    prompt: str = Field(..., description="提示词")
    n: int = Field(1, description="生成数量")
    size: str = Field("1280x720", description="视频尺寸") 