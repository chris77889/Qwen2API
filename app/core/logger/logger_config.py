import logging
from app.core.logger.logger import setup_logger, InterceptHandler, get_logger, loguru_logger
from app.core.config_manager import ConfigManager

def configure_logging():
    """
    配置全局日志系统
    """
    # 获取配置
    config_manager = ConfigManager()
    log_file = config_manager.get("log.file_path", "logs/app.log")
    log_level = config_manager.get("log.level", "INFO")

    # 定义日志过滤器
    def log_filter(record):
        """过滤掉不需要的日志"""
        # 过滤掉 uvicorn.protocols.http.h11_impl 的日志
        if record["name"].startswith("uvicorn.protocols.http.h11_impl"):
            return False
        return True

    # 初始化全局日志（清除之前所有 sink）
    root_logger = setup_logger(
        name=None,  # 根记录器
        log_file=log_file,
        level=log_level,
        format="<level>[{level}]</level> - <blue>{time:YYYY-MM-DD HH:mm:ss}</blue> - <magenta>{name}</magenta> - <level>{message}</level>",
        rotation="10 MB",
        retention="1 week",
        filter=log_filter  # 添加过滤器
    )

    # 配置需要统一处理的 logger 列表
    loggers = [
        logging.getLogger(),           # 根记录器
        logging.getLogger('fastapi'),
        logging.getLogger('uvicorn'),
        logging.getLogger('uvicorn.access'),
        logging.getLogger('uvicorn.error'),
        logging.getLogger('question_service'),
        logging.getLogger('middleware'),
        logging.getLogger('service'),
    ]
    
    for logger_obj in loggers:
        logger_obj.handlers = []
        logger_obj.addHandler(InterceptHandler())
        logger_obj.setLevel(log_level)
        logger_obj.propagate = False


    return root_logger
