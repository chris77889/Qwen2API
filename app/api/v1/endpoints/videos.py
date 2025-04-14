"""
视频API路由
"""
import time
from fastapi import APIRouter, Depends

from app.models.api import VideoRequest
from app.core.security import verify_auth
from app.services.account import account_manager
from app.services.video import video_service
from app.core.logger import logger

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
    try:
        # 获取通义千问账户令牌
        auth_token = account_manager.get_account_token()

        # 构建消息列表
        messages = [{
            "role": "user",
            "content": request.prompt,
            "chat_type": "t2v",
            "extra": {},
            "feature_config": {
                "thinking_enabled": False
            }
        }]

        # 发送视频生成请求
        response_data = await video_service.generate_video(
            messages=messages,
            auth_token=auth_token,
            model=request.model,
            size=request.size
        )
        
        if response_data.get('status') != 200:
            error_msg = response_data.get('error', "视频生成失败")
            logger.error(f"视频生成失败：{error_msg}")
            return {
                "error": error_msg,
                "status_code": 500
            }

        # 构建响应
        response = {
            "created": int(time.time() * 1000),
            "data": [{"url": response_data['url']} for _ in range(request.n)]
        }
        
        return response
        
    except Exception as e:
        error_msg = f"处理视频生成请求时发生错误：{str(e)}"
        logger.error(error_msg)
        return {
            "error": error_msg,
            "status_code": 500
        } 