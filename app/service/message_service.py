# app/service/message_service.py

import json
from typing import Dict, List, Any
from app.models.chat import ChatRequest
from app.service.completion_service import CompletionService
from app.service.model_service import ModelService
from app.service.task_service import TaskService
from app.core.cookie_service import CookieService
from fastapi.responses import StreamingResponse
from app.core.logger.logger import get_logger

# 新增导入
from app.service.upload_service import UploadService

logger = get_logger(__name__)


# -- 新增基础处理函数 --
async def process_user_images(msgs: list, auth_token: str, upload_service: UploadService):
    """
    将user消息中的base64类型图片上传OSS，替换成合法图片url
    """
    for msg in msgs:
        if msg.get("role") != "user":
            continue
        content = msg.get("content")
        if not isinstance(content, list):
            continue
        new_content = []
        for item in content:
            if item.get("type") == "image_url":
                image_url = item.get("image_url", {}).get("url", "")
                if image_url.startswith("data:image/"):  # base64 格式
                    try:
                        img_url = await upload_service.save_url(image_url, auth_token)
                        if img_url:
                            new_content.append({"type": "image", "image": img_url})
                            continue  # 跳过原item
                    except Exception as e:
                        logger.warning(f"Base64图片上传失败:{e}")
            new_content.append(item)
        msg["content"] = new_content


class MessageService:
    def __init__(
        self,
        model_service: ModelService,
        completion_service: CompletionService,
        cookie_service: CookieService,
        upload_service: UploadService,   # 新增
    ):
        self.model_service = model_service
        self.completion_service = completion_service
        self.cookie_service = cookie_service
        self.task_service = TaskService(cookie_service)
        self.upload_service = upload_service    # 新增

    async def chat(
        self,
        client_payload: ChatRequest,
        auth_token: str
    ):
        model = client_payload.model
        messages = [msg.dict() for msg in client_payload.messages]

        # ========== 新增处理：base64 image_url替换 ==========
        await process_user_images(messages, auth_token, self.upload_service)
        # ==================================================

        temperature = client_payload.temperature if client_payload.temperature is not None else 1.0
        stream = client_payload.stream if client_payload.stream is not None else True

        model_config = self.model_service.get_model_config(model)
        chat_type = model_config["completion"].get("chat_type", "t2t")
        sub_chat_type = model_config["completion"].get("sub_chat_type", "t2t")
        chat_mode = model_config["completion"].get("chat_mode", "normal")
        feature_config = model_config["message"].get("feature_config", {})
        message_chat_type = model_config["message"].get("chat_type", "normal")
        task_type = await self.model_service.get_task_type(model)
        size = model_config["completion"].get("size")
        # 对于t2i和t2v任务，强制使用非流式响应
        if task_type in ('t2i', 't2v'):
            stream = False

        # 处理所有消息，确保字段正确
        qwen_messages = []
        for m in messages:
            m2 = dict(m)
            # 设置正确的chat_type
            m2["chat_type"] = message_chat_type
            # 确保extra字段存在且不为null
            m2["extra"] = {} if m2.get("extra") is None else m2.get("extra", {})
            # 确保feature_config字段存在且不为null，对于t2i任务强制设置thinking_enabled为false
            if task_type == 't2i':
                m2["feature_config"] = {
                    "thinking_enabled": False,
                    "output_schema": "phase"
                }
            else:
                # 修复：当feature_config为None时使用默认值
                m2["feature_config"] = feature_config if m2.get("feature_config") is None else m2.get("feature_config")
                logger.info(f"m2: {m2}")
            qwen_messages.append(m2)

        real_model = await self.model_service.get_real_model(model)
        #logger.info(f"qwen_messages: {qwen_messages}")
        if stream:
            stream_gen = self.completion_service.stream_completion(
                messages=qwen_messages,
                auth_token=auth_token,
                model=real_model,
                stream=stream,
                chat_type=chat_type,
                sub_chat_type=sub_chat_type,
                chat_mode=chat_mode,
                temperature=temperature,
                size=size
            )
            return StreamingResponse(stream_gen, media_type="text/event-stream")
        else:
            #logger.info(f"非流式请求")
            result, response_data = await self.completion_service.chat_completion(
                messages=qwen_messages,
                auth_token=auth_token,
                model=real_model,
                stream=stream,
                chat_type=chat_type,
                sub_chat_type=sub_chat_type,
                chat_mode=chat_mode,
                temperature=temperature,
                size=size
            )
            #print(f"result: {result}")
            #print(f"response_data: {response_data}")

            # 处理任务型响应（t2i和t2v）
            task_result = None
            if task_type in ('t2i', 't2v'):
                task_id = self._extract_task_id(response_data)
                if not task_id:
                    return {
                        "chat_type": task_type,
                        "task_status": "failed",
                        "message": "未能获取任务ID",
                        "remaining_time": "",
                        "content": ""
                    }

                # 根据任务类型选择合适的轮询方法
                if task_type == 't2i':
                    task_result = await self.task_service.poll_image_task(
                        task_id=task_id,
                        auth_token=auth_token
                    )
                else:  # t2v
                    task_result = await self.task_service.poll_video_task(
                        task_id=task_id,
                        auth_token=auth_token
                    )
                logger.info(f"task_result: {task_result}")
                # 对于图片和视频任务，task_result 已经是格式化好的 OpenAI 格式响应
                return self._format_sync_response(task_result)
            else:
                # 对于普通文本对话，使用 format_sync_response 处理思考模式
                return self._format_sync_response(result)

    def _extract_task_id(self, response: Dict[str, Any]) -> str:
        """
        从响应中提取任务ID

        Args:
            response: 完整的响应数据

        Returns:
            str: 任务ID，如果未找到则返回空字符串
        """
        try:
            messages = response.get("messages", [])
            if not messages:
                return ""

            # 获取最后一条消息
            last_message = messages[-1]
            task_id = last_message.get("extra", {}).get("wanx", {}).get("task_id")
            if task_id:
                return task_id
        except Exception:
            pass
        return ""

    def _format_sync_response(self, qwen_response: dict):
        if not qwen_response or "choices" not in qwen_response:
            #logger.info(f"qwen_response: {qwen_response}")
            return qwen_response
        choices = qwen_response["choices"]
        think_idx = [i for i, c in enumerate(choices)
                     if c.get("message", {}).get("phase") == "think"]
        if not think_idx:
            #logger.info(f"qwen_response: {qwen_response}")
            return qwen_response
        for i, idx in enumerate(think_idx):
            content = choices[idx]["message"]["content"]
            if i == 0:
                content = f"<think>{content}"
            if i == len(think_idx) - 1:
                content = f"{content}</think>"
            choices[idx]["message"]["content"] = content
            choices[idx]["delta"]["reasoning_content"] = choices[idx]["message"]["content"].replace("<think>", "").replace("</think>", "")
        #logger.info(f"qwen_response: {qwen_response}")
        return qwen_response