import os
import uvicorn
from app.main import app, get_start_info
from app.core.logger.logger import get_logger
from app.core.config_manager import ConfigManager

logger = get_logger(__name__)
config_manager = ConfigManager()
    
if __name__ == "__main__":
    # 从配置管理器获取配置
    listen_address = config_manager.get('api.host')
    service_port = config_manager.get('api.port')
    reload_enabled = config_manager.get('api.reload', False)
    
    # 打印启动信息
    logger.info(get_start_info())
    
    # 启动服务器
    uvicorn.run(
        "app.main:app", 
        host=listen_address, 
        port=service_port,
        reload=reload_enabled
    ) 