from fastapi import APIRouter, Depends, HTTPException
from typing import List

from app.service.account_service import AccountService
from app.core.security import verify_api_key
from app.service.model_service import ModelService
from app.models.model import ModelResponse
router = APIRouter(prefix="/models", tags=["models"])

model_service = ModelService()

@router.get("", response_model=List[ModelResponse])
async def get_models(
    auth: AccountService = Depends(verify_api_key)
):
    """
    获取模型列表
    """
    return await model_service.get_models()

@router.post("/update", response_model=List[ModelResponse])
async def update_models(
    auth: AccountService = Depends(verify_api_key)
):
    """
    更新模型列表
    """
    await model_service.refresh_models()
    return await model_service.get_models()