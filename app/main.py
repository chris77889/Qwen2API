"""
通义千问API服务主程序
"""
import uvicorn
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.router.account import router as account_router
from app.router.model import router as model_router
from app.router.chat import router as chat_router
from app.core.logger.logger import get_logger
from app.core.config_manager import ConfigManager
from app.core.account_manager import AccountManager

logger = get_logger(__name__)
config_manager = ConfigManager()
account_manager = AccountManager()
# 创建FastAPI实例
app = FastAPI(
    title="通义千问 API",
    description="Python版通义千问API服务",
    version="1.0.0"
)

# 添加CORS中间件
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册API路由
app.include_router(account_router)
app.include_router(model_router)
app.include_router(chat_router)
def get_start_info() -> str:
    """
    获取启动信息字符串
    
    Returns:
        str: 启动信息
    """
    listen_address = config_manager.get("api.listen_address", "0.0.0.0")
    service_port = config_manager.get("api.port", 8000)
    api_prefix = "/v1"
    account_count = len(account_manager.get_enabled_accounts())
    api_keys_count = len(config_manager.get("api.api_keys", []))
    
    return f"""
-------------------------------------------------------------------
监听地址：{listen_address}
服务端口：{service_port}
API前缀：{api_prefix}
账户数：{account_count}
API密钥数：{api_keys_count}
-------------------------------------------------------------------
    """