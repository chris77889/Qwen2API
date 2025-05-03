from typing import Dict, Optional, Tuple
from .account_manager import AccountManager

class CookieService:
    def __init__(self, account_manager: AccountManager):
        """
        初始化Cookie服务
        
        Args:
            account_manager: AccountManager实例，用于获取cookies
        """
        self.account_manager = account_manager
    
    def _get_default_account(self) -> Tuple[str, str]:
        """
        获取默认账号的token和cookie
        
        Returns:
            Tuple[str, str]: (token, cookie)元组
        """
        # 获取有效账号列表
        valid_accounts = self.account_manager.get_valid_accounts()
        if not valid_accounts:
            return '', ''
            
        # 使用第一个有效账号
        account = valid_accounts[0]
        return account.get('token', ''), account.get('cookie', '')
    
    def _merge_cookies(self, custom_cookie: Optional[str] = None) -> str:
        """
        合并通用cookies和自定义cookie
        
        Args:
            custom_cookie: 可选的自定义cookie字符串
            
        Returns:
            str: 合并后的cookie字符串
        """
        cookie_parts = []
        
        # 添加自定义cookie
        if custom_cookie:
            cookie_parts.append(custom_cookie)
        
        # 添加通用cookies
        common_cookies = self.account_manager.get_common_cookies()
        if common_cookies:
            common_cookie_str = '; '.join([f'{k}={v}' for k, v in common_cookies.items()])
            cookie_parts.append(common_cookie_str)
            
        # 合并所有cookie
        return '; '.join(cookie_parts)
    
    def get_headers(self, auth_token: Optional[str] = None, custom_cookie: Optional[str] = None) -> Dict[str, str]:
        """
        获取请求头
        
        Args:
            auth_token: 可选的认证Token
            custom_cookie: 可选的自定义cookie字符串
            
        Returns:
            Dict[str, str]: 完整的请求头字典
        """
        # 如果没有提供token和cookie，使用默认账号
        if auth_token is None and custom_cookie is None:
            auth_token, custom_cookie = self._get_default_account()
        # 如果只提供了token，尝试查找对应的cookie
        elif auth_token and not custom_cookie:
            account = self.account_manager.get_account_by_token(auth_token)
            if account:
                custom_cookie = account.get('cookie', '')
        
        # 基础请求头
        headers = {
            "accept": "application/json",
            "accept-language": "zh-CN,zh;q=0.8,zh-TW;q=0.7,zh-HK;q=0.5,en-US;q=0.3,en;q=0.2",
            "accept-encoding": "gzip",
            "content-type": "application/json",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:138.0) Gecko/20100101 Firefox/138.0",
            "origin": "https://chat.qwen.ai",
            "referer": "https://chat.qwen.ai/",
            "dnt": "1",
            "sec-gpc": "1",
            "connection": "keep-alive",
            "source": "web",
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "same-origin",
            "Priority": "u=4",
            "TE": "trailers",
            "Pragma": "no-cache",
            "Cache-Control": "no-cache"
        }
        
        # 添加认证token
        if auth_token:
            headers["authorization"] = f"Bearer {auth_token}"
        
        # 合并并添加cookies
        merged_cookies = self._merge_cookies(custom_cookie)
        if merged_cookies:
            headers["cookie"] = merged_cookies
            
        return headers 