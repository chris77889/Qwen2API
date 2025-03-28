"""
配置管理服务
"""
from typing import Any, Dict, List, Optional, Union
import yaml
from pathlib import Path
import os

from .logger import logger


class ConfigManager:
    """配置管理器"""
    
    def __init__(self):
        """初始化配置管理器"""
        self.config_file = Path("config.yaml")
        self.config: Dict[str, Any] = {}
        
        # 硬编码的常量配置
        self.CONSTANTS = {
            # 硬编码的通义千问API请求参数
            "QWEN_API_URL": "https://chat.qwen.ai/api",
            "QWEN_DEFAULT_MODEL": "qwen-max-latest",
            "QWEN_IMAGE_MODEL": "qwen-max-latest",
            "QWEN_VIDEO_MODEL": "qwen-max-latest",  # 视频生成模型
            # 硬编码的图像尺寸选项
            "IMAGE_SIZES": ["256x256", "512x512", "1024x1024"],
            # 硬编码的视频尺寸选项
            "VIDEO_SIZES": ["1280x720"],  # 16:9
            # 硬编码的聊天特性 
            "THINK_TAG_START": "<think>",
            "THINK_TAG_END": "</think>",
            # 允许的文件类型
            "ALLOWED_FILE_TYPES": [
                "txt", "pdf", "doc", "docx", "md",
                "png", "jpg", "jpeg", "gif", "webp",
                "mp4", "mov", "avi"  # 添加视频格式支持
            ],
        }
        
        # 默认配置
        self.default_config = {
            "api": {
                "host": "0.0.0.0",
                "port": 2778,
                "debug": False,
                "reload": False,
                "workers": 1,
                "api_keys": [os.urandom(16).hex()],
                "enable_api_key": True
            },
            "chat": {
                "model": self.CONSTANTS["QWEN_DEFAULT_MODEL"],
                "search_info_mode": "table"
            },
            "image": {
                "model": self.CONSTANTS["QWEN_IMAGE_MODEL"],
                "size": "1024x1024",
            },
            "video": {  # 添加视频配置
                "model": self.CONSTANTS["QWEN_VIDEO_MODEL"],
                "size": "1280x720",
            },
            "upload": {
                "enable": True,
                "max_size": 10,  # MB
                "save_path": "uploads"
            },
        }
        
        self.load_config()
        
    def load_config(self) -> None:
        """加载配置文件"""
        try:
            if self.config_file.exists():
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    self.config = yaml.safe_load(f) or {}
            else:
                self.config = {}
                
            # 合并默认配置
            self.config = self._deep_merge(self.default_config, self.config)
            self.save_config()
            
        except Exception as e:
            logger.error(f"配置文件加载错误: {e}")
            self.config = self.default_config.copy()
            self.save_config()
            
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
        
    def _deep_merge(self, dict1: Dict[str, Any], dict2: Dict[str, Any]) -> Dict[str, Any]:
        """
        深度合并两个字典
        
        Args:
            dict1: 基础字典
            dict2: 要合并的字典
            
        Returns:
            Dict[str, Any]: 合并后的字典
        """
        result = dict1.copy()
        
        for key, value in dict2.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                result[key] = self._deep_merge(result[key], value)
            else:
                result[key] = value
                
        return result
    
    # 常用配置项的访问方法
    def get_api_keys(self) -> List[str]:
        """获取API密钥列表"""
        api_keys = self.get('api.api_keys', [])
        if api_keys:
            logger.debug(f"从环境变量获取到API密钥")
            logger.debug(f"API密钥列表: {api_keys}")
            return api_keys
        return []
    
    def is_api_key_valid(self, api_key: str) -> bool:
        """验证API密钥是否有效"""
        return api_key in self.get_api_keys()
    
    def is_api_key_required(self) -> bool:
        """检查是否启用API密钥认证"""
        return self.get('api.enable_api_key', False)
    
    
    def get_upload_config(self) -> Dict[str, Any]:
        """获取上传配置"""
        config = self.get('upload', {})
        # 始终使用硬编码的允许文件类型列表
        config['allowed_types'] = self.CONSTANTS["ALLOWED_FILE_TYPES"]
        return config
        
    def get_model_config(self, model_type: str = "chat") -> Dict[str, Any]:
        """获取模型配置"""
        if model_type == "image":
            return self.get('image', {})
        elif model_type == "video":
            return self.get('video', {})
        else:
            return self.get('chat', {})


# 创建全局配置管理器实例
config_manager = ConfigManager() 