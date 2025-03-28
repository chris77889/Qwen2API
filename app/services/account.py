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

from ..core.config import config_manager
from ..core.logger import logger


class AccountManager:
    """账户管理器"""
    
    def __init__(self):
        """初始化账户管理器"""
        self.accounts_file = Path("accounts.yml")
        self.accounts: List[Dict[str, Any]] = []
        self.error_account_tokens: List[str] = []
        self.request_number: int = 0
        self.current_index: int = 0
        self.load_accounts()
        
    def load_accounts(self) -> None:
        """加载账户配置"""
        try:
            if self.accounts_file.exists():
                with open(self.accounts_file, 'r', encoding='utf-8') as f:
                    data = yaml.safe_load(f) or {}
                    self.accounts = data.get('accounts', [])
        except Exception as e:
            logger.error(f"加载账户时出错: {e}")
            self.accounts = []
            
    def save_accounts(self) -> None:
        """保存账户配置"""
        try:
            data = {'accounts': self.accounts}
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
            "Host": "chat.qwen.ai",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36 Edg/133.0.0.0",
            "Connection": "keep-alive",
            "Accept": "*/*",
            "Accept-Encoding": "gzip",
            "Content-Type": "application/json",
            "x-request-id": "647cb70a-cba5-4c36-b2b6-24ffd1cd9ddd",
            "bx-umidtoken": "T2gANtcYZT9YXfuoIZSNG3a6XIXekUQTnHdkm89EvfK4PlAHce3PTY7P2uXFuSyOUD0=",
            "sec-ch-ua": "\"Not(A:Brand\";v=\"99\", \"Microsoft Edge\";v=\"133\", \"Chromium\";v=\"133\"",
            "bx-ua": "231!HfE3n4mU6XD+joD+2A3qn9GjUq/YvqY2leOxacSC80vTPuB9lMZY9mRWFzrwLEkXiDXjNoMrUTUrD8F60zRopdw4q1VCXXb6a3OcTO0aNraYN7OvMJaMSPZflmanlUyoCu/53Ob3Z2axxzeocMRAZBbLWmN5pACia0pqOo32MEW8R00WUQ8Eh/x/9FF9Wsw51YBfIx0BNoJOn3iv7H4JNd4Pn7Fc3kjC0Q3oyE+jlN0WmBO0lGIGHkE+++3+qCS4+ItM2+6yoj2Co+4oHoHrYllvGajKNtZP0VnAemzey5L2aDafscJnytDA0CU9Lr2fBdtUJ05wM85zMV1K82dLiIIwrx7R2j2RhroyQJVkNGvMrbggEB9jwafW9HB4ZSUHvT2o3dfd2ttMeoYcE8eRZaEfwAJaPh4OQH9JOxqVSs4hkFD9V2/l3lDylss7J9hBsENAc8XpkC3H42Vd7Bd3nOh6i2804/kS4sOVefHFQr6uuAKNEN0VgW1lTVHPx6J+v6EsUX5Pia1jhfxu7hrX9M13Xx66nvCmYVqhPLC3khh8T/9iSqWL2Hz923Ah1dYM86HVfctlWbq+Gpz150IcktLUpfZOh+rmO26G34RyjOzKiaqroI0G7TVSS0wRNpTYwwSRhx4XLlTCovLEAeKV9FOdRg7PmqId30ad0Q6pa05uGljSAhW0nhfhQ3hUX7xWM08rUkZdFY77emjkWOMgKoPJ9MGcpbSsosUgT8nY0UDNgJrKZukRbMsmHGcwPfxhlnhTBb792FAmGwIFVauUINI8Rs6iJpp2pOMOTkKFIVp3jtPuSrdXskdpCUAcuVHttIHQlQe4ZBkQwxOd6KTNla89AkF8imVObsEwS2jnygnPJxYFh+XJ5q9p5HsvCf/6lxFzc+x+JLRfEE7vshRemUjRAf58jfCxArX7K2WZtIUrvgW6b6lGYgJmDfpSnNNIzEoixI7SQtdYo0oF49r5yMTeF6Z9X8Tv9a8tGPnc73lcaITtouRfkBiWRJdCg9I8ycMDqJbwUkMjMpF/+c+A0o/inaz4ehRlTxI0upr/OtzdbVkwWcFYbmJuDrZLTlt+MsyE2KmNfVjNccAw4f5OWcjLtKGjX3FUvxpfCobuYKqcOP1q8ku5xQrEQgDXxBSrckylc4qGlzD0b+ykDbkQHec99V6stxgWsT2yGM04ODEqomDk+CkRcKKXzjET5DPA0kJ2j0+XErTyYwP3uwhbNtjcXmo/dCCSC7t1HRp9E+/o0fDMtv2is6aIMBFO4Pq5K5MQ0ESl2Q1/lrQseYqgQbQpKLAaKhmldVJFGCMOlH82qXOnwgQ8RlUlwAbVAYansCMgyrNQASS3Wdj+mjPRjubbT436s5UT2/Tv4+9IaI2fwE1BAGlw2ip8YXZsgfkDI1R7XZpSxiUWx85zfbbcMdqXyOyPM68k4rVksmS5eDb2e2ZJEesRRDo3KLLnGanGlYkMFMpAuBVx",
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": "\"Windows\"",
            "bx-v": "2.5.28",
            "origin": "https://chat.qwen.ai",
            "sec-fetch-site": "same-origin",
            "sec-fetch-mode": "cors",
            "sec-fetch-dest": "empty",
            "referer": "https://chat.qwen.ai/",
            "accept-language": "zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7",
            "priority": "u=1, i"
        }
        
        # 添加认证和cookie
        headers["authorization"] = f"Bearer {auth_token}"
        headers["cookie"] = f"_gcl_au=1.1.828597960.1740456102;cna=qS5EIEcjlH0BASQOBGAZfs5p;acw_tc=13b5be1680f7cde2106f40ee928d097af327aba086a9228880897a73ecb3aafb;token={auth_token};xlly_s=1;ssxmod_itna=mqUxRDBDnD00I4eKYIxAK0QD2W3nDAQDRDl4Bti=GgexFqAPqDHIa3vY8i0W0DjObNem07GneDl=24oDSxD6HDK4GTmzgh2rse77ObPpKYQ7R2xK7Amx4cTilPo+gY=GEUPn3rMI6FwDCPDExGkPrmrDeeaDCeDQxirDD4DADibe4D1GDDkD0+m7UovW4GWDm+mDWPDYxDrbRYDRPxD0ZmGDQI3aRDDBgGqob0CESfGR4bUO+hLGooD9E4DsO2nQYO6Wk=qGS8uG13bQ40kmq0OC4bAeILQa38vvb4ecEDoV=mxYamN10DOK0ZIGNjGN0DK02kt+4j0xRG4lhrQwFfYoDDWmAq8es8mGmACAT1ju1m7YTi=eDofhpY847DtKYxIO+gG=lDqeDpFidgOD/MhKhx4D;ssxmod_itna2=mqUxRDBDnD00I4eKYIxAK0QD2W3nDAQDRDl4Bti=GgexFqAPqDHIa3vY8i0W0DjObNem07GeDAYg25EoK0Gx03K+UeDsXWBk3hA77G1R5XFltYQ0EqlfYj5XW2iYjxf3l4tdco06thrWXGiW+cFHXQrO7QxF/CydRcHQsPA4LxPFc=AxoKpPD1F1bEPz/O283eHkOiYG/7DFLZbOozFFbZbH/BwaKjcF7Sn1r/psVBEWv9MP69pCFgqGiScCq/406p8WDwrXDtjP7hDaYUP4updgT0HrO/Y0god6QnKGD8DqhqYsqGDwYtP9Yt4oPQhAZDYqbPD=DzhYE26QPARiDKo6BGGzaoXn6dKPemrM2PKZYfAQ/DiN7PE2vV0DbiDGQmVepx7GUBhxPT2B5/1ufDRN4d8/hM7E6emvnuNtDwRjdi4blREb4wGq10qgl5dicH8eQnexD;SERVERID=0a3251b1bff13a18b856bcf1852f8829|1740834371|1740834361;SERVERCORSID=0a3251b1bff13a18b856bcf1852f8829|1740834371|1740834361;tfstk=gPzmGd62kooXVyepH8ufvlDQWTIRGIgsxRLtBVHN4Yk7kRIjBu0aTJmtbiZYEIauKFLAhiNwSV3Np9QdJSNo5VWp4f9awKGjiF7tQn-rlfUww0dFJSNXauNajS_pIvg355kaQmor4jHrgno4Q4RrMY8q_ElwU_csUVlq0m-zafh6gfkaQ75o1YkZ7Vl09Fk37zaPUrRE4Yhm4zcmmvPlAF8MojJKpSkJ7FkmimqYgYYw7zqRLJ-s3MO-CqHbZj21REgqjlzxzrWP72rQEPmE-GCj05quCqUP_nkUD-3zukAw77000caZxKXoLrNzR4oR86VzP-Fbr5dN7beKUSaqSw5IoqkqrbaOFEkg4lzxcV9VIAauarrG4RtyYw1y53D94hts0bGopKGwPsvDzz35Z_xCcmlSM9ClZhOq0bGIJ_fkYeoqNjel.;isg=BPz8BdNVt0zUyoPuxsZIFaJNzZqu9aAfdEJYtdZ9jOfKoZ4r_gYOroLXhcnZ6dh3"
                
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