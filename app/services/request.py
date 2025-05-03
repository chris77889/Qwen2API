from typing import Dict, Any, Optional, List, Callable
from pathlib import Path
import uuid
import time
import json
import httpx
import asyncio
import traceback

from ..core.config import config_manager
from .account import account_manager
from ..core.logger import logger

class RequestService:
    """统一的请求服务"""

    def __init__(self):
        self.base_url = config_manager.get("api.url", "https://chat.qwen.ai")

    async def _request(
        self,
        method: str,
        endpoint: str,
        data: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, Any]] = None,
        files: Optional[Dict[str, Any]] = None,
        auth_token: Optional[str] = None,
        timeout: float = 30.0
    ) -> Any:
        url = f"{self.base_url}/{endpoint}"
        headers = account_manager.get_headers(auth_token)
        try:
            async with httpx.AsyncClient() as client:
                response = await client.request(
                    method=method,
                    url=url,
                    headers=headers,
                    params=params,
                    json=data,
                    files=files,
                    timeout=timeout
                )
                if response.status_code == 200:
                    return response.json()
                elif response.status_code == 401:
                    re_login = await account_manager.re_login(auth_token)
                    if re_login.get('success'):
                        return await self._request(
                            method=method,
                            endpoint=endpoint,
                            data=data,
                            params=params,
                            files=files,
                            auth_token=auth_token,
                            timeout=timeout
                        )
                    else:
                        raise Exception(f"认证失败: {re_login.get('message')}")
                else:
                    raise Exception(f"请求失败: {response.status_code} - {response.text}")
        except Exception as e:
            raise Exception(f"请求异常: {str(e)}")

    async def upload_file(
        self,
        file_path: str,
        auth_token: Optional[str] = None,
        timeout: float = 60.0
    ) -> Any:
        file_path = Path(file_path)
        if not file_path.exists():
            raise FileNotFoundError(f"文件不存在: {file_path}")
        files = {
            "file": (
                file_path.name,
                file_path.open("rb"),
                "application/octet-stream"
            )
        }
        return await self._request(
            method="POST",
            endpoint="files/upload",
            files=files,
            auth_token=auth_token,
            timeout=timeout
        )

    async def media_generation(
        self,
        media_type: str,  # "image" or "video"
        messages: List[Dict[str, Any]],
        model: Optional[str] = None,
        size: Optional[str] = None,
        auth_token: Optional[str] = None,
        timeout: float = 60.0
    ) -> Any:
        # 参数校验/修正
        if media_type == "image":
            size_map = ['1024*1024', '768*1024', '1024*768', '1280*720', '720*1280']
            size = size if size in size_map else "1024*1024"
            chat_type = "t2i"
            if model:
                model = model.replace('-draw', '').replace('-thinking', '').replace('-search', '').replace('-video', '')
            else:
                model = config_manager.CONSTANTS["QWEN_IMAGE_MODEL"]
        elif media_type == "video":
            size_map = config_manager.CONSTANTS.get("VIDEO_SIZES", ['1280x720'])
            size = size if size in size_map else "1280x720"
            chat_type = "t2v"
            if model:
                model = model.replace('-video', '').replace('-thinking', '').replace('-search', '').replace('-draw', '')
            else:
                model = config_manager.CONSTANTS["QWEN_VIDEO_MODEL"]
        else:
            raise Exception("媒体类型错误")

        processed_messages = []
        for message in messages:
            pmsg = self._preprocess_message(message, chat_type)
            processed_messages.append(pmsg)

        data = {
            "stream": False,
            "incremental_output": True,
            "chat_type": chat_type,
            "model": model,
            "messages": processed_messages,
            "session_id": str(uuid.uuid4()),
            "chat_id": str(uuid.uuid4()),
            "id": str(uuid.uuid4()),
            "size": size
        }
        logger.info(f"[{media_type}]生成请求参数：{json.dumps(data, ensure_ascii=False, indent=2)}")
        response = await self._request(
            method="POST",
            endpoint="chat/completions",
            data=data,
            auth_token=auth_token,
            timeout=timeout
        )

        if not response or "messages" not in response:
            return {"status": 500, "error": f"{media_type}生成响应缺少 messages 字段或为空"}

        assistant_messages = [
            msg for msg in response["messages"]
            if msg.get("role") == "assistant"
            and msg.get("extra")
            and isinstance(msg["extra"], dict)
            and msg["extra"].get("wanx")
            and isinstance(msg["extra"]["wanx"], dict)
            and msg["extra"]["wanx"].get("task_id")
        ]
        if not assistant_messages:
            return {"status": 500, "error": "未找到包含任务ID的助手消息"}
        task_id = assistant_messages[0]["extra"]["wanx"]["task_id"]
        return {"status": 200, "task_id": task_id}

    def _preprocess_message(self, message: Dict[str, Any], chat_type: str) -> Dict[str, Any]:
        # 【支持多模态/文本/图片/视频，不省略任何逻辑】
        if message.get('role') == 'assistant':
            content = message.get("content", "")
            processed = {
                "role": "assistant",
                "chat_type": chat_type
            }
            if isinstance(content, str) and content.startswith('![') and content.endswith(')'):
                url = content[content.find('(')+1:content.find(')')]
                if chat_type == "t2i":
                    processed["image"] = url
                else:
                    processed["content"] = url
            else:
                processed['content'] = content
            return processed
        else:
            processed = {
                "role": message.get('role', 'user'),
                "chat_type": chat_type,
                "extra": message.get('extra', {}),
                "feature_config": {"thinking_enabled": False}
            }
            content = message.get('content', '')
            if isinstance(content, list):
                processed_content = []
                for item in content:
                    if item.get("type") == "text":
                        processed_content.append({
                            "type": "text",
                            "text": item.get("text"),
                            "chat_type": chat_type,
                            "feature_config": {"thinking_enabled": False}
                        })
                    elif item.get("type") == "image_url":
                        image_data = item.get("image_url", {}).get("url", "")
                        processed_content.append({"type": "image", "image": image_data})
                    elif item.get("type") == "image":
                        image_data = item.get("image", "")
                        processed_content.append({"type": "image", "image": image_data})
                processed["content"] = processed_content
            else:
                processed["content"] = content
            return processed

    async def polling_task_status(
        self,
        task_id: str,
        auth_token: Optional[str] = None,
        timeout: float = 180.0,
        max_retries: int = 60,
        retry_interval: float = 5.0
    ) -> Dict[str, Any]:
        start_time = time.time()
        retry_count = 0
        while retry_count < max_retries:
            try:
                response = await self._request(
                    method="GET",
                    endpoint=f"v1/tasks/status/{task_id}",
                    auth_token=auth_token,
                    timeout=30.0
                )
                logger.info(f"第{retry_count+1}次检查状态, 响应: {json.dumps(response, ensure_ascii=False, indent=2)}")
                task_status = response.get('task_status', '')
                if task_status == 'failed':
                    error_message = response.get('message', '未知错误')
                    logger.error(f"媒体生成失败：{error_message}")
                    return {
                        "status": 500,
                        "error": error_message,
                        "task_status": "failed"
                    }
                if response.get('content'):
                    logger.info("媒体生成成功")
                    return {
                        "status": 200,
                        "url": response['content'],
                        "task_status": "success"
                    }
                if time.time() - start_time > timeout:
                    logger.error("等待超时")
                    return {
                        "status": 408, 
                        "error": "等待超时",
                        "task_status": "timeout"
                    }
                await asyncio.sleep(retry_interval)
                retry_count += 1
            except Exception as e:
                logger.error(f"查询任务进度报错: {str(e)}\n{traceback.format_exc()}")
                await asyncio.sleep(retry_interval)
                retry_count += 1
        return {
            "status": 408, 
            "error": "达到最大重试次数",
            "task_status": "max_retries_exceeded"
        }

    async def generate_and_wait_media(
        self,
        media_type: str,  # "image" or "video"
        messages: List[Dict[str, Any]],
        model: Optional[str] = None,
        size: Optional[str] = None,
        auth_token: Optional[str] = None,
        save: bool = True
    ) -> Dict[str, Any]:
        try:
            # 1. 创建媒体生成任务
            response = await self.media_generation(
                media_type=media_type,
                messages=messages,
                model=model,
                size=size,
                auth_token=auth_token
            )

            if response.get("status") != 200:
                error_msg = response.get("error", f"{media_type}生成请求失败")
                logger.error(f"{media_type}生成请求失败：{error_msg}")
                return {"status": 500, "error": error_msg}
            if not response.get("task_id"):
                error_msg = "未获取到任务ID"
                logger.error(error_msg)
                return {"status": 500, "error": error_msg}

            # 2. 轮询直到完成
            result = await self.polling_task_status(
                task_id=response['task_id'],
                auth_token=auth_token
            )
            if result.get("status") != 200:
                error_msg = result.get("error", f"{media_type}生成失败")
                logger.error(f"{media_type}生成失败：{error_msg}")
                return {"status": 500, "error": error_msg}

            if not result.get("url"):
                error_msg = f"未获取到生成的{media_type}URL"
                logger.error(error_msg)
                return {"status": 500, "error": error_msg}
            logger.info(f"{media_type}生成成功，URL：{result['url']}")
            return {
                "status": 200,
                "url": result["url"]
            }
        except Exception as e:
            error_stack = traceback.format_exc()
            error_msg = f"{media_type}生成失败: {str(e)}"
            logger.error(f"{error_msg}\n堆栈跟踪：\n{error_stack}")
            return {"status": 500, "error": error_msg}

# 创建唯一实例
request_service = RequestService()