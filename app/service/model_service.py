"""
模型服务
"""

from typing import Dict, Any, List, Optional
import json
from pathlib import Path
import httpx
from app.core.logger.logger import get_logger
from app.core.cookie_service import CookieService
from app.core.account_manager import AccountManager
from app.core.config_manager import ConfigManager

config_manager = ConfigManager()

logger = get_logger(__name__)


class ModelServiceError(Exception):
    """模型服务相关错误"""

    pass


class ModelService:
    """模型服务"""

    # 模型功能后缀
    MODEL_FEATURES = [
        "",  # 基础模型
        "-thinking",  # 思考模式
        "-search",  # 搜索模式
        "-thinking-search",  # 思考+搜索模式
        "-draw",  # 绘图模式
        "-video",  # 视频生成模式
    ]

    # 模型配置映射
    MODEL_CONFIGS = {
        "base": {  # 基础模型配置
            "completion": {
                "chat_type": "t2t",
                "sub_chat_type": "t2t",
                "chat_mode": "normal",
            },
            "message": {
                "feature_config": {
                    "thinking_enabled": False,
                    "output_schema": "phase",
                }
            },
        },
        "thinking": {  # 思考模式配置
            "completion": {
                "chat_type": "t2t",
                "sub_chat_type": "t2t",
                "chat_mode": "normal",
            },
            "message": {
                "feature_config": {
                    "thinking_enabled": True,
                    "output_schema": "phase",
                    "thinking_budget": 38912,
                }
            },
        },
        "search": {  # 搜索模式配置
            "completion": {
                "chat_type": "t2t",
                "sub_chat_type": "t2t",
                "chat_mode": "normal",
            },
            "message": {
                "chat_type": "search",
                "feature_config": {
                    "thinking_enabled": False,
                    "output_schema": "phase",
                },
            },
        },
        "thinking-search": {  # 思考+搜索模式配置
            "completion": {
                "chat_type": "t2t",
                "sub_chat_type": "t2t",
                "chat_mode": "normal",
            },
            "message": {
                "chat_type": "search",
                "feature_config": {
                    "thinking_enabled": True,
                    "output_schema": "phase",
                    "thinking_budget": 38912,
                },
            },
        },
        "draw": {  # 绘图模式配置
            "completion": {
                "chat_type": "t2i",
                "sub_chat_type": "t2i",
                "chat_mode": "normal",
                "stream": False,
                "size": config_manager.get("image.size", "1:1"),
            },
            "message": {
                "chat_type": "t2i",
                "feature_config": {"thinking_enabled": False, "output_schema": "phase"},
            },
        },
        "video": {  # 视频生成模式配置
            "completion": {
                "chat_type": "t2v",
                "sub_chat_type": "t2v",
                "chat_mode": "normal",
                "stream": False,
                "size": config_manager.get("video.size", "1280x720"),
            },
            "message": {
                "chat_type": "t2v",
                "feature_config": {"thinking_enabled": False, "output_schema": "phase"},
            },
        },
        # 还有artifacts，不过没什么用就不加了
    }

    def __init__(self):
        """初始化模型服务"""

        self.model_file = Path("data/model.json")
        self._models: List[Dict[str, Any]] = []
        self.account_manager = AccountManager()
        self.cookie_service = CookieService(self.account_manager)
        self.config_manager = ConfigManager()
        self.base_url = self.config_manager.get("api.url", "https://chat.qwen.ai/api")
        self._load_models_from_file()

    def _convert_to_openai_format(self, model_id: str) -> List[Dict[str, Any]]:
        """
        将通义千问模型ID转换为OpenAI格式，并添加功能后缀

        Args:
            model_id: 通义千问模型ID

        Returns:
            List[Dict[str, Any]]: OpenAI格式的模型信息列表
        """
        return [
            {
                "id": f"{model_id}{suffix}",
                "object": "model",
                "created": 0,
                "owned_by": "qwen",
            }
            for suffix in self.MODEL_FEATURES
        ]

    def _load_models_from_file(self) -> None:
        """从model.json文件加载模型列表，如果文件不存在或加载失败则从API获取"""
        try:
            if self.model_file.exists():
                data = json.loads(self.model_file.read_text(encoding="utf-8"))
                self._models = data.get("data", [])
                if self._models:
                    return
            self._fetch_and_save_models()
        except Exception as e:
            logger.error(f"加载模型列表失败: {str(e)}")
            self._fetch_and_save_models()

    async def _fetch_and_save_models(self) -> None:
        """从API获取模型列表并保存到文件"""
        try:
            auth_token = self.cookie_service.get_auth_token()
            headers = self.cookie_service.get_headers(auth_token)

            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{self.base_url}/models/", headers=headers, timeout=30.0
                )
                text = await response.aread()
                print(text)
                if response.status_code == 200:
                    models_data = response.json()
                    if not models_data or "data" not in models_data:
                        raise ModelServiceError("API返回的模型数据格式错误")

                    self._models = []
                    for item in models_data["data"]["data"]:
                        if model_id := item.get("id"):
                            self._models.extend(
                                self._convert_to_openai_format(model_id)
                            )
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
                json.dumps(
                    {"object": "list", "data": self._models},
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
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

    async def get_models(self) -> Dict[str, Any]:
        """
        获取可用模型列表，优先使用缓存，失败时从API获取

        Returns:
            Dict[str, Any]: 包含object和data字段的模型列表
        """
        if self._models:
            return {"object": "list", "data": self._models}

        await self._fetch_and_save_models()
        return {"object": "list", "data": self._models}

    async def refresh_models(self) -> None:
        """刷新模型列表"""
        await self._fetch_and_save_models()

    def get_completion_config(self, model: str) -> Dict[str, Any]:
        """
        获取模型的completion service配置参数

        Args:
            model: 模型名称

        Returns:
            Dict[str, Any]: completion service配置参数
        """
        # 提取特性后缀
        feature = "base"
        for suffix in self.MODEL_FEATURES:
            if suffix and model.endswith(suffix):
                feature = suffix.lstrip("-")
                break

        # 获取配置
        config = self.MODEL_CONFIGS.get(feature, {}).get("completion", {})
        if not config:
            # 如果没有找到配置，使用基础配置
            config = self.MODEL_CONFIGS["base"]["completion"]

        return config

    def get_message_feature_config(self, model: str) -> Dict[str, Any]:
        """
        获取模型的message特性配置

        Args:
            model: 模型名称

        Returns:
            Dict[str, Any]: message特性配置
        """
        # 提取特性后缀
        feature = "base"
        for suffix in self.MODEL_FEATURES:
            if suffix and model.endswith(suffix):
                feature = suffix.lstrip("-")
                break

        # 获取配置
        config = self.MODEL_CONFIGS.get(feature, {}).get("message", {})
        if not config:
            # 如果没有找到配置，使用基础配置
            config = self.MODEL_CONFIGS["base"]["message"]

        return config

    def get_model_config(self, model: str) -> Dict[str, Any]:
        """
        获取模型的完整配置（包括completion和message配置）

        Args:
            model: 模型名称

        Returns:
            Dict[str, Any]: 完整配置
        """
        completion_config = self.get_completion_config(model)
        message_config = self.get_message_feature_config(model)

        return {"completion": completion_config, "message": message_config}

    async def get_task_type(self, model_id: str) -> str:
        """
        获取任务类型
        """
        if model_id.endswith("-draw"):
            return "t2i"
        elif model_id.endswith("-video"):
            return "t2v"
        else:
            return "t2t"

    async def get_real_model(self, model: str) -> str:
        """
        获取实际的模型名称

        Args:
            model: 模型名称

        Returns:
            str: 实际的模型名称
        """
        # 获取基础模型（去除所有后缀）
        base_model = model
        for suffix in self.MODEL_FEATURES:
            if suffix:  # 跳过空字符串
                base_model = base_model.replace(suffix, "")

        # 验证基础模型是否存在
        models_data = await self.get_models()
        model_ids = [m["id"] for m in models_data.get("data", [])]

        if base_model not in model_ids:
            logger.warning(
                f"模型 {model} 不在支持列表中，降级到默认模型 qwen-max-latest"
            )
            return "qwen-max-latest"

        return base_model

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
                base_model = base_model.replace(suffix, "")

        # 验证基础模型是否存在
        models_data = await self.get_models()
        model_ids = [m["id"] for m in models_data.get("data", [])]

        if model not in model_ids:
            logger.warning(f"模型 {model} 不在支持列表中，降级到默认模型 qwen-turbo")
            return "qwen-turbo"

        return model
