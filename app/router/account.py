from fastapi import APIRouter, Depends, HTTPException
from typing import List

from app.models.account import (
    LoginRequest,
    AccountResponse,
    AccountStatusUpdate,
    CommonCookiesUpdate,
    BaseResponse
)
from app.service.account_service import AccountService
from app.core.security import verify_api_key
router = APIRouter(prefix="/accounts", tags=["accounts"])


account_service = AccountService()
@router.post("/login", response_model=BaseResponse)
async def _login(
    request: LoginRequest,
    auth: AccountService = Depends(verify_api_key)
):
    """
    账号登录
    
    Args:
        request: 登录请求
        cookie: 登录成功后的 cookie
        expires_at: cookie 过期时间
        auth: 账号服务实例
    
    Returns:
        BaseResponse: 登录结果
    """
    account = await account_service.login(
        username=request.username,
        password=request.password,
    )
    return BaseResponse(
        message="登录成功",
        data=account
    )

@router.post("/logout/{username}", response_model=BaseResponse)
async def logout(
    username: str,
    auth: AccountService = Depends(verify_api_key)
):
    """
    账号登出
    
    Args:
        username: 用户名
        auth: 账号服务实例
    
    Returns:
        BaseResponse: 登出结果
    """
    success = await account_service.logout(username)
    if not success:
        raise HTTPException(status_code=400, detail="登出失败")
    return BaseResponse(message="登出成功")

@router.get("/list", response_model=List[AccountResponse])
async def get_accounts(
    auth: AccountService = Depends(verify_api_key)
):
    """
    获取账号列表
    
    Args:
        auth: 账号服务实例
    
    Returns:
        List[AccountResponse]: 账号列表
    """
    return await account_service.get_accounts()

@router.post("/{username}/status", response_model=BaseResponse)
async def update_account_status(
    username: str,
    status: AccountStatusUpdate,
    auth: AccountService = Depends(verify_api_key)
):
    """
    更新账号状态
    
    Args:
        username: 用户名
        status: 状态更新请求
        auth: 账号服务实例
    
    Returns:
        BaseResponse: 更新结果
    """
    success = await account_service.update_account_status(username, status.enabled)
    if not success:
        raise HTTPException(status_code=400, detail="状态更新失败")
    return BaseResponse(message="状态更新成功")

@router.post("/common-cookies", response_model=BaseResponse)
async def update_common_cookies(
    cookies: CommonCookiesUpdate,
    auth: AccountService = Depends(verify_api_key)
):
    """
    更新通用 cookies
    
    Args:
        cookies: cookies 更新请求
        auth: 账号服务实例
    
    Returns:
        BaseResponse: 更新结果
    """
    await account_service.update_common_cookies(cookies.cookies)
    return BaseResponse(message="通用 cookies 更新成功")

@router.get("/common-cookies", response_model=BaseResponse)
async def get_common_cookies(
    auth: AccountService = Depends(verify_api_key)
):
    """
    获取通用 cookies
    
    Args:
        auth: 账号服务实例
    
    Returns:
        BaseResponse: 包含通用 cookies 的响应
    """
    cookies = await account_service.get_common_cookies()
    return BaseResponse(
        message="获取成功",
        data={"cookies": cookies}
    ) 