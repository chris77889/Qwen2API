"""
视频API路由
"""
import time
from fastapi import APIRouter, Depends

from app.models.api import VideoRequest
from app.core.security import verify_auth
from app.services.account import account_manager
from app.services.video import video_service

router = APIRouter()


@router.post("/generations")
async def generate_videos(
    request: VideoRequest,
    token: str = Depends(verify_auth)
):
    """
    处理视频生成请求
    
    Args:
        request: 视频生成请求
        token: 认证令牌（支持API Key或Bearer Token）
        
    Returns:
        生成的视频URL列表
    """
    # 获取通义千问账户令牌
    auth_token = account_manager.get_account_token()

    # 发送视频生成请求
    response_data = await video_service.generate_video(
        prompt=request.prompt,
        auth_token=auth_token,
        model=request.model,
        size=request.size
    )
    
    if response_data.get('status') != 200:
        return {"error": response_data.get('error', "视频生成失败"), "status_code": 500}

    # 构建响应
    response = {
        "created": int(time.time() * 1000),
        "data": [{"url": response_data['url']} for _ in range(request.n)]
    }
    
    return response 