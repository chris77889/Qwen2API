import hashlib
import time
import httpx
from typing import Dict, List, Optional, Any
from fastapi import HTTPException
from app.core.account_manager import AccountManager
from app.models.account import AccountResponse
from app.core.cookie_service import CookieService
class AccountService:
    def __init__(self):
        """初始化账号服务"""
        self.account_manager = AccountManager()
        self.cookie_service = CookieService(self.account_manager)
    
    def _sha256(self, text: str) -> str:
        """
        计算文本的SHA256哈希值
        
        Args:
            text: 要计算哈希的文本
            
        Returns:
            str: SHA256哈希值
        """
        return hashlib.sha256(text.encode()).hexdigest()
    
    async def login(self, username: str, password: str) -> Dict:
        """
        账号登录
        
        Args:
            username: 用户名
            password: 密码
            
        Returns:
            Dict: 账号信息
            
        Raises:
            HTTPException: 登录失败时抛出
        """
        try:
            # 计算密码的SHA256值
            hashed_password = self._sha256(password)
            
            # 获取请求头
            headers = self.cookie_service.get_headers()
            # 添加登录特定的请求头
            headers.update({
                "x-request-id": f"{time.time()}-{hash(username)}",
                "Referer": "https://chat.qwen.ai/auth?action=signin",
                "bx-v": "2.5.28",
                "version": "0.0.57"
            })
            
            data = {
                "email": username,
                "password": hashed_password
            }
            
            # 发送登录请求
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    "https://chat.qwen.ai/api/v1/auths/signin",
                    headers=headers,
                    json=data,
                    timeout=30.0
                )
                
                if response.status_code != 200:
                    raise HTTPException(status_code=response.status_code, detail=response.text)
                
                result = response.json()
                cookie = response.headers.get('set-cookie', '')
                expires_at = result.get('expires_at', 0)
                
                try:
                    # 创建基础账号信息
                    account = self.account_manager.add_account(username, password)
                    
                    # 完成账号信息添加
                    if not self.account_manager.complete_account_info(username, cookie, expires_at):
                        raise HTTPException(status_code=400, detail="账号信息添加失败")
                    
                    return account
                except ValueError:
                    # 账号已存在，更新信息
                    updates = {
                        "cookie": cookie,
                        "token": result.get('token', ''),
                        "expires_at": expires_at
                    }
                    if not self.account_manager.update_account(username, updates):
                        raise HTTPException(status_code=400, detail="账号信息更新失败")
                    
                    return self.account_manager.get_account_by_username(username)
                    
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))
    
    async def logout(self, username: str) -> bool:
        """
        账号登出
        
        Args:
            username: 用户名
            
        Returns:
            bool: 是否成功登出
            
        Raises:
            HTTPException: 账号不存在时抛出
        """
        account = self.account_manager.get_account_by_username(username)
        if not account:
            raise HTTPException(status_code=404, detail="账号不存在")
        
        return self.account_manager.delete_account(username)
    
    async def get_accounts(self) -> List[AccountResponse]:
        """
        获取所有账号列表
        
        Returns:
            List[AccountResponse]: 账号列表
        """
        accounts = self.account_manager.get_all_accounts()
        return [
            AccountResponse(
                username=account["username"],
                enabled=account["enabled"],
                expires_at=account.get("expires_at")
            )
            for account in accounts
        ]
    
    async def update_account_status(self, username: str, enabled: bool) -> bool:
        """
        更新账号状态
        
        Args:
            username: 用户名
            enabled: 是否启用
            
        Returns:
            bool: 是否更新成功
            
        Raises:
            HTTPException: 账号不存在时抛出
        """
        if not self.account_manager.get_account_by_username(username):
            raise HTTPException(status_code=404, detail="账号不存在")
        
        return self.account_manager.update_account(username, {"enabled": enabled})
    
    async def update_common_cookies(self, cookies: Dict[str, str]) -> None:
        """
        更新通用 cookies
        
        Args:
            cookies: 新的 cookies 字典
        """
        self.account_manager.update_common_cookies(cookies)
    
    async def get_common_cookies(self) -> Dict[str, str]:
        """
        获取通用 cookies
        
        Returns:
            Dict[str, str]: 通用 cookies 字典
        """
        return self.account_manager.get_common_cookies() 