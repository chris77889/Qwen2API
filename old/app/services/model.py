"""
模型服务
"""
from typing import Dict, Any, List, Optional
import json
import httpx
from pathlib import Path
import asyncio
from ..core.logger import logger
from .account import account_manager
from ..core.config import config_manager

class ModelServiceError(Exception):
    """模型服务相关错误"""
    pass

class ModelService:
    """模型服务"""
    
    # 模型功能后缀
    MODEL_FEATURES = [
        '',  # 基础模型
        '-thinking',  # 思考模式
        '-search',  # 搜索模式
        '-thinking-search',  # 思考+搜索模式
        '-draw',  # 绘图模式
        '-video'  # 视频生成模式
    ]
    
    def __init__(self):
        """初始化模型服务"""
        self.base_url = config_manager.get("api.url", "https://chat.qwen.ai")
        self.model_file = Path("model.json")
        self._models: List[Dict[str, Any]] = []
        self._load_models_from_file()
        
    def _convert_to_openai_format(self, model_id: str) -> List[Dict[str, Any]]:
        """
        将通义千问模型ID转换为OpenAI格式，并添加功能后缀
        
        Args:
            model_id: 通义千问模型ID
            
        Returns:
            List[Dict[str, Any]]: OpenAI格式的模型信息列表
        """
        return [{
            "id": f"{model_id}{suffix}",
            "object": "model",
            "created": 0,
            "owned_by": "qwen"
        } for suffix in self.MODEL_FEATURES]
        
    def _load_models_from_file(self) -> None:
        """从model.json文件加载模型列表，如果文件不存在或加载失败则从API获取"""
        try:
            if self.model_file.exists():
                data = json.loads(self.model_file.read_text(encoding='utf-8'))
                self._models = data.get('data', [])
                if self._models:
                    return
            self._fetch_and_save_models()
        except Exception as e:
            logger.error(f"加载模型列表失败: {str(e)}")
            self._fetch_and_save_models()
            
    def _fetch_and_save_models(self) -> None:
        """从API获取模型列表并保存到文件"""
        try:
            with httpx.Client() as client:
                auth_token = account_manager.get_account_token()
                response = client.get(
                    f"{self.base_url}/models",
                    headers=account_manager.get_headers(auth_token),
                    timeout=30.0
                )
                
                if response.status_code == 200:
                    models_data = response.json()
                    if not models_data or 'data' not in models_data:
                        raise ModelServiceError("API返回的模型数据格式错误")
                        
                    self._models = []
                    for item in models_data['data']:
                        if model_id := item.get('id'):
                            self._models.extend(self._convert_to_openai_format(model_id))
                    self._save_models_to_file()
                    return
                        
                raise ModelServiceError(f"API请求失败: {response.status_code}")
                
        except Exception as e:
            logger.error(f"从API获取模型列表失败: {str(e)}")
            self._models = []
            
    def _save_models_to_file(self) -> None:
        """将当前模型列表保存到文件"""
        try:
            self.model_file.write_text(
                json.dumps({
                    "object": "list",
                    "data": self._models
                }, ensure_ascii=False, indent=2),
                encoding='utf-8'
            )
        except Exception as e:
            logger.error(f"保存模型列表失败: {str(e)}")
            
    def set_models(self, models: List[str]) -> None:
        """
        设置模型列表并保存到文件
        
        Args:
            models: 新的模型列表
        """
        self._models = []
        for model in models:
            self._models.extend(self._convert_to_openai_format(model))
        self._save_models_to_file()
        
    async def get_models(self) -> List[Dict[str, Any]]:
        """
        获取可用模型列表，优先使用缓存，失败时从API获取
        
        Returns:
            List[Dict[str, Any]]: OpenAI格式的模型列表
        """
        if self._models:
            return self._models
            
        try:
            auth_token = account_manager.get_account_token()
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{self.base_url}/models",
                    headers=account_manager.get_headers(auth_token),
                    timeout=30.0
                )
                
                if response.status_code == 200:
                    models_data = response.json()
                    if not models_data or 'data' not in models_data:
                        raise ModelServiceError("API返回的模型数据格式错误")
                        
                    self._models = []
                    for item in models_data['data']:
                        if model_id := item.get('id'):
                            self._models.extend(self._convert_to_openai_format(model_id))
                    self._save_models_to_file()
                    return self._models
                    
                raise ModelServiceError(f"API请求失败: {response.status_code}")
                
        except Exception as e:
            logger.error(f"从API获取模型列表失败: {str(e)}")
            return self._models
        
    async def verify_model_with_feature(self, model: str) -> str:
        """
        验证模型是否支持特定功能，如果不支持则返回默认模型
        
        Args:
            model: 要验证的模型名
            
        Returns:
            str: 有效的模型名
        """
        # 获取基础模型（去除所有后缀）
        base_model = model
        for suffix in self.MODEL_FEATURES:
            if suffix:  # 跳过空字符串
                base_model = base_model.replace(suffix, '')
        
        # 验证基础模型是否存在
        models = await self.get_models()
        model_ids = [m['id'] for m in models]
        
        if base_model not in model_ids:
            logger.warning(f"模型 {base_model} 不在支持列表中，降级到默认模型 qwq-32b")
            return "qwq-32b"
        
        return model

# 创建全局模型服务实例
model_service = ModelService() 