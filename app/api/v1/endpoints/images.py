from fastapi import APIRouter, Depends
import time
import json

from app.models.api import ImageRequest
from app.core.security import verify_auth
from app.services.account import account_manager
from app.services.media import image_service

router = APIRouter()

@router.post("/generations")
async def generate_images(
    request: ImageRequest,
    token: str = Depends(verify_auth)
):
    auth_token = account_manager.get_account_token()
    resp = await image_service.generate(
        messages=[{"role": "user", "content": request.prompt, "chat_type": "t2i", "extra": {}, "feature_config": {"thinking_enabled": False}}],
        model=request.model,
        size=request.size,
        auth_token=auth_token
    )
    if resp.get('status') != 200:
        return {"error": resp.get('error', "图像生成失败"), "status_code": 500}
    return {
        "created": int(time.time() * 1000),
        "data": [{"url": resp['url']} for _ in range(request.n)]
    }