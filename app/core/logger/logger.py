import sys
import logging
from pathlib import Path
from typing import Union, Any, Protocol, runtime_checkable
from loguru import logger as loguru_logger
from loguru._logger import Logger

@runtime_checkable
class LoggerProtocol(Protocol):
    """日志记录器协议，定义了日志记录器应该具有的方法"""
    def debug(self, __message: str, *args: Any, **kwargs: Any) -> None: ...
    def info(self, __message: str, *args: Any, **kwargs: Any) -> None: ...
    def warning(self, __message: str, *args: Any, **kwargs: Any) -> None: ...
    def error(self, __message: str, *args: Any, **kwargs: Any) -> None: ...
    def critical(self, __message: str, *args: Any, **kwargs: Any) -> None: ...
    def exception(self, __message: str, *args: Any, **kwargs: Any) -> None: ...
    def log(self, __level: str, __message: str, *args: Any, **kwargs: Any) -> None: ...
    def bind(self, **kwargs: Any) -> Any: ...

class InterceptHandler(logging.Handler):
    """
    将标准 logging 的日志重定向到 loguru
    """
    def emit(self, record: logging.LogRecord) -> None:
        try:
            level = loguru_logger.level(record.levelname).name
        except ValueError:
            level = record.levelno

        frame, depth = sys._getframe(6), 6
        while frame and frame.f_code.co_filename == logging.__file__:
            frame = frame.f_back
            depth += 1

        loguru_logger.opt(depth=depth, exception=record.exc_info).log(
            level, record.getMessage()
        )

def setup_logger(
    name: Union[str, None] = None,
    log_file: str = "logs/app.log",
    level: Union[str, int] = "INFO",
    rotation: str = "10 MB",
    retention: str = "1 week",
    format: str = (
        "<level>[{level}]</level> - "
        "<blue>{time:YYYY-MM-DD HH:mm:ss}</blue> - "
        "<magenta>{name}</magenta> - "
        "<level>{message}</level>"
    ),
    filter: Any = None
) -> logging.Logger:
    """
    全局初始化 loguru 日志记录器，并配置标准 logging 拦截到 loguru 中。
    注意：全局初始化只应在入口处调用一次。
    """
    # 清除所有已有 sink（仅用于全局初始化）
    loguru_logger.remove()

    # 添加控制台输出
    loguru_logger.add(
        sys.stdout,
        format=format,
        level=level,
        colorize=True,
        filter=filter
    )

    # 添加文件输出
    file_path = Path(log_file)
    file_path.parent.mkdir(parents=True, exist_ok=True)
    loguru_logger.add(
        str(file_path),
        rotation=rotation,
        retention=retention,
        format=format,
        level=level,
        encoding="utf-8",
        filter=filter
    )

    # 配置标准 logging 拦截到 loguru
    logging_logger = logging.getLogger(name) if name else logging.getLogger()
    logging_logger.handlers.clear()
    logging_logger.addHandler(InterceptHandler())
    logging_logger.setLevel(level)

    return logging_logger

def get_logger(name: str) -> LoggerProtocol:
    """
    获取绑定指定名称的 loguru 日志记录器，绑定 extra 字段，用于日志格式中显示模块名称
    """
    return loguru_logger.bind(name=name)
