import yaml
from typing import Any, Dict, List, Optional, Union
import os
from pathlib import Path
from copy import deepcopy
from loguru import logger

class ConfigManager:
    def __init__(self, config_path: str = "config/config.yaml"):
        """
        初始化配置管理器
        
        Args:
            config_path: 配置文件路径
        """
        self.config_path = config_path
        self.config = {}
        self.load_config()

    def load_config(self) -> None:
        """加载配置文件"""
        if not os.path.exists(self.config_path):
            logger.error(f"配置文件不存在: {self.config_path}")
            raise FileNotFoundError(f"配置文件不存在: {self.config_path}")

        with open(self.config_path, 'r', encoding='utf-8') as f:
            self.config = yaml.safe_load(f)
            if not self.config:
                logger.error(f"配置文件为空: {self.config_path}")
                raise ValueError(f"配置文件为空: {self.config_path}")

    def save_config(self) -> None:
        """保存配置到文件"""
        try:
            os.makedirs(os.path.dirname(self.config_path), exist_ok=True)
            with open(self.config_path, 'w', encoding='utf-8') as f:
                yaml.safe_dump(self.config, f, allow_unicode=True)
            logger.info(f"配置已保存到: {self.config_path}")
        except Exception as e:
            logger.error(f"保存配置失败: {str(e)}")
            raise

    def get(self, path: str, default: Any = None) -> Any:
        """
        获取配置值
        
        Args:
            path: 配置路径，使用点号分隔，如 'api.host'
            default: 默认值，如果配置项不存在时返回默认值
        Returns:
            Any: 配置值
        
        Raises:
            KeyError: 配置项不存在时抛出异常
        """
        keys = path.split('.')
        value = self.config
        
        for key in keys:
            if not isinstance(value, dict):
                logger.error(f"配置路径无效: {path}")
                raise KeyError(f"配置路径无效: {path}")
            
            if key not in value and default is not None:
                return default
                
            value = value[key]
        
        return value

    def set(self, path: str, value: Any) -> None:
        """
        设置配置值
        
        Args:
            path: 配置路径，使用点号分隔，如 'api.host'
            value: 要设置的值
        """
        keys = path.split('.')
        config = self.config
        
        # 遍历到最后一个键之前
        for key in keys[:-1]:
            if key not in config:
                config[key] = {}
            elif not isinstance(config[key], dict):
                logger.error(f"配置路径无效: {path}")
                raise KeyError(f"配置路径无效: {path}")
            config = config[key]
            
        # 设置最后一个键的值
        config[keys[-1]] = value
        self.save_config()
        logger.info(f"已更新配置: {path} = {value}")

    def delete(self, path: str) -> None:
        """
        删除配置项
        
        Args:
            path: 配置路径，使用点号分隔，如 'api.host'
            
        Raises:
            KeyError: 配置项不存在时抛出异常
        """
        keys = path.split('.')
        config = self.config
        
        # 遍历到最后一个键之前
        for key in keys[:-1]:
            if key not in config:
                logger.error(f"配置项不存在: {path}")
                raise KeyError(f"配置项不存在: {path}")
            config = config[key]
            
        # 删除最后一个键
        if keys[-1] not in config:
            logger.error(f"配置项不存在: {path}")
            raise KeyError(f"配置项不存在: {path}")
            
        del config[keys[-1]]
        self.save_config()
        logger.info(f"已删除配置项: {path}")

    def get_section(self, section: str) -> Dict:
        """
        获取整个配置部分
        
        Args:
            section: 配置部分名称，如 'api'
        
        Returns:
            Dict: 配置部分的内容
            
        Raises:
            KeyError: 配置部分不存在时抛出异常
        """
        if section not in self.config:
            logger.error(f"配置部分不存在: {section}")
            raise KeyError(f"配置部分不存在: {section}")
        return dict(self.config[section])

    def update_section(self, section: str, values: Dict) -> None:
        """
        更新配置部分
        
        Args:
            section: 配置部分名称，如 'api'
            values: 要更新的值
        """
        if section not in self.config:
            self.config[section] = {}
        
        def deep_update(d: Dict, u: Dict) -> None:
            for k, v in u.items():
                if isinstance(v, dict) and k in d and isinstance(d[k], dict):
                    deep_update(d[k], v)
                else:
                    d[k] = v
        
        deep_update(self.config[section], values)
        self.save_config()
        logger.info(f"已更新配置部分: {section}")

    def get_all(self) -> Dict:
        """
        获取所有配置
        
        Returns:
            Dict: 所有配置的副本
        """
        return dict(self.config)

    def exists(self, path: str) -> bool:
        """
        检查配置项是否存在
        
        Args:
            path: 配置路径，使用点号分隔，如 'api.host'
        
        Returns:
            bool: 配置项是否存在
        """
        try:
            self.get(path)
            return True
        except KeyError:
            return False 