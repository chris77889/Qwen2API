"""
安全服务模块

提供基于 FastAPI security 的多认证机制支持
"""
from typing import Optional, List
from fastapi import Depends, HTTPException, Security
from fastapi.security import APIKeyHeader, HTTPBearer, HTTPAuthorizationCredentials
from starlette.status import HTTP_401_UNAUTHORIZED, HTTP_403_FORBIDDEN

from .config import config_manager


class MultiAuth:
    """多认证方式支持"""
    
    def __init__(self):
        """初始化多认证支持"""
        self.api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)
        self.bearer_scheme = HTTPBearer(auto_error=False)
        
    def _is_api_key_valid(self, api_key: str) -> bool:
        """
        验证API密钥是否有效
        
        Args:
            api_key: 要验证的API密钥
            
        Returns:
            bool: API密钥有效返回True，否则返回False
        """
        # 从配置中获取有效的API密钥列表
        valid_api_keys: List[str] = config_manager.get("api.api_keys", [])
        return bool(valid_api_keys and api_key in valid_api_keys)
        
    async def __call__(
        self,
        api_key: Optional[str] = Security(APIKeyHeader(name="X-API-Key", auto_error=False)),
        credentials: Optional[HTTPAuthorizationCredentials] = Security(HTTPBearer(auto_error=False))
    ) -> Optional[str]:
        """
        验证认证信息
        
        Args:
            api_key: API密钥
            credentials: Bearer Token认证信息
            
        Returns:
            Optional[str]: 有效的认证令牌
            
        Raises:
            HTTPException: 认证失败时抛出
        """
        if not config_manager.get("api.enable_api_key", True):
            return None
            
        # 尝试API Key认证
        if api_key:
            if self._is_api_key_valid(api_key):
                return api_key
            raise HTTPException(
                status_code=HTTP_403_FORBIDDEN,
                detail="API密钥无效",
                headers={"WWW-Authenticate": "ApiKey"}
            )
            
        # 尝试Bearer Token认证
        if credentials and credentials.scheme == "Bearer":
            token = credentials.credentials
            if self._is_api_key_valid(token):
                return token
            raise HTTPException(
                status_code=HTTP_403_FORBIDDEN,
                detail="Bearer Token无效",
                headers={"WWW-Authenticate": "Bearer"}
            )
            
        # 未提供任何认证信息
        raise HTTPException(
            status_code=HTTP_401_UNAUTHORIZED,
            detail="未提供认证信息",
            headers={"WWW-Authenticate": "ApiKey, Bearer"}
        )


# 创建全局认证实例
auth = MultiAuth()

# 导出认证依赖
verify_auth = auth 