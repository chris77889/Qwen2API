"""
安全服务模块

提供基于 FastAPI security 的多认证机制支持
"""
from typing import Optional
from fastapi import Depends, HTTPException
from fastapi.security import APIKeyHeader, HTTPBearer, HTTPAuthorizationCredentials
from starlette.status import HTTP_401_UNAUTHORIZED, HTTP_403_FORBIDDEN

from .config import config_manager
from .auth import auth

# 定义 API 密钥头
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)

# 导出认证依赖
verify_auth = auth

async def verify_api_key(api_key: Optional[str] = Depends(api_key_header)) -> str:
    """
    验证 API 密钥
    
    Args:
        api_key: 从请求头获取的 API 密钥
        
    Returns:
        str: 验证通过的 API 密钥
        
    Raises:
        HTTPException: 当 API 密钥未提供或无效时
    """
    if not api_key:
        raise HTTPException(
            status_code=HTTP_401_UNAUTHORIZED,
            detail="未提供 API 密钥",
        )

    # 获取配置中的 API 密钥列表
    valid_api_keys = config_manager.get("api.api_keys", [])
    
    # 验证 API 密钥
    if not valid_api_keys or api_key not in valid_api_keys:
        raise HTTPException(
            status_code=HTTP_403_FORBIDDEN,
            detail="API 密钥无效",
        )

    return api_key 