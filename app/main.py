"""
通义千问API服务主程序
"""
import uvicorn
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import time
import platform

from .api.v1.api import api_router
from .core.config import config_manager
from .core.logger import logger
from .services.account import account_manager

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
app.include_router(api_router, prefix="/v1")


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


if __name__ == "__main__":
    # 获取配置
    listen_address = config_manager.get("api.listen_address", "0.0.0.0")
    service_port = config_manager.get("api.port", 8000)
    
    # 打印启动信息
    print(get_start_info())
    
    # 启动服务器
    uvicorn.run(
        "app.main:app",
        host=listen_address,
        port=service_port,
        reload=True
    ) 