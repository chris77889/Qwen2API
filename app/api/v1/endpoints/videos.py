from fastapi import APIRouter, Depends
import time
import json

from app.models.api import VideoRequest
from app.core.security import verify_auth
from app.services.account import account_manager
from app.services.media import video_service
from app.core.logger import logger

router = APIRouter()

@router.post("/generations")
async def generate_videos(
    request: VideoRequest,
    token: str = Depends(verify_auth)
):
    try:
        auth_token = account_manager.get_account_token()
        # 标准化消息
        msg = [{"role": "user", "content": request.prompt, "chat_type": "t2v", "extra": {}, "feature_config": {"thinking_enabled": False}}]
        resp = await video_service.generate(
            messages=msg,
            model=request.model,
            size=request.size,
            auth_token=auth_token
        )
        if resp.get('status') != 200:
            logger.error(f"视频生成失败：{resp.get('error')}")
            return {"error": resp.get('error', "视频生成失败"), "status_code": 500}
        return {
            "created": int(time.time() * 1000),
            "data": [{"url": resp['url']} for _ in range(request.n)]
        }
    except Exception as e:
        err = f"处理视频生成请求时发生错误：{str(e)}"
        logger.error(err)
        return {"error": err, "status_code": 500}