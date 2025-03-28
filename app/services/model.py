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

# 定义model.json文件路径
MODEL_FILE_PATH = Path("model.json")

class ModelService:
    """模型服务"""
    
    def __init__(self):
        """初始化模型服务"""
        self.base_url = config_manager.CONSTANTS["QWEN_API_URL"]
        self._models = []
        self._load_models_from_file()
        
    def _convert_to_openai_format(self, model_id: str) -> List[Dict[str, Any]]:
        """
        将通义千问模型ID转换为OpenAI格式，并添加功能后缀
        
        Args:
            model_id: 通义千问模型ID
            
        Returns:
            List[Dict[str, Any]]: OpenAI格式的模型信息列表
        """
        models = []
        # 基础模型
        models.append({
            "id": model_id,
            "object": "model",
            "created": 0,
            "owned_by": "qwen"
        })
        
        # 思考模式
        models.append({
            "id": f"{model_id}-thinking",
            "object": "model",
            "created": 0,
            "owned_by": "qwen"
        })
        
        # 搜索模式
        models.append({
            "id": f"{model_id}-search",
            "object": "model",
            "created": 0,
            "owned_by": "qwen"
        })
        
        # 思考+搜索模式
        models.append({
            "id": f"{model_id}-thinking-search",
            "object": "model",
            "created": 0,
            "owned_by": "qwen"
        })
        
        # 绘图模式
        models.append({
            "id": f"{model_id}-draw",
            "object": "model",
            "created": 0,
            "owned_by": "qwen"
        })
        
        # 视频生成模式
        #models.append({
        #    "id": f"{model_id}-video",
        #    "object": "model",
        #    "created": 0,
        #    "owned_by": "qwen"
        #})
        
        return models
        
    def _load_models_from_file(self) -> None:
        """
        从model.json文件加载模型列表
        如果文件不存在，则从API获取并保存
        """
        try:
            if MODEL_FILE_PATH.exists():
                with open(MODEL_FILE_PATH, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self._models = data.get('data', [])
            else:
                # 文件不存在时，从API获取模型列表
                self._fetch_and_save_models()
        except Exception as e:
            logger.error(f"加载模型列表失败: {str(e)}")
            self._fetch_and_save_models()
            
    def _fetch_and_save_models(self) -> None:
        """
        从API获取模型列表并保存到文件
        """
        try:
            # 创建同步HTTP客户端
            with httpx.Client() as client:
                # 获取认证令牌
                auth_token = account_manager.get_account_token()
                headers = account_manager.get_headers(auth_token)
                
                # 发送请求
                response = client.get(
                    f"{self.base_url}/models",
                    headers=headers,
                    timeout=30.0
                )
                
                if response.status_code == 200:
                    models_data = response.json()
                    if models_data and 'data' in models_data:
                        # 为每个模型添加功能后缀
                        self._models = []
                        for item in models_data['data']:
                            model_id = item.get('id')
                            if model_id:
                                self._models.extend(self._convert_to_openai_format(model_id))
                        self._save_models_to_file()
                        return
                        
            logger.error("从API获取模型列表失败")
            self._models = []
            
        except Exception as e:
            logger.error(f"从API获取模型列表失败: {str(e)}")
            self._models = []
            
    def _save_models_to_file(self) -> None:
        """
        将当前模型列表保存到model.json文件
        使用OpenAI格式
        """
        try:
            with open(MODEL_FILE_PATH, 'w', encoding='utf-8') as f:
                json.dump({
                    "object": "list",
                    "data": self._models
                }, f, ensure_ascii=False, indent=2)
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
        获取可用模型列表
        
        Returns:
            List[Dict[str, Any]]: OpenAI格式的模型列表
        """
        # 如果已经有缓存的模型列表，则直接返回
        if self._models:
            return self._models
            
        try:
            # 从API获取最新的模型列表
            auth_token = account_manager.get_account_token()
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{self.base_url}/models",
                    headers=account_manager.get_headers(auth_token),
                    timeout=30.0
                )
                
                if response.status_code == 200:
                    models_data = response.json()
                    if models_data and 'data' in models_data:
                        # 为每个模型添加功能后缀
                        self._models = []
                        for item in models_data['data']:
                            model_id = item.get('id')
                            if model_id:
                                self._models.extend(self._convert_to_openai_format(model_id))
                        self._save_models_to_file()
                        return self._models
                        
        except Exception as e:
            logger.error(f"从API获取模型列表失败: {str(e)}")
            
        # 如果API请求失败，返回文件中的模型列表
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
        for suffix in ['-thinking', '-search', '-thinking-search', '-draw', '-video']:
            base_model = base_model.replace(suffix, '')
        
        # 验证基础模型是否存在
        models = await self.get_models()
        model_ids = [m['id'] for m in models]
        
        if base_model not in model_ids:
            # 如果基础模型不在列表中，则降级到默认模型
            logger.warning(f"模型 {base_model} 不在支持列表中，降级到默认模型 qwq-32b")
            return "qwq-32b"
        
        return model

# 创建全局模型服务实例
model_service = ModelService() 