"""
聊天API路由
"""
import uuid
import json
import time
from datetime import datetime
from typing import Dict, Any, List, Optional
from fastapi import APIRouter, Request, Depends, HTTPException
from fastapi.responses import StreamingResponse, Response
import traceback

from app.models.api import ChatRequest
from app.core.security import verify_auth
from app.core.config import config_manager
from app.services.account import account_manager
from app.services.request import request_service
from app.services.upload import upload_service
from app.services.image import image_service
from app.utils.json import is_json
from app.core.logger import logger

router = APIRouter()


@router.post("/completions")
async def chat_completions(
    request: ChatRequest,
    raw_request: Request,
    token: str = Depends(verify_auth)
):
    """
    处理聊天完成请求
    
    Args:
        request: 聊天请求模型
        raw_request: 原始FastAPI请求对象
        token: 认证令牌（支持API Key或Bearer Token）
        
    Returns:
        适当的响应类型（JSON或流）
    """
    # 获取通义千问账户令牌
    auth_token = account_manager.get_account_token()

    # 处理stream参数
    stream = request.stream if request.stream is not None else False

    # 记录请求信息
    thinking_enabled = "-thinking" in request.model or "qwq-32b" in request.model
    logger.info(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}]: 原始模型: {request.model} | 思考模式: {'启用' if thinking_enabled else '未启用'} | stream: {stream} | authToken: {auth_token[:len(auth_token)//2]}...")

    # 处理消息列表
    messages = [msg.dict() for msg in request.messages]
    
    # 处理文件消息
    file_url = None
    is_file_message = isinstance(messages[-1]['content'], list)

    if is_file_message:
        # 查找非文本类型的内容
        non_text_items = [item for item in messages[-1]['content'] if item.get('type') != 'text']
        
        if non_text_items and non_text_items[0].get('type') == 'image_url':
            # 使用新的 save_url 方法处理图像URL
            image_url = non_text_items[0].get('image_url', {}).get('url')
            if image_url:
                file_url = await upload_service.save_url(image_url, auth_token)
        
        if file_url:
            # 更新最后一条消息的图像URL，使用与JS版本一致的格式
            for i, item in enumerate(messages[-1]['content']):
                if item.get('type') == 'image_url':
                    messages[-1]['content'][i] = {
                        "type": "image",
                        "image": file_url
                    }

    # 处理非流式响应模板
    async def not_stream_response(response_data: Dict[str, Any]) -> Response:
        try:
            body_template = {
                "id": f"chatcmpl-{uuid.uuid4()}",
                "object": "chat.completion",
                "created": int(time.time() * 1000),
                "model": request.model,
                "choices": [
                    {
                        "index": 0,
                        "message": {
                            "role": "assistant",
                            "content": response_data['choices'][0]['message']['content']
                        },
                        "finish_reason": "stop"
                    }
                ],
                "usage": {
                    "prompt_tokens": len(json.dumps(messages)),
                    "completion_tokens": len(response_data['choices'][0]['message']['content']),
                    "total_tokens": len(json.dumps(messages)) + len(response_data['choices'][0]['message']['content'])
                }
            }
            return Response(
                content=json.dumps(body_template),
                media_type="application/json"
            )
        except Exception as e:
            logger.error(f"Error in not_stream_response: {e}")
            return Response(
                content=json.dumps({"error": "服务错误"}),
                status_code=500,
                media_type="application/json"
            )

    # 处理流式响应
    async def stream_response_generator(response_gen, thinking_enabled):
        """
        处理流式响应的生成器函数
        
        Args:
            response_gen: 响应生成器
            thinking_enabled: 是否启用思考模式
            
        Yields:
            bytes: 处理后的响应数据
        """
        try:
            id_value = str(uuid.uuid4())
            back_content = None
            web_search_info = None
            temp_content = ''
            think_end = False
            full_response = ''
            
            # 思考标签
            think_tag_start = "<think>"
            think_tag_end = "</think>"
            
            # 默认输出思考内容
            output_think = True
            
            async for line in response_gen:
                if not line:
                    continue
                
                logger.debug(f"收到原始数据行: {line!r}")  # 调试日志
                             
                if line.startswith("data: "):
                    try:
                        if line.startswith("data: [DONE]"):
                            yield b"data: [DONE]\n\n"
                            break
                        
                        data = json.loads(line[6:])
                        logger.debug(f"解析JSON数据: {data}")  # 调试日志
                        
                        if "choices" in data and data["choices"]:
                            choice = data["choices"][0]
                            logger.debug(f"处理选择数据: {choice}")  # 调试日志
                            
                            if "finish_reason" in choice and choice["finish_reason"] == "stop":
                                logger.debug("接收到结束标志")  # 调试日志
                                # 在结束前添加web搜索信息（如果存在且output_think为false）
                                if not output_think and web_search_info:
                                    search_info_mode = config_manager.get("chat.search_info_mode", "table")
                                    web_search_table = await account_manager.generate_markdown_table(web_search_info, search_info_mode)
                                    
                                    stream_template = {
                                        "id": f"chatcmpl-{id_value}",
                                        "object": "chat.completion.chunk",
                                        "created": int(time.time() * 1000),
                                        "choices": [
                                            {
                                                "index": 0,
                                                "delta": {
                                                    "content": f"\n\n\n{web_search_table}"
                                                }
                                            }
                                        ]
                                    }
                                    yield f"data: {json.dumps(stream_template)}\n\n".encode('utf-8', errors='replace')
                                
                                # 发送结束标记
                                yield b"data: [DONE]\n\n"
                                break
                                
                            if "delta" in choice and "content" in choice["delta"]:
                                content = choice["delta"]["content"]
                                logger.debug(f"接收到内容片段: {content}")  # 调试日志
                                
                                # 处理web搜索信息
                                if "name" in choice["delta"] and choice["delta"]["name"] == "web_search":
                                    web_search_info = choice["delta"]["extra"]["web_search_info"]
                                elif web_search_info and output_think:
                                    search_info_mode = config_manager.get("chat.search_info_mode", "table")
                                    if thinking_enabled and think_tag_start in content:
                                        markdown_table = await account_manager.generate_markdown_table(web_search_info, search_info_mode)
                                        content = content.replace(think_tag_start, f'{think_tag_start}\n\n\n{markdown_table}\n\n\n')
                                        web_search_info = None
                                    elif not thinking_enabled:
                                        markdown_table = await account_manager.generate_markdown_table(web_search_info, search_info_mode)
                                        content = f'{think_tag_start}\n{markdown_table}\n{think_tag_end}\n{content}'
                                        web_search_info = None
                                
                                # 构建流式响应模板
                                stream_template = {
                                    "id": f"chatcmpl-{id_value}",
                                    "object": "chat.completion.chunk",
                                    "created": int(time.time() * 1000),
                                    "choices": [
                                        {
                                            "index": 0,
                                            "delta": {
                                                "content": content
                                            },
                                            "finish_reason": None
                                        }
                                    ]
                                }
                                # 使用 errors='replace' 来处理无法编码的字符
                                yield f"data: {json.dumps(stream_template)}\n\n".encode('utf-8', errors='replace')
                                
                    except json.JSONDecodeError as e:
                        logger.error(f"JSON解析失败: {e}, 行内容: {line!r}")  # 调试日志
                        continue
                    
        except Exception as e:
            logger.error(f"Error in stream_response_generator: {e}")
            stream_error = {
                "error": "处理流式响应时出错",
                "details": str(e)
            }
            yield f"data: {json.dumps(stream_error)}\n\n".encode('utf-8', errors='replace')
            yield b"data: [DONE]\n\n"

    try:
        # 发送请求
        if '-draw' in request.model:
            # 绘图请求
            # 使用默认的图像尺寸
            size = config_manager.get('image.size', "1024x1024")
            
            response_data = await image_service.generate_image(
                auth_token=auth_token, 
                model=request.model, 
                size=size,
                messages=messages  # 直接传递完整的消息列表
            )
            
            # 检查请求是否成功
            if response_data.get('status') != 200:
                logger.error(f"请求失败: {response_data}")
                error_message = response_data.get('error', '未知错误')
                logger.error(f"Error in chat_completions: {error_message}")
                return Response(
                    content=json.dumps({
                        "error": {
                            "message": error_message,
                            "type": "image_generation_error"
                        }
                    }),
                    status_code=500,
                    media_type="application/json"
                )
            
            # 处理绘图流式响应
            if stream:
                response = StreamingResponse(
                    async_generator_draw_stream(response_data.get('url')),
                    media_type="text/event-stream",
                    headers={
                        "Cache-Control": "no-cache",
                        "Connection": "keep-alive",
                    }
                )
                return response
            else:
                # 处理绘图非流式响应
                return Response(
                    content=json.dumps({
                        "id": f"chatcmpl-{uuid.uuid4()}",
                        "object": "chat.completion",
                        "created": int(time.time() * 1000),
                        "model": request.model,
                        "choices": [
                            {
                                "index": 0,
                                "message": {
                                    "role": "assistant",
                                    "content": f"![{response_data.get('url')}]({response_data.get('url')})"
                                },
                                "finish_reason": "stop"
                            }
                        ],
                        "usage": {
                            "prompt_tokens": len(json.dumps(messages)),
                            "completion_tokens": len(response_data.get('url')),
                            "total_tokens": len(json.dumps(messages)) + len(response_data.get('url'))
                        }
                    }),
                    media_type="application/json"
                )
        elif '-video' in request.model:
            # 视频生成请求
            text_items = []
            content = messages[-1].get('content', '')
            
            # 处理不同的消息格式
            if isinstance(content, str):
                # 直接文本消息
                text_items = [content]
            elif isinstance(content, list):
                # 多模态消息
                text_items = [
                    item.get('text', '')
                    for item in content
                    if isinstance(item, dict) and item.get('type') == 'text'
                ]
            
            prompt = ' '.join(text_items)
            
            # 使用默认的视频尺寸
            size = config_manager.get('video.size', "1280x720")
            
            # 发送视频生成请求
            response_data = await request_service.video_generation(
                prompt=prompt,
                model=request.model,
                size=size,
                auth_token=auth_token
            )
            
            if response_data.get('status') != 200:
                error_message = response_data.get('error', '未知错误')
                logger.error(f"视频生成请求失败: {error_message}")
                return Response(
                    content=json.dumps({
                        "error": {
                            "message": error_message,
                            "type": "video_generation_error"
                        }
                    }),
                    status_code=500,
                    media_type="application/json"
                )
            
            # 等待视频生成完成
            result = await request_service.await_video(
                task_id=response_data['task_id'],
                auth_token=auth_token
            )
            
            if result.get('status') != 200:
                error_message = result.get('error', '未知错误')
                logger.error(f"视频生成失败: {error_message}")
                return Response(
                    content=json.dumps({
                        "error": {
                            "message": error_message,
                            "type": "video_generation_error"
                        }
                    }),
                    status_code=500,
                    media_type="application/json"
                )
            
            # 构建成功响应
            return Response(
                content=json.dumps({
                    "choices": [{
                        "message": {
                            "content": result['url'],
                            "role": "assistant"
                        }
                    }]
                }),
                media_type="application/json"
            )
        else:
            # 常规聊天请求
            response_data = await request_service.chat_completion(model=request.model, messages=messages, stream=stream, auth_token=auth_token)
            
            # 检查请求是否成功
            if response_data.get('status') != 200:
                error_info = response_data.get('response', {}).get('error', {})
                error_message = error_info.get('message', '未知错误')
                error_stack = error_info.get('stack_trace', '')
                logger.error(f"Error in chat_completions: {error_message}\n堆栈跟踪:\n{error_stack}")
                return Response(
                    content=json.dumps({
                        "error": {
                            "message": error_message,
                            "type": error_info.get('type', 'internal_server_error'),
                            "stack_trace": error_stack
                        }
                    }),
                    status_code=500,
                    media_type="application/json"
                )
            
            # 处理流式/非流式响应
            if stream:
                return StreamingResponse(
                    stream_response_generator(response_data.get('response'), response_data.get('thinking_enabled', False)),
                    media_type="text/event-stream",
                    headers={
                        "Cache-Control": "no-cache",
                        "Connection": "keep-alive",
                    }
                )
            else:
                return await not_stream_response(response_data.get('response'))
                
    except Exception as e:
        error_msg = f"Error in chat_completions:\n{str(e)}\n\nStack trace:\n{traceback.format_exc()}"
        logger.error(error_msg)
        return Response(
            content=json.dumps({"error": str(e), "stack_trace": traceback.format_exc()}),
            status_code=500,
            media_type="application/json"
        )


async def async_generator_draw_stream(image_url):
    """绘图流式响应生成器"""
    try:
        stream_template = {
            "id": f"chatcmpl-{uuid.uuid4()}",
            "object": "chat.completion.chunk",
            "created": int(time.time() * 1000),
            "choices": [
                {
                    "index": 0,
                    "delta": {
                        "content": f"![{image_url}]({image_url})"
                    },
                    "finish_reason": None
                }
            ]
        }
        
        yield f"data: {json.dumps(stream_template)}\n\n"
        yield "data: [DONE]\n\n"
    except Exception as e:
        logger.error(f"Error in async_generator_draw_stream: {e}")
        yield f"data: {json.dumps({'error': str(e)})}\n\n"
        yield "data: [DONE]\n\n" 