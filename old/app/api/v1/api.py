"""
API路由聚合
"""
from fastapi import APIRouter

from .endpoints import chat, images, models, videos, account

# 创建API路由
api_router = APIRouter()

# 注册路由
api_router.include_router(chat.router, prefix="/chat", tags=["聊天"])
api_router.include_router(images.router, prefix="/images", tags=["图像"])
api_router.include_router(videos.router, prefix="/videos", tags=["视频"])
api_router.include_router(models.router, prefix="/models", tags=["模型"])
api_router.include_router(account.router, prefix="/account", tags=["账户"]) 