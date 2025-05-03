import json
from typing import Dict, List, Any
from app.models.chat import ChatRequest
from app.service.completion_service import CompletionService
from app.service.model_service import ModelService
from fastapi.responses import StreamingResponse

class MessageService:
    def __init__(self, model_service: ModelService, completion_service: CompletionService):
        self.model_service = model_service
        self.completion_service = completion_service

    async def chat(
        self,
        client_payload: ChatRequest,
        auth_token: str
    ):
        model = client_payload.model
        messages = [msg.dict() for msg in client_payload.messages]
        temperature = client_payload.temperature if client_payload.temperature is not None else 1.0
        stream = client_payload.stream if client_payload.stream is not None else True

        model_config = self.model_service.get_model_config(model)
        chat_type = model_config["completion"].get("chat_type", "t2t")
        sub_chat_type = model_config["completion"].get("sub_chat_type", "t2t")
        chat_mode = model_config["completion"].get("chat_mode", "normal")
        feature_config = model_config["message"].get("feature_config", {})
        message_chat_type = model_config["message"].get("chat_type", "normal")
        task_type = await self.model_service.get_task_type(model)
        if task_type == 't2i' or task_type == 't2v':
            stream = False
        total_len = len(messages)
        qwen_messages = []
        for idx, m in enumerate(messages):
            m2 = dict(m)
            if m2["role"] == "user" and idx == total_len - 1:
                m2["chat_type"] = message_chat_type
                m2["extra"] = {}
                m2["feature_config"] = feature_config
            qwen_messages.append(m2)

        real_model = await self.model_service.get_real_model(model)


        if stream:
            # === 关键点：直接用 CompletionService 的 "流式" async 生成器 ===
            stream_gen = self.completion_service.stream_completion(
                messages=qwen_messages,
                auth_token=auth_token,
                model=real_model,
                stream=stream,
                chat_type=chat_type,
                sub_chat_type=sub_chat_type,
                chat_mode=chat_mode,
                temperature=temperature,
            )
            return StreamingResponse(stream_gen, media_type="text/event-stream")
        else:
            result = await self.completion_service.chat_completion(
                messages=qwen_messages,
                auth_token=auth_token,
                model=real_model,
                stream=stream,
                chat_type=chat_type,
                sub_chat_type=sub_chat_type,
                chat_mode=chat_mode,
                temperature=temperature,
            )
            return self._format_sync_response(result)

    def _format_sync_response(self, qwen_response: dict):
        if not qwen_response or "choices" not in qwen_response:
            return qwen_response
        choices = qwen_response["choices"]
        think_idx = [i for i, c in enumerate(choices)
                     if c.get("message", {}).get("phase") == "think"]
        if not think_idx:
            return qwen_response
        for i, idx in enumerate(think_idx):
            content = choices[idx]["message"]["content"]
            if i == 0:
                content = f"<think>{content}"
            if i == len(think_idx) - 1:
                content = f"{content}</think>"
            choices[idx]["message"]["content"] = content
            choices[idx]["modelextra"] = {"reasoning_content": choices[idx]["message"]["content"].replace("<think>","").replace("</think>","")}
        return qwen_response