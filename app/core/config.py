"""
简化版配置管理服务
"""
from typing import Any, Dict
import yaml
from pathlib import Path

from .logger import logger


class ConfigManager:
    """配置管理器"""
    
    def __init__(self):
        """初始化配置管理器"""
        self.config_file = Path("config.yaml")
        self.config: Dict[str, Any] = {}
        self.load_config()
        
    def load_config(self) -> None:
        """加载配置文件"""
        try:
            if self.config_file.exists():
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    self.config = yaml.safe_load(f) or {}
        except Exception as e:
            logger.error(f"配置文件加载错误: {e}")
            self.config = {}
            
    def save_config(self) -> None:
        """保存配置文件"""
        try:
            with open(self.config_file, 'w', encoding='utf-8') as f:
                yaml.safe_dump(self.config, f, allow_unicode=True)
        except Exception as e:
            logger.error(f"配置文件保存错误: {e}")
            
    def get(self, path: str, default: Any = None) -> Any:
        """
        获取配置值
        
        Args:
            path: 配置路径，使用点号分隔
            default: 默认值
            
        Returns:
            Any: 配置值
        """
        current = self.config
        try:
            for key in path.split('.'):
                current = current[key]
            return current
        except (KeyError, TypeError):
            return default
    
    def set(self, path: str, value: Any) -> None:
        """
        设置配置值
        
        Args:
            path: 配置路径，使用点号分隔
            value: 配置值
        """
        keys = path.split('.')
        current = self.config
        
        for key in keys[:-1]:
            if key not in current:
                current[key] = {}
            elif not isinstance(current[key], dict):
                current[key] = {}
            current = current[key]
            
        current[keys[-1]] = value
        self.save_config()


# 创建全局配置管理器实例
config_manager = ConfigManager() 