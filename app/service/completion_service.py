import json
import uuid
import time
from typing import Dict, List, Any, AsyncGenerator, Optional
import httpx
import asyncio
from fastapi import HTTPException

from app.core.account_manager import AccountManager
from app.core.cookie_service import CookieService
from app.core.logger.logger import get_logger
from app.service.account_service import AccountService
account_service = AccountService()
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
        size: str = None,
        temperature: float = 1.0
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
            "chat_mode": chat_mode,
        }
        if size is not None:
            data["size"] = size
        if temperature is not None:
            data["temperature"] = temperature
        return data

    async def _post_with_retry(
        self,
        url: str,
        headers: Dict[str, str],
        json_data: Any,
        timeout: float,
        *,
        max_token_refresh: int = 1,
        max_429_retry: int = 5
    ) -> httpx.Response:
        """
        - 401 自动刷新token后重试1次
        - 429 指数退避重试5次
        """
        attempt = 0
        token_refresh_count = 0
        current_headers = dict(headers)
        last_exception = None
        while attempt < max_429_retry:
            try:
                async with httpx.AsyncClient() as client:
                    resp = await client.post(url, headers=current_headers, json=json_data, timeout=timeout)
                    # 401，token失效
                    if resp.status_code == 401 and token_refresh_count < max_token_refresh:
                        logger.warning("检测到401无效token，尝试刷新token...")
                        account = self.account_manager.get_account_by_token(headers['Authorization'].split(' ')[1])
                        new_token_dict = await account_service.login(account['username'], account['password'])
                        if not new_token_dict:
                            logger.error("刷新token失败，无法继续重试！")
                            raise Exception("无法刷新token")
                        # 刷新header，重试
                        current_headers = self.cookie_service.get_headers(new_token_dict['token'])
                        token_refresh_count += 1
                        continue
                    # 429，需要指数退避
                    if resp.status_code == 429 and attempt < max_429_retry - 1:
                        wait_time = 2 ** attempt
                        logger.warning(f"请求429限流，第{attempt+1}次重试，{wait_time}s后再试...")
                        await asyncio.sleep(wait_time)
                        attempt += 1
                        continue
                    # 其它错误直接抛出
                    if resp.status_code >= 400:
                        resp.raise_for_status()
                    # 成功
                    return resp
            except Exception as e:
                logger.error(f"请求出错: {e}")
                last_exception = e
                break
        if last_exception:
            raise last_exception

    async def stream_completion(
        self,
        messages: List[Dict[str, Any]],
        auth_token: str,
        model: str = "qwen3-235b-a22b",
        stream: bool = True,
        chat_type: str = "t2t",
        sub_chat_type: str = "t2t",
        chat_mode: str = "normal",
        size: str = None,
        temperature: float = 1.0,
        timeout: float = 60.0
    ) -> AsyncGenerator[bytes, None]:
        """
        流式接口，支持<think></think>及401/429自动重试
        """
        data = self._prepare_request_data(
            messages=messages,
            model=model,
            stream=stream,
            chat_type=chat_type,
            sub_chat_type=sub_chat_type,
            chat_mode=chat_mode,
            temperature=temperature,
            size=size
        )
        url = f"{self.base_url}/chat/completions"

        max_token_refresh = 1
        max_429_retry = 5
        attempt = 0
        token_refresh_count = 0
        token = auth_token

        while attempt < max_429_retry:
            current_headers = self.cookie_service.get_headers(token)
            try:
                async with httpx.AsyncClient() as client:
                    async with client.stream(
                        "POST", url,
                        json=data,
                        headers=current_headers,
                        timeout=timeout
                    ) as response:
                        # 401处理
                        if response.status_code == 401 and token_refresh_count < max_token_refresh:
                            logger.warning("stream检测到401无效token，尝试刷新后重试")
                            account = self.account_manager.get_account_by_token(auth_token)
                            new_token_dict = await account_service.login(account['username'], account['password'])
                            if not new_token_dict:
                                logger.error("stream刷新token失败，无法继续重试！")
                                yield b"data: [DONE]\n\n"
                                return
                            token = new_token_dict['token']
                            token_refresh_count += 1
                            continue
                        # 429退避重试
                        if response.status_code == 429 and attempt < max_429_retry - 1:
                            wait_time = 2 ** attempt
                            logger.warning(f"stream 429限流，{wait_time}s后重试")
                            await asyncio.sleep(wait_time)
                            attempt += 1
                            continue
                        if response.status_code >= 400:
                            text = await response.aread()
                            logger.error(f"stream 响应异常: {text}")
                            errtxt = text.decode("utf8", "ignore")
                            yield f"data: {json.dumps({'error': f'请求失败: {errtxt}'})}\n\n".encode()
                            yield b"data: [DONE]\n\n"
                            return

                        # ==== 正常流式处理 ↓
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
                                    for choice in data_json.get("choices", []):
                                        delta = choice.get("delta", {})
                                        seg = delta.get("content", "")
                                        phase = delta.get("phase")
                                        name = delta.get("name")
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
                                                    title = item.get('title', '').replace('|','\\|').replace('\n',' ')
                                                    snippet = item.get('snippet', '').replace('|','\\|').replace('\n',' ')
                                                    url_l = item.get('url', '')
                                                    table_rows += f"| {idx} | {title} | {snippet} | [链接]({url_l}) |\n"
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
                                            continue
                                        if phase == "think":
                                            if not in_think_phase:
                                                c = f"<think>{seg}"
                                                in_think_phase = True
                                            else:
                                                c = seg
                                        elif phase == "answer":
                                            if in_think_phase:
                                                c = f"</think>{seg}"
                                                in_think_phase = False
                                            else:
                                                c = seg
                                        else:
                                            c = seg
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
                        return  # 流式正常完成直接return
            except Exception as e:
                logger.error(f"stream 响应处理错误: {str(e)}")
                yield f"data: {json.dumps({'error': str(e)})}\n\n".encode()
                yield b"data: [DONE]\n\n"
                return
        # 如果到这里说明retries用完，无可用token
        yield f"data: {json.dumps({'error': '流式请求多次失败'})}\n\n".encode()
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
        size: str = None,
        temperature: float = 1.0,
        timeout: float = 60.0
    ) -> Any:
        """
        非流式调用（做同步请求等），支持401刷新token，429指数退避
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
            temperature=temperature,
            size=size
        )
        url = f"{self.base_url}/chat/completions"
        headers = self.cookie_service.get_headers(auth_token)
        try:
            resp = await self._post_with_retry(url, headers, data, timeout)
        except Exception as e:
            logger.error(f"请求失败: {e}")
            raise HTTPException(
                status_code=500,
                detail=f"请求失败: {e}"
            )
        if resp.status_code != 200:
            logger.error(f"请求失败: {resp.text}")
            logger.error(f"请求数据: {data}")
            raise HTTPException(
                status_code=resp.status_code,
                detail=f"请求失败: {resp.text}"
            )
        response_data = resp.json()
        formated_response = self._format_nonstream_response(
            response_data=response_data,
            model=model,
            messages=messages
        )
        return formated_response, response_data