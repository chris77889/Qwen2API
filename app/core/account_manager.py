import yaml
from datetime import datetime
from typing import Dict, List, Optional, Union
import os
from pathlib import Path

class AccountManager:
    def __init__(self, config_path: str = "config/accounts.yml"):
        """
        初始化账号管理器
        
        Args:
            config_path: YAML配置文件的路径
        """
        self.config_path = config_path
        self.accounts = []
        self.common_cookies = {}
        self.load_accounts()
    
    def load_accounts(self) -> None:
        """加载账号配置文件"""
        if not os.path.exists(self.config_path):
            self.save_accounts()
            return
        
        with open(self.config_path, 'r', encoding='utf-8') as f:
            data = yaml.safe_load(f)
            self.accounts = data.get('accounts', [])
            self.common_cookies = data.get('common_cookies', {})
    
    def save_accounts(self) -> None:
        """保存账号配置到文件"""
        # 确保目录存在
        os.makedirs(os.path.dirname(self.config_path), exist_ok=True)
        
        data = {
            'accounts': self.accounts,
            'common_cookies': self.common_cookies
        }
        
        with open(self.config_path, 'w', encoding='utf-8') as f:
            yaml.safe_dump(data, f, allow_unicode=True)
    
    def _extract_token_from_cookie(self, cookie: str) -> Optional[str]:
        """
        从cookie字符串中提取token
        
        Args:
            cookie: cookie字符串
        
        Returns:
            Optional[str]: 提取到的token，如果未找到则返回None
        """
        # 分割cookie字符串
        cookie_parts = cookie.split(',')
        for part in cookie_parts:
            if 'token=' in part:
                # 提取token值
                token = part.split('token=')[1].split(';')[0]
                return token
        return None
    
    def add_account(self, username: str, password: str) -> Dict:
        """
        添加新账号（仅需用户名和密码）
        
        Args:
            username: 用户名
            password: 密码
        
        Returns:
            Dict: 创建的账号基础信息
        """
        # 检查是否已存在相同用户名的账号
        if self.get_account_by_username(username):
            raise ValueError(f"用户名 {username} 已存在")
        
        # 创建基础账号信息
        account = {
            "username": username,
            "password": password,
            "enabled": True
        }
        
        # 返回账号信息供登录逻辑使用
        return account
    
    def complete_account_info(self, username: str, cookie: str, expires_at: int) -> bool:
        """
        完成账号信息的添加（登录后调用）
        
        Args:
            username: 用户名
            cookie: 登录后获取的cookie
            expires_at: 过期时间戳
        
        Returns:
            bool: 是否成功完成账号信息添加
        """
        account = self.get_account_by_username(username)
        if not account:
            return False
            
        # 从cookie中提取token
        token = self._extract_token_from_cookie(cookie)
        if not token:
            return False
            
        # 更新账号信息
        account.update({
            "cookie": cookie,
            "token": token,
            "expires_at": expires_at
        })
        
        # 添加到账号列表并保存
        self.accounts.append(account)
        self.save_accounts()
        return True
    
    def get_account_by_token(self, token: str) -> Optional[Dict]:
        """
        通过token查找账号
        
        Args:
            token: 要查找的token
        
        Returns:
            Optional[Dict]: 找到的账号信息，未找到返回None
        """
        for account in self.accounts:
            if account.get('token') == token:
                return account
        return None
    
    def update_account(self, username: str, updates: Dict) -> bool:
        """
        更新账号信息
        
        Args:
            username: 要更新的账号的用户名
            updates: 要更新的字段和值
        
        Returns:
            bool: 是否更新成功
        """
        for i, account in enumerate(self.accounts):
            if account['username'] == username:
                self.accounts[i].update(updates)
                self.save_accounts()
                return True
        return False
    
    def delete_account(self, username: str) -> bool:
        """
        删除账号
        
        Args:
            username: 要删除的账号的用户名
        
        Returns:
            bool: 是否删除成功
        """
        initial_length = len(self.accounts)
        self.accounts = [acc for acc in self.accounts if acc['username'] != username]
        
        if len(self.accounts) < initial_length:
            self.save_accounts()
            return True
        return False
    
    def get_account_by_username(self, username: str) -> Optional[Dict]:
        """
        通过用户名查找账号
        
        Args:
            username: 要查找的用户名
        
        Returns:
            Optional[Dict]: 找到的账号信息，未找到返回None
        """
        for account in self.accounts:
            if account['username'] == username:
                return account
        return None
    
    def get_enabled_accounts(self) -> List[Dict]:
        """
        获取所有启用的账号
        
        Returns:
            List[Dict]: 启用的账号列表
        """
        return [acc for acc in self.accounts if acc['enabled']]
    
    def get_valid_accounts(self) -> List[Dict]:
        """
        获取所有未过期的账号
        
        Returns:
            List[Dict]: 未过期的账号列表
        """
        now = datetime.now().timestamp()
        return [acc for acc in self.accounts if acc['expires_at'] > now]
    
    def get_common_cookies(self) -> Dict:
        """
        获取通用cookies
        
        Returns:
            Dict: 通用cookies字典
        """
        return self.common_cookies
    
    def update_common_cookies(self, cookies: Dict) -> None:
        """
        更新通用cookies
        
        Args:
            cookies: 新的cookies字典
        """
        self.common_cookies = cookies
        self.save_accounts()
    
    def get_all_accounts(self) -> List[Dict]:
        """
        获取所有账号
        
        Returns:
            List[Dict]: 所有账号列表
        """
        return self.accounts