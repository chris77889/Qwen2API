"""
模型相关接口
"""
import httpx
import time
from fastapi import APIRouter, Depends, HTTPException
from typing import Dict, Any, List

from app.core.security import verify_auth
from app.services.account import account_manager
from app.services.model import model_service
from app.core.logger import logger

router = APIRouter()

@router.get("")
async def get_models(token: str = Depends(verify_auth)) -> Dict[str, Any]:
    """
    获取模型列表（从文件中读取）
    
    Args:
        token: 认证令牌（支持API Key或Bearer Token）
        
    Returns:
        Dict[str, Any]: 模型列表
    """
    try:
        # 从model service获取模型列表
        models = await model_service.get_models()
        return {
            "object": "list",
            "data": models
        }
    except Exception as e:
        logger.error(f"Error in get_models: {e}")
        raise HTTPException(
            status_code=500,
            detail=str(e)
        )

@router.post("/update")
async def update_models(token: str = Depends(verify_auth)) -> Dict[str, Any]:
    """
    更新模型列表（从API获取并保存到文件）
    
    Args:
        token: 认证令牌（支持API Key或Bearer Token）
        
    Returns:
        Dict[str, Any]: 更新后的模型列表
    """
    try:
        # 获取通义千问账户令牌
        auth_token = account_manager.get_account_token()
        
        # 从API获取模型列表
        async with httpx.AsyncClient() as client:
            response = await client.get(
                'https://chat.qwen.ai/api/models',
                headers=account_manager.get_headers(auth_token),
                timeout=15.0
            )
            
            if response.status_code != 200:
                raise HTTPException(
                    status_code=response.status_code,
                    detail="从API获取模型列表失败"
                )
                
            models_data = response.json()
            if not models_data or 'data' not in models_data:
                raise HTTPException(
                    status_code=500,
                    detail="API返回的模型数据格式不正确"
                )
                
            # 处理模型列表，添加后缀变种
            models_list = []
            default_models = []
            
            for item in models_data['data']:
                model_id = item.get('id')
                if not model_id:
                    continue
                    
                default_models.append(model_id)
                models_list.append(model_id)
                
                # 思考模式：所有模型都支持
                models_list.append(f"{model_id}-thinking")
                
                # 搜索模式：所有模型都支持
                models_list.append(f"{model_id}-search")
                models_list.append(f"{model_id}-thinking-search")
                
                # 绘图模式：只有部分模型支持
                if model_id in ["qwen-max-latest", "qwen-plus-latest"]:
                    models_list.append(f"{model_id}-draw")
            
            # 构建模型列表响应
            models = {
                "object": "list",
                "data": [
                    {
                        "id": item,
                        "object": "model",
                        "created": int(models_data.get('created', time.time() * 1000)),
                        "owned_by": "qwen"
                    } for item in models_list
                ]
            }
            
            # 更新model service中的模型列表
            model_service.set_models(default_models)
            
            return models
            
    except Exception as e:
        logger.error(f"Error in update_models: {e}")
        raise HTTPException(
            status_code=500,
            detail=str(e)
        ) 