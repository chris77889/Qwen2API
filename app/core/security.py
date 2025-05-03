from typing import Optional
from fastapi import HTTPException, Security, Depends
from fastapi.security import APIKeyHeader, HTTPBearer, HTTPAuthorizationCredentials
from starlette.status import HTTP_403_FORBIDDEN
from loguru import logger

from .config_manager import ConfigManager

# 创建认证处理器
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)
bearer_auth = HTTPBearer(auto_error=False)

async def verify_api_key(
    api_key_header: Optional[str] = Security(api_key_header),
    bearer_auth: Optional[HTTPAuthorizationCredentials] = Security(bearer_auth),
    config: ConfigManager = Depends(lambda: ConfigManager())
) -> None:
    """
    验证API Key的依赖函数，支持两种方式：
    1. Authorization: Bearer <api_key>
    2. X-API-Key: <api_key>
    
    Args:
        api_key_header: 从X-API-Key头获取的API Key
        bearer_auth: 从Authorization头获取的Bearer凭证
        config: 配置管理器实例
    
    Raises:
        HTTPException: 当API Key验证失败时抛出
    """
    try:
        # 检查是否启用了API Key认证
        if not config.get("api.enable_api_key"):
            return
            
        # 获取API Key（优先使用Authorization header）
        api_key = None
        if bearer_auth:
            api_key = bearer_auth.credentials
        elif api_key_header:
            api_key = api_key_header
            
        if not api_key:
            raise HTTPException(
                status_code=HTTP_403_FORBIDDEN,
                detail="未提供API Key（支持Authorization: Bearer <api_key> 或 X-API-Key: <api_key>）"
            )
            
        # 获取允许的API Keys列表
        allowed_keys = config.get("api.api_keys")
        if not isinstance(allowed_keys, list):
            logger.error("配置错误：api.api_keys 必须是一个列表")
            raise HTTPException(
                status_code=HTTP_403_FORBIDDEN,
                detail="API认证配置错误"
            )
            
        # 验证API Key
        if api_key not in allowed_keys:
            logger.warning(f"无效的API Key尝试: {api_key[:8]}...")
            raise HTTPException(
                status_code=HTTP_403_FORBIDDEN,
                detail="无效的API Key"
            )
            
        logger.debug(f"API Key验证成功: {api_key[:8]}...")
        
    except KeyError as e:
        logger.error(f"配置错误: {str(e)}")
        raise HTTPException(
            status_code=HTTP_403_FORBIDDEN,
            detail="API认证配置错误"
        ) 