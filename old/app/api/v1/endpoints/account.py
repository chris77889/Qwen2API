"""
账户管理API路由
"""
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, EmailStr
from typing import Dict, Any
import time
from app.services.account import account_manager
from app.core.security import verify_auth
router = APIRouter()

class LoginRequest(BaseModel):
    """登录请求模型"""
    email: EmailStr
    password: str

class LogoutRequest(BaseModel):
    """登出请求模型"""
    username: str

@router.post("/login", response_model=Dict[str, Any])
async def login(request: LoginRequest, token: str = Depends(verify_auth)):
    """
    使用账号密码登录通义千问
    
    Args:
        request: 登录请求
        
    Returns:
        Dict[str, Any]: 登录结果
    """
    result = await account_manager.login_with_credentials(request.email, request.password)
    if not result['success']:
        raise HTTPException(status_code=400, detail=result['message'])
    return result

@router.post("/logout", response_model=Dict[str, Any])
async def logout(request: LogoutRequest, token: str = Depends(verify_auth)):
    """
    登出通义千问账户
    
    Args:
        request: 登出请求
        
    Returns:
        Dict[str, Any]: 登出结果
    """
    result = await account_manager.logout(request.username)
    if not result['success']:
        raise HTTPException(status_code=400, detail=result['message'])
    return result

@router.get("/accounts", response_model=Dict[str, Any])
async def get_accounts(token: str = Depends(verify_auth)):
    """
    获取所有账户信息
    
    Returns:
        Dict[str, Any]: 账户列表
    """
    accounts = account_manager.get_accounts().copy()
    enabled_accounts = account_manager.get_enabled_accounts().copy()

    # 隐藏敏感信息
    for account in accounts:
        if 'token' in account:
            account.pop('token')
        if 'cookie' in account:
            account.pop('cookie')
        if 'expires_at' in account:
            try:
                expires_at = account['expires_at']
                if isinstance(expires_at, str):
                    # 如果是字符串，尝试解析为时间戳
                    try:
                        expires_at = float(expires_at)
                    except ValueError:
                        # 如果无法解析为时间戳，保持原样
                        continue
                if isinstance(expires_at, (int, float)):
                    account['expires_at'] = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(expires_at))
            except Exception as e:
                # 如果转换失败，保持原样
                continue
        if 'password' in account:
            account.pop('password')
    return {
        'success': True,
        'count': len(accounts),
        'enabled_count': len(enabled_accounts),
        'accounts': accounts,
    } 