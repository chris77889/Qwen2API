import json
import uuid
import time
from typing import Dict, List, Optional, Any, AsyncGenerator
import httpx
from fastapi import HTTPException

from app.core.account_manager import AccountManager
from app.core.cookie_service import CookieService
from app.core.logger.logger import get_logger

logger = get_logger(__name__)

class CompletionService:
    def __init__(self):
        self.account_manager = AccountManager()
        self.cookie_service = CookieService(self.account_manager)
        self.base_url = "https://chat.qwen.ai/api"

    def _prepare_request_data(
        self,
        messages: List[Dict[str, Any]],
        model: str,
        stream: bool = True,
        chat_type: str = "t2t",
        sub_chat_type: str = "t2t",
        chat_mode: str = "normal",
        temperature: Optional[float] = None
    ) -> Dict[str, Any]:
        data = {
            "stream": stream,
            "incremental_output": True,
            "chat_type": chat_type,
            "model": model,
            "messages": messages,
            "session_id": str(uuid.uuid4()),
            "chat_id": str(uuid.uuid4()),
            "id": str(uuid.uuid4()),
            "sub_chat_type": sub_chat_type,
            "chat_mode": chat_mode
        }
        if temperature is not None:
            data["temperature"] = temperature
        return data

    async def stream_completion(
        self,
        messages: List[Dict[str, Any]],
        auth_token: str,
        model: str = "qwen3-235b-a22b",
        stream: bool = True,
        chat_type: str = "t2t",
        sub_chat_type: str = "t2t",
        chat_mode: str = "normal",
        temperature: float = 1.0,
        timeout: float = 60.0
    ) -> AsyncGenerator[bytes, None]:
        """
        流式接口，处理 phase 并标明 <think> ... </think>
        """
        data = self._prepare_request_data(
            messages=messages,
            model=model,
            stream=stream,
            chat_type=chat_type,
            sub_chat_type=sub_chat_type,
            chat_mode=chat_mode,
            temperature=temperature
        )
        headers = self.cookie_service.get_headers(auth_token)
        url = f"{self.base_url}/chat/completions"

        try:
            async with httpx.AsyncClient() as client:
                async with client.stream(
                    "POST", url,
                    json=data,
                    headers=headers,
                    timeout=timeout
                ) as response:
                    if response.status_code != 200:
                        text = await response.aread()
                        logger.error(f"请求失败: {text}")
                        logger.error(f"请求数据: {data}")
                        yield f"data: {json.dumps({'error': f'请求失败: {text}'})}\n\n".encode()
                        yield b"data: [DONE]\n\n"
                        return
                    in_think_phase = False
                    async for line in response.aiter_lines():
                        if not line.strip():
                            continue
                        if line.startswith("data: "):
                            payload = line[6:].strip()
                            if payload == "[DONE]":
                                yield b"data: [DONE]\n\n"
                                return
                            try:
                                data_json = json.loads(payload)
                                logger.info(f"流式响应: {data_json}")
                                for choice in data_json.get("choices", []):
                                    delta = choice.get("delta", {})
                                    seg = delta.get("content", "")
                                    phase = delta.get("phase")
                                    name = delta.get("name")
                                    # 处理 phase
                                    # 优先处理 web_search 函数表格
                                    if name == 'web_search':
                                        web_search_info = None
                                        if 'extra' in delta and 'web_search_info' in delta['extra']:
                                            web_search_info = delta['extra']['web_search_info']
                                        if web_search_info:
                                            max_row = 5
                                            table_header = "| 序号 | 标题 | 摘要 | 链接 |\n|---|---|---|---|\n"
                                            table_rows = ""
                                            table_footer = "\n\n"
                                            for idx, item in enumerate(web_search_info, 1):
                                                #if idx > max_row:
                                                    #table_rows += "| ... | ... | ... | ... |\n"
                                                    #break
                                                title = item.get('title', '').replace('|','\\|').replace('\n',' ')
                                                snippet = item.get('snippet', '').replace('|','\\|').replace('\n',' ')
                                                url = item.get('url', '')
                                                table_rows += f"| {idx} | {title} | {snippet} | [链接]({url}) |\n"
                                            c = table_header + table_rows + table_footer
                                        else:
                                            c = ""
                                        chunk = {
                                            "choices": [{
                                                "index": 0,
                                                "delta": {
                                                    "role": delta.get("role", "function"),
                                                    "content": c,
                                                    "phase": phase,
                                                    "name": name,
                                                    "render_type": "table"
                                                },
                                                "finish_reason": None
                                            }]
                                        }
                                        yield f"data: {json.dumps(chunk, ensure_ascii=False)}\n\n".encode("utf-8")
                                        continue  # 只要是web_search立即continue, 不落入下面的think/answer逻辑
                                    if phase == "think":
                                        if not in_think_phase:
                                            c = f"<think>{seg}"
                                            in_think_phase = True
                                        else:
                                            # 只要还在think阶段，直接输出内容
                                            c = seg
                                    elif phase == "answer":
                                        if in_think_phase:
                                            c = f"</think>{seg}"
                                            in_think_phase = False
                                        else:
                                            c = seg
                                    else:
                                        c = seg
                                    # 打包数据
                                    chunk = {
                                        "choices": [{
                                            "index": 0,
                                            "delta": {
                                                "role": delta.get("role", "assistant"),
                                                "content": c,
                                                "reasoning_content": seg if in_think_phase else None,
                                                "phase": phase
                                            },
                                            "finish_reason": None
                                        }]
                                    }
                                    yield f"data: {json.dumps(chunk, ensure_ascii=False)}\n\n".encode("utf-8")
                            except Exception as e:
                                logger.error(f"流式响应解析错误: {str(e)} | {payload}")
                                yield f"data: {json.dumps({'error': str(e)})}\n\n".encode()
                    yield b"data: [DONE]\n\n"
        except httpx.TimeoutException:
            yield b"data: [DONE]\n\n"
        except Exception as e:
            logger.error(f"流式响应处理错误: {str(e)}")
            yield f"data: {json.dumps({'error': str(e)})}\n\n".encode()
            yield b"data: [DONE]\n\n"

    def _format_nonstream_response(
        self,
        response_data: Dict[str, Any],
        model: str,
        messages: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        return {
            "id": f"chatcmpl-{uuid.uuid4()}",
            "object": "chat.completion",
            "created": int(time.time() * 1000),
            "model": model,
            "choices": [
                {
                    "index": 0,
                    "message": {
                        "role": "assistant",
                        "content": response_data['choices'][0]['message']['content'] if response_data and response_data.get('choices') else ''
                    },
                    "finish_reason": "stop"
                }
            ],
            "usage": {
                "prompt_tokens": len(json.dumps(messages)),
                "completion_tokens": len(response_data['choices'][0]['message']['content']) if response_data and response_data.get('choices') else 0,
                "total_tokens": len(json.dumps(messages)) + (len(response_data['choices'][0]['message']['content']) if response_data and response_data.get('choices') else 0)
            }
        }

    async def chat_completion(
        self,
        messages: List[Dict[str, Any]],
        auth_token: str,
        model: str = "qwen3-235b-a22b",
        stream: bool = True,
        chat_type: str = "t2t",
        sub_chat_type: str = "t2t",
        chat_mode: str = "normal",
        temperature: float = 1.0,
        timeout: float = 60.0
    ) -> Any:
        """
        非流式调用（做同步请求等）
        """
        if not messages:
            raise HTTPException(status_code=400, detail="消息列表不能为空")
        data = self._prepare_request_data(
            messages=messages,
            model=model,
            stream=stream,
            chat_type=chat_type,
            sub_chat_type=sub_chat_type,
            chat_mode=chat_mode,
            temperature=temperature
        )
        headers = self.cookie_service.get_headers(auth_token)
        url = f"{self.base_url}/chat/completions"
        async with httpx.AsyncClient() as client:
            resp = await client.post(url, headers=headers, json=data, timeout=timeout)
            if resp.status_code != 200:
                logger.error(f"请求失败: {resp.text}")
                logger.error(f"请求数据: {data}")
                raise HTTPException(
                    status_code=resp.status_code,
                    detail=f"请求失败: {resp.text}"
                )
            response_data = resp.json()
            return self._format_nonstream_response(
                response_data=response_data,
                model=model,
                messages=messages
            )