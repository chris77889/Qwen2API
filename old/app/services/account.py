"""
账户管理服务
"""
from typing import List, Dict, Any, Optional
import yaml
import httpx
from pathlib import Path
import time
import hashlib
import json

from app.core.config_manager import ConfigManager
from app.core.logger.logger import logger


class AccountManager:
    """账户管理器"""
    
    def __init__(self):
        """初始化账户管理器"""
        self.accounts_file = Path("accounts.yml")
        self.accounts: List[Dict[str, Any]] = []
        self.error_account_tokens: List[str] = []
        self.request_number: int = 0
        self.current_index: int = 0
        self.common_cookies: Dict[str, str] = {}
        self.load_accounts()
        
    def load_accounts(self) -> None:
        """加载账户配置"""
        try:
            if self.accounts_file.exists():
                with open(self.accounts_file, 'r', encoding='utf-8') as f:
                    data = yaml.safe_load(f) or {}
                    self.accounts = data.get('accounts', [])
                    self.common_cookies = data.get('common_cookies', {})
        except Exception as e:
            logger.error(f"加载账户时出错: {e}")
            self.accounts = []
            self.common_cookies = {}
            
    def save_accounts(self) -> None:
        """保存账户配置"""
        try:
            data = {
                'accounts': self.accounts,
                'common_cookies': self.common_cookies
            }
            with open(self.accounts_file, 'w', encoding='utf-8') as f:
                yaml.safe_dump(data, f, allow_unicode=True)
        except Exception as e:
            logger.error(f"保存账户时出错: {e}")
            
    def get_account_token(self) -> str:
        """
        获取当前账户令牌并切换到下一个
        
        Returns:
            str: 当前账户令牌
        """
        enabled_accounts = [account for account in self.accounts if account.get('enabled', True)]
        
        if not enabled_accounts:
            raise ValueError("没有可用的账户")
        
        if self.current_index >= len(enabled_accounts):
            self.current_index = 0
            
        account = enabled_accounts[self.current_index]
        token = account.get('token', '')
        self.current_index += 1
        self.request_number += 1
        return token
    
    def get_accounts(self) -> List[Dict[str, Any]]:
        """
        获取所有账户信息
        
        Returns:
            List[Dict[str, Any]]: 账户列表
        """
        return self.accounts
    
    def get_enabled_accounts(self) -> List[Dict[str, Any]]:
        """
        获取所有启用的账户信息
        
        Returns:
            List[Dict[str, Any]]: 启用的账户列表
        """
        enabled_accounts = [account for account in self.accounts if account.get('enabled', True)]
        
        if not enabled_accounts:
            logger.warning('没有找到可用账户，请在accounts.yaml文件中配置通义千问账户')
        else:
            logger.info(f'已加载 {len(enabled_accounts)} 个通义千问账户')
        return enabled_accounts
    
    def get_error_accounts(self) -> List[str]:
        """
        获取无效账户令牌列表
        
        Returns:
            List[str]: 无效账户令牌列表
        """
        return self.error_account_tokens
    
    def get_request_count(self) -> int:
        """
        获取请求计数
        
        Returns:
            int: 请求计数
        """
        return self.request_number
    
    def add_account(self, account: Dict[str, Any]) -> bool:
        """
        添加账户
        
        Args:
            account: 账户信息
            
        Returns:
            bool: 是否成功添加
        """
        if not account.get('token'):
            return False
            
        # 检查是否已存在
        for existing in self.accounts:
            if existing.get('token') == account['token']:
                return False
                
        self.accounts.append(account)
        self.save_accounts()
        return True
    
    def update_account(self, token: str, updates: Dict[str, Any]) -> bool:
        """
        更新账户信息
        
        Args:
            token: 账户令牌
            updates: 要更新的字段
            
        Returns:
            bool: 是否成功更新
        """
        for i, account in enumerate(self.accounts):
            if account.get('token') == token:
                self.accounts[i].update(updates)
                self.save_accounts()
                return True
        return False
    
    def delete_account(self, token: str) -> bool:
        """
        删除账户
        
        Args:
            token: 账户令牌
            
        Returns:
            bool: 是否成功删除
        """
        initial_count = len(self.accounts)
        self.accounts = [a for a in self.accounts if a.get('token') != token]
        
        if len(self.accounts) != initial_count:
            self.save_accounts()
            return True
        return False
    
    async def check_account_token(self, token: str) -> bool:
        """
        检查账户令牌是否有效
        
        Args:
            token: 要检查的账户令牌
            
        Returns:
            bool: 令牌有效返回True
        """
        try:
            headers = self.get_headers(token)
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    'https://chat.qwen.ai/api/models',
                    headers=headers,
                    timeout=10.0
                )
                return response.status_code == 200
        except Exception:
            return False
            
    async def check_all_account_tokens(self) -> None:
        """检查所有账户令牌的有效性"""
        self.error_account_tokens = []
        
        for account in self.accounts:
            token = account.get('token', '')
            if token:
                is_valid = await self.check_account_token(token)
                if not is_valid:
                    # 只显示前半部分token，保护隐私
                    self.error_account_tokens.append(token)
                    account['enabled'] = False
                    
        self.save_accounts()
    
    def get_common_cookies(self) -> Dict[str, str]:
        """
        获取通用cookie配置
        
        Returns:
            Dict[str, str]: 通用cookie字典
        """
        return self.common_cookies.copy()
        
    def get_headers(self, auth_token: Optional[str] = None) -> Dict[str, str]:
        """
        获取请求头
        
        Args:
            auth_token: 认证Token
            
        Returns:
            Dict[str, str]: 请求头
        """
        if auth_token is None:
            account_info = self.get_account_info()
            auth_token = account_info.get('token', '')
            custom_cookie = account_info.get('cookie', '')
        else:             
            # 尝试在配置中查找账户
            custom_cookie = ''
            for account in self.accounts:
                if account.get('token') == auth_token:
                    custom_cookie = account.get('cookie', '')
                    break
                    
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
        
        # 添加认证和cookie
        headers["authorization"] = f"Bearer {auth_token}"
        
        # 构建cookie字符串
        cookie_parts = []
        
        # 添加账户特定的cookie
        if custom_cookie:
            cookie_parts.append(custom_cookie)
            
        # 添加通用cookie
        common_cookies = self.get_common_cookies()
        if common_cookies:
            common_cookie_str = '; '.join([f'{k}={v}' for k, v in common_cookies.items()])
            cookie_parts.append(common_cookie_str)
            
        # 合并所有cookie
        if cookie_parts:
            headers["cookie"] = '; '.join(cookie_parts)
                
        return headers
    
    def get_account_info(self) -> Dict[str, Any]:
        """
        获取当前账户完整信息
        
        Returns:
            Dict[str, Any]: 当前账户信息
        """
        enabled_accounts = self.get_enabled_accounts()
        
        if not enabled_accounts:
            return {}
            
        index = self.current_index - 1 if self.current_index > 0 else len(enabled_accounts) - 1
        return enabled_accounts[index]
    
    async def generate_markdown_table(self, websites: List[Dict[str, str]], mode: str = "table") -> str:
        """
        生成Markdown格式的网站表格
        
        Args:
            websites: 网站信息列表
            mode: 表格模式
            
        Returns:
            str: Markdown格式的表格
        """
        if not websites:
            return ""
            
        markdown = ""
        if mode == "table":
            markdown += "| **序号** | **网站URL** | **来源** |\n"
            markdown += "|:---|:---|:---|\n"
            
        for index, site in enumerate(websites):
            title = site.get('title', "未知标题")
            url = site.get('url', "https://www.baidu.com")
            hostname = site.get('hostname', "未知来源")
            
            url_cell = f"[{title}]({url})"
            
            if mode == "table":
                markdown += f"| {index + 1} | {url_cell} | {hostname} |\n"
            else:
                markdown += f"[{index + 1}] {url_cell} | 来源: {hostname}\n"
                
        return markdown
    
    def _sha256(self, text: str) -> str:
        """
        计算字符串的SHA256哈希值
        
        Args:
            text: 要计算哈希值的字符串
            
        Returns:
            str: SHA256哈希值
        """
        return hashlib.sha256(text.encode()).hexdigest()
    
    async def login_with_credentials(self, email: str, password: str) -> Dict[str, Any]:
        """
        使用账号密码登录通义千问
        
        Args:
            email: 邮箱
            password: 密码
            
        Returns:
            Dict[str, Any]: 登录结果
        """
        try:
            # 计算密码的SHA256值
            hashed_password = self._sha256(password)
            
            # 准备登录请求
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:137.0) Gecko/20100101 Firefox/137.0",
                "Accept": "*/*",
                "Accept-Language": "zh-CN,zh;q=0.8,zh-TW;q=0.7,zh-HK;q=0.5,en-US;q=0.3,en;q=0.2",
                "Accept-Encoding": "gzip, deflate, br, zstd",
                "Referer": "https://chat.qwen.ai/auth?action=signin",
                "bx-v": "2.5.28",
                "content-type": "application/json",
                "source": "web",
                "version": "0.0.57",
                "x-request-id": f"{time.time()}-{hash(email)}",
                "Origin": "https://chat.qwen.ai",
                "DNT": "1",
                "Sec-GPC": "1",
                "Connection": "keep-alive",
                "Sec-Fetch-Dest": "empty",
                "Sec-Fetch-Mode": "cors",
                "Sec-Fetch-Site": "same-origin"
            }
            
            data = {
                "email": email,
                "password": hashed_password
            }
            
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    "https://chat.qwen.ai/api/v1/auths/signin",
                    headers=headers,
                    json=data,
                    timeout=30.0
                )
                
                if response.status_code == 200:
                    result = response.json()
                    
                    # 检查账户是否已存在
                    for account in self.accounts:
                        if account.get('username') == email:
                            # 更新账户信息
                            account.update({
                                'password': password,
                                'token': result.get('token', ''),
                                'cookie': response.headers.get('set-cookie', ''),
                                'expires_at': result.get('expires_at', 0),
                                'enabled': True,
                            })
                            self.save_accounts()
                            return {
                                'success': True,
                                'message': '登录成功',
                                'account': {
                                    'username': email,
                                    'token': result.get('token', ''),
                                    'expires_at': result.get('expires_at', 0),
                                    'enabled': True
                                }
                            }
                    
                    # 添加新账户
                    new_account = {
                        'username': email,
                        'password': password,
                        'token': result.get('token', ''),
                        'cookie': response.headers.get('set-cookie', ''),
                        'expires_at': result.get('expires_at', 0),
                        'enabled': True,
                    }
                    self.accounts.append(new_account)
                    self.save_accounts()
                    
                    return {
                        'success': True,
                        'message': '登录成功',
                        'account': {
                            'username': email,
                            'token': result.get('token', ''),
                            'expires_at': result.get('expires_at', 0),
                            'enabled': True
                        }
                    }
                else:
                    return {
                        'success': False,
                        'message': f'登录失败：{response.text}'
                    }
        except Exception as e:
            logger.error(f"登录失败: {e}")
            return {
                'success': False,
                'message': f'登录失败：{str(e)}'
            }
    async def re_login(self, token: str) -> Dict[str, Any]:
        """
        重新登录通义千问账户
        
        Args:
            token: 账户令牌    
        
        Returns:
            Dict[str, Any]: 重新登录结果
        """
        try:
            for account in self.accounts:
                if account.get('token') == token:
                    return await self.login_with_credentials(account.get('username'), account.get('password'))
                else:
                    return {
                        'success': False,
                        'message': '未找到账户'
                    }
        except Exception as e:
            logger.error(f"重新登录失败: {e}")
            return {
                'success': False,
                'message': f'重新登录失败：{str(e)}'
            }
    async def logout(self, username: str) -> Dict[str, Any]:
        """
        登出通义千问账户
        
        Args:
            token: 账户令牌
            
        Returns:
            Dict[str, Any]: 登出结果
        """
        try:
            for account in self.accounts:
                if account.get('username') == username:
                    account['enabled'] = False
                    self.save_accounts()
                    return {
                        'success': True,
                        'message': '登出成功',
                        'account': {
                            'username': username,
                            'enabled': False
                        }
                    }
            return {
                'success': False,
                'message': '登出失败：未找到账户'
            }
        except Exception as e:
            logger.error(f"登出失败: {e}")
            return {
                'success': False,
                'message': f'登出失败：{str(e)}'
            }


# 创建全局账户管理器实例
account_manager = AccountManager()