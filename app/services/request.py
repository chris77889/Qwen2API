"""
请求服务
"""
from typing import Dict, Any, Optional, AsyncGenerator, List, Union
import json
import uuid
import httpx
import traceback
from pathlib import Path
import asyncio
from fastapi import HTTPException
import base64
import re
from urllib.parse import urlparse
from io import BytesIO
import time

from ..core.config import config_manager
from .account import account_manager
from .model import model_service
from ..core.logger import logger

class RequestService:
    """请求服务"""
    
    def __init__(self):
        """初始化请求服务"""
        self.base_url = config_manager.CONSTANTS["QWEN_API_URL"]
        
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
        """
        发送HTTP请求 (非流式)
        
        Args:
            method: 请求方法
            endpoint: 请求端点
            data: 请求数据
            params: 查询参数
            files: 文件数据
            auth_token: 认证令牌
            timeout: 超时时间
            
        Returns:
            Any: 响应数据
            
        Raises:
            Exception: 请求失败
        """
        url = f"{self.base_url}/{endpoint}"
        headers = account_manager.get_headers(auth_token)
        
        try:
            async with httpx.AsyncClient() as client:
                # 对于非流式响应，使用普通的request方法
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
                        raise HTTPException(
                            status_code=401,
                            detail=re_login.get('message')
                        )
                else:
                    error_msg = f"请求失败: {response.status_code} - {response.text}"
                    raise Exception(error_msg)
                    
        except Exception as e:
            error_msg = f"请求异常: {str(e)}"
            raise Exception(error_msg)
    count = 0
    async def _request_stream(
        self,
        method: str,
        endpoint: str,
        data: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, Any]] = None,
        files: Optional[Dict[str, Any]] = None,
        auth_token: Optional[str] = None,
        timeout: float = 30.0
    ):
        """
        发送流式请求
        
        Args:
            method: 请求方法
            endpoint: 请求端点
            data: 请求数据
            params: 请求参数
            files: 文件数据
            auth_token: 认证令牌
            timeout: 超时时间
            
        Returns:
            AsyncGenerator: 响应生成器
        """
        try:
            url = f"{self.base_url}/{endpoint}"
            
            # 构建请求头
            headers = account_manager.get_headers(auth_token)
            
            # 验证token
            if not auth_token:
                raise HTTPException(
                    status_code=401,
                    detail="认证token无效或未提供"
                )
            
            # 记录请求信息
            logger.info(f"发送请求到: {url}")
            if data:
                # 记录原始模型信息
                original_model = data.get("model", "未知模型")
                # 记录是否启用思考模式
                thinking_enabled = "-thinking" in original_model or "qwq-32b" in original_model
                logger.info(f"原始模型: {original_model}")
                logger.info(f"思考模式: {'启用' if thinking_enabled else '未启用'}")
                logger.info(f"请求体: {json.dumps(data, ensure_ascii=False, indent=2)}")
            
            async with httpx.AsyncClient() as client:
                async with client.stream(
                    method=method,
                    url=url,
                    json=data,
                    params=params,
                    files=files,
                    headers=headers,
                    timeout=timeout
                ) as response:
                    # 检查响应状态
                    
                    if response.status_code == 401:
                        # 如果状态码为401，尝试重新登录
                        re_login = await account_manager.re_login(auth_token)
                        if re_login.get('success'):
                            # 获取新的token
                            new_token = re_login.get('account', {}).get('token')
                            if new_token:
                                # 使用新token重新发起请求
                                async for chunk in self._request_stream(
                                    method=method,
                                    endpoint=endpoint, 
                                    data=data,
                                    params=params,
                                    files=files,
                                    auth_token=new_token,
                                    timeout=timeout
                                ):
                                    yield chunk
                                return
                        # 重新登录失败,抛出异常
                        raise HTTPException(
                            status_code=401,
                            detail=re_login.get('message', '重新登录失败')
                        )
                       
                    elif response.status_code != 200:
                        error_text = await response.aread()
                        error_text = error_text.decode('utf-8', errors='replace')
                        logger.error(f"请求失败: {response.status_code} - {error_text}")
                        raise HTTPException(
                            status_code=response.status_code,
                            detail=f"请求失败: {error_text}"
                        )
                    
                    # 处理流式响应
                    temp_content = ""
                    full_response = ""
                    is_finished = False
                    
                    async for line in response.aiter_lines():
                        line = line.strip()

                        if not line:
                            continue
                            
                        if not line.startswith("data: "):
                            temp_content += line
                            continue
                            
                        if temp_content:
                            line = temp_content + line
                            temp_content = ""
                            
                        try:
                                
                            data = json.loads(line[6:])  # 去除 "data: " 前缀
                            logger.debug(f"接收到数据: {data}")
                            
                            if "choices" in data and data["choices"]:
                                choice = data["choices"][0]
                                logger.debug(f"处理选择数据: {choice}")
                                
                                if "finish_reason" in choice and choice["finish_reason"] == "stop":
                                    logger.debug("接收到 finish_reason=stop")
                                    is_finished = True
                                    yield line
                                    break
                                    
                                if "delta" in choice:
                                    if "content" in choice["delta"]:
                                        content = choice["delta"]["content"]
                                        logger.debug(f"接收到内容片段: {content}")
                                        full_response += content
                                        yield line
                                    elif "name" in choice["delta"]:
                                        yield line
                                        
                        except json.JSONDecodeError as e:
                            logger.error(f"JSON解析失败: {e}, 行内容: {line!r}")
                            temp_content = ""
                            continue
                        except Exception as e:
                            logger.error(f"处理响应数据时出错: {str(e)}")
                            raise
                            
                    if not is_finished:
                        # 麻烦死了懒得判断结不结束了🙄💅
                        yield "data: [DONE]\n\n"
                    
        except httpx.TimeoutException as e:
            logger.error(f"请求超时: {str(e)}")
            raise HTTPException(
                status_code=504,
                detail=f"请求超时: {str(e)}"
            )
        except httpx.RequestError as e:
            logger.error(f"请求错误: {str(e)}")
            raise HTTPException(
                status_code=500,
                detail=f"请求错误: {str(e)}"
            )
        except Exception as e:
            logger.error(f"发送请求时出错: {str(e)}")
            # 确保在抛出异常前返回结束标记
            yield "data: {\"error\": \"" + str(e) + "\"}\n\n"
            yield "data: [DONE]\n\n"
            raise HTTPException(
                status_code=500,
                detail=f"发送请求时出错: {str(e)}"
            )
    
    async def chat_completion(
        self,
        messages: List[Dict[str, Any]],
        model: Optional[str] = None,
        stream: bool = True,
        auth_token: Optional[str] = None,
        timeout: float = 60.0,
        temperature: Optional[float] = 1.0
    ) -> Any:
        """
        聊天补全
        
        Args:
            messages: 消息列表
            model: 模型名称
            stream: 是否流式输出
            auth_token: 认证令牌
            timeout: 超时时间
            temperature: 采样温度，控制输出的随机性，取值范围0-2，默认1.0
            
        Returns:
            Any: 响应数据
        """
        try:
            # 验证消息列表
            if not messages:
                raise ValueError("消息列表不能为空")
            
            # 处理消息列表
            processed_messages = []
            last_valid_message = None
            session_id = None
            chat_id = None
            thinking_enabled = False
            
            # 判断是否开启推理
            if model and ('-thinking' in model or 'qwq-32b' in model):
                thinking_enabled = True

            for i, message in enumerate(messages):
                if message is None:
                    logger.warning(f"跳过空消息，索引: {i}")
                    continue
                    
                # 确保消息是字典类型
                if isinstance(message, str):
                    processed_message = {
                        "role": "user",
                        "content": message,
                        "chat_type": "t2t",
                        "extra": {},
                        "feature_config": {
                            "thinking_enabled": thinking_enabled
                        }
                    }
                elif isinstance(message, dict):
                    # 创建基本消息结构
                    processed_message = {
                        "role": message.get('role', 'user'),
                        "chat_type": "t2t",
                        "extra": {},
                        "feature_config": {
                            "thinking_enabled": thinking_enabled
                        }
                    }
                    
                    # 处理角色转换
                    if processed_message['role'] == 'developer':
                        processed_message['role'] = 'system'
                        
                    # 处理消息内容
                    content = message.get('content', '')
                    if isinstance(content, list):
                        # 处理多模态消息
                        processed_content = []
                        for item in content:
                            if item.get('type') == 'text':
                                processed_content.append({
                                    "type": "text",
                                    "text": item.get('text'),
                                    "chat_type": "t2t",
                                    "feature_config": {
                                        "thinking_enabled": thinking_enabled
                                    }
                                })
                            elif item.get('type') == 'image_url':
                                # 获取图片数据
                                image_data = item.get('image_url', {}).get('url', '')
                                if image_data:
                                    # 使用upload服务处理图片上传
                                    from .upload import upload_service
                                    uploaded_url = await upload_service.save_url(image_data, auth_token)
                                    if uploaded_url:
                                        processed_content.append({
                                            "type": "image",
                                            "image": uploaded_url
                                        })
                            elif item.get('type') == 'image':
                                # 直接处理base64数据
                                image_data = item.get('image', '')
                                if image_data:
                                    # 使用upload服务处理图片上传
                                    from .upload import upload_service
                                    uploaded_url = await upload_service.save_url(image_data, auth_token)
                                    if uploaded_url:
                                        processed_content.append({
                                            "type": "image",
                                            "image": uploaded_url
                                        })

                        processed_message['content'] = processed_content
                    else:
                        processed_message['content'] = content

                # 检查消息内容是否包含think标签
                if processed_message['role'] == 'assistant':
                    if isinstance(content, str) and '<think>' in content and '</think>' in content:
                        thinking_enabled = True
                
                # 如果原消息有chat_type，使用原消息的chat_type
                if message.get('chat_type'):
                    processed_message['chat_type'] = message['chat_type']
                    
                # 如果原消息有extra，使用原消息的extra
                if message.get('extra'):
                    processed_message['extra'] = message['extra']

                processed_messages.append(processed_message)
                if processed_message['role'] != 'assistant':
                    last_valid_message = processed_message
            
            # 再次验证处理后的消息列表
            if not processed_messages:
                raise ValueError("处理后的消息列表为空")

            # 处理模型名称和特性
            chat_model = model or config_manager.get('chat.model', config_manager.CONSTANTS["QWEN_DEFAULT_MODEL"])
            chat_type = "t2t"
            
            # 移除模型后缀
            if '-thinking' in chat_model:
                chat_model = chat_model.replace('-thinking', '')
                
            # 判断是否开启搜索 - 后处理 search
            if '-search' in chat_model:
                if last_valid_message is not None:
                    last_valid_message['chat_type'] = 'search'
                chat_model = chat_model.replace('-search', '')
                chat_type = 'search'

            # 验证模型是否支持所请求的特性
            chat_model = await model_service.verify_model_with_feature(chat_model)

            # 获取session_id和chat_id（如果存在）
            if isinstance(messages, list) and len(messages) > 0:
                last_message = messages[-1]
                if isinstance(last_message, dict):
                    session_id = last_message.get('session_id')
                    chat_id = last_message.get('chat_id')

            # 构建请求体
            data = {
                "model": chat_model,
                "messages": processed_messages,
                "stream": stream,
                "chat_type": chat_type,
                "incremental_output": True,
                "id": str(uuid.uuid4())
            }
            
            # 添加temperature参数（如果提供）
            if temperature is not None:
                data["temperature"] = temperature
            
            # 添加session_id和chat_id（如果存在）
            if session_id:
                data["session_id"] = session_id
            if chat_id:
                data["chat_id"] = chat_id

            # 发送请求
            if stream:
                return {
                    "status": 200,
                    "response": self._request_stream(
                        method="POST",
                        endpoint="chat/completions",
                        data=data,
                        auth_token=auth_token,
                        timeout=timeout
                    ),
                    "thinking_enabled": thinking_enabled
                }
            else:
                response = await self._request(
                    method="POST",
                    endpoint="chat/completions",
                    data=data,
                    auth_token=auth_token,
                    timeout=timeout
                )
                return {
                    "status": 200,
                    "response": response
                }
        except Exception as e:
            error_stack = traceback.format_exc()
            logger.error(f"请求失败: {str(e)}\n堆栈跟踪:\n{error_stack}")
            return {
                "status": 500,
                "response": {
                    "error": {
                        "message": str(e),
                        "type": "internal_server_error",
                        "stack_trace": error_stack
                    }
                }
            }
    
    async def image_generation(
        self,
        messages: List[Dict[str, Any]],
        model: Optional[str] = None,
        size: Optional[str] = None,
        auth_token: Optional[str] = None,
        timeout: float = 60.0
    ) -> Any:
        """
        图像生成
        
        Args:
            messages: 消息列表
            model: 模型名称
            size: 尺寸
            auth_token: 认证令牌
            timeout: 超时时间
            
        Returns:
            Any: 响应数据
        """
        try:
            # 验证并处理尺寸参数
            size_map = [
                '1024*1024',
                '768*1024',
                '1024*768',
                '1280*720',
                '720*1280'
            ]
            if not size or size not in size_map:
                size = '1024*1024'
                
            # 处理模型名称
            if model:
                model = model.replace('-draw', '').replace('-thinking', '').replace('-search', '').replace('-video', '')
            else:
                model = config_manager.CONSTANTS["QWEN_IMAGE_MODEL"]

            # 处理消息列表
            processed_messages = []
            for message in messages:
                # 如果是助手消息，只保留必要字段
                if message.get('role') == 'assistant':
                    processed_message = {
                        "role": "assistant",
                        "chat_type": "t2i"
                    }
                    
                    # 处理消息内容
                    content = message.get('content', '')
                    if isinstance(content, str) and content.startswith('![') and content.endswith(')'):
                        # 提取URL
                        url = content[content.find('(')+1:content.find(')')]
                        processed_message['image'] = url
                    else:
                        processed_message['content'] = content
                else:
                    # 非助手消息保持原有格式
                    processed_message = {
                        "role": message.get('role', 'user'),
                        "chat_type": "t2i",
                        "extra": message.get('extra', {}),
                        "feature_config": {
                            "thinking_enabled": False
                        }
                    }
                    
                    # 处理消息内容
                    content = message.get('content', '')
                    if isinstance(content, list):
                        # 处理多模态消息
                        processed_content = []
                        for item in content:
                            if item.get('type') == 'text':
                                processed_content.append({
                                    "type": "text",
                                    "text": item.get('text'),
                                    "chat_type": "t2i",
                                    "feature_config": {
                                        "thinking_enabled": False
                                    }
                                })
                            elif item.get('type') == 'image_url':
                                # 获取图片数据
                                image_data = item.get('image_url', {}).get('url', '')
                                if image_data:
                                    # 使用upload服务处理图片上传
                                    from .upload import upload_service
                                    uploaded_url = await upload_service.save_url(image_data, auth_token)
                                    if uploaded_url:
                                        processed_content.append({
                                            "type": "image",
                                            "image": uploaded_url
                                        })
                            elif item.get('type') == 'image':
                                # 直接处理base64数据
                                image_data = item.get('image', '')
                                if image_data:
                                    # 使用upload服务处理图片上传
                                    from .upload import upload_service
                                    uploaded_url = await upload_service.save_url(image_data, auth_token)
                                    if uploaded_url:
                                        processed_content.append({
                                            "type": "image",
                                            "image": uploaded_url
                                        })
                        processed_message['content'] = processed_content
                    else:
                        processed_message['content'] = content

                processed_messages.append(processed_message)
            
            # 构建请求数据
            data = {
                "stream": False,
                "incremental_output": True,
                "chat_type": "t2i",
                "model": model,
                "messages": processed_messages,
                "session_id": str(uuid.uuid4()),
                "chat_id": str(uuid.uuid4()),
                "id": str(uuid.uuid4()),
                "size": size
            }
            
            logger.info(f"发送图像生成请求，参数：{json.dumps(data, ensure_ascii=False, indent=2)}")
            
            response = await self._request(
                method="POST",
                endpoint="chat/completions",
                data=data,
                auth_token=auth_token,
                timeout=timeout
            )
            
            if not response:
                logger.error("图像生成请求返回空响应")
                return {
                    "status": 500,
                    "error": "图像生成请求返回空响应"
                }
                
            if 'messages' not in response:
                logger.error(f"响应中缺少 messages 字段：{json.dumps(response, ensure_ascii=False, indent=2)}")
                return {
                    "status": 500,
                    "error": "响应格式错误：缺少 messages 字段"
                }
            
            # 提取任务ID
            try:
                # 查找包含任务ID的助手消息
                assistant_messages = [
                    msg for msg in response['messages'] 
                    if msg.get('role') == 'assistant' 
                    and msg.get('extra') 
                    and isinstance(msg['extra'], dict)
                    and msg['extra'].get('wanx')
                    and isinstance(msg['extra']['wanx'], dict)
                    and msg['extra']['wanx'].get('task_id')
                ]
                
                if not assistant_messages:
                    logger.error(f"未找到包含任务ID的助手消息，响应内容：{json.dumps(response, ensure_ascii=False, indent=2)}")
                    return {
                        "status": 500,
                        "error": "未找到包含任务ID的助手消息"
                    }
                    
                task_id = assistant_messages[0]['extra']['wanx']['task_id']
                logger.info(f"成功获取任务ID：{task_id}")
                return {
                    "status": 200,
                    "task_id": task_id
                }
            except Exception as e:
                logger.error(f"提取任务ID失败：{str(e)}")
                logger.error(f"响应内容：{json.dumps(response, ensure_ascii=False, indent=2)}")
                return {
                    "status": 500,
                    "error": f"提取任务ID失败：{str(e)}"
                }
                
        except Exception as e:
            error_stack = traceback.format_exc()
            logger.error(f"图像生成请求异常：{str(e)}\n堆栈跟踪：\n{error_stack}")
            return {
                "status": 500,
                "error": f"图像生成请求异常：{str(e)}"
            }
    
    async def upload_file(
        self,
        file_path: str,
        auth_token: Optional[str] = None,
        timeout: float = 60.0
    ) -> Any:
        """
        上传文件
        
        Args:
            file_path: 文件路径
            auth_token: 认证令牌
            timeout: 超时时间
            
        Returns:
            Any: 响应数据
        """
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
        
        response = await self._request(
            method="POST",
            endpoint="files/upload",
            files=files,
            auth_token=auth_token,
            timeout=timeout
        )
        return response

    async def await_image(
        self,
        task_id: str,
        auth_token: Optional[str] = None,
        timeout: float = 60.0,
        max_retries: int = 30,
        retry_interval: float = 6.0
    ) -> Dict[str, Any]:
        """
        等待图像生成完成
        
        Args:
            task_id: 任务ID
            auth_token: 认证令牌
            timeout: 超时时间
            max_retries: 最大重试次数
            retry_interval: 重试间隔(秒)
            
        Returns:
            Dict[str, Any]: 生成结果
        """
        start_time = time.time()
        retry_count = 0
        
        logger.info(f"开始等待图片生成完成，任务ID：{task_id}")
        
        while retry_count < max_retries:
            try:
                response = await self._request(
                    method="GET",
                    endpoint=f"v1/tasks/status/{task_id}",
                    auth_token=auth_token,
                    timeout=30.0
                )
                
                logger.info(f"第 {retry_count + 1} 次检查状态，响应：{json.dumps(response, ensure_ascii=False, indent=2)}")
                
                # 检查任务状态
                task_status = response.get('task_status', '')
                
                # 处理失败状态
                if task_status == 'failed':
                    error_message = response.get('message', '未知错误')
                    logger.error(f"图片生成失败：{error_message}")
                    return {
                        "status": 500,
                        "error": f"图片生成失败：{error_message}",
                        "task_status": "failed"
                    }
                
                # 处理成功状态
                if response.get('content'):
                    logger.info("图片生成成功")
                    return {
                        "status": 200,
                        "url": response['content'],
                        "task_status": "success"
                    }
                    
                # 检查是否超时
                if time.time() - start_time > timeout:
                    logger.error("等待超时")
                    return {
                        "status": 408, 
                        "error": "等待超时",
                        "task_status": "timeout"
                    }
                    
                # 等待一段时间后重试
                await asyncio.sleep(retry_interval)
                retry_count += 1
                
            except Exception as e:
                error_stack = traceback.format_exc()
                logger.error(f"检查图片生成状态时出错：{str(e)}\n堆栈跟踪：\n{error_stack}")
                await asyncio.sleep(retry_interval)
                retry_count += 1
                
        logger.error("达到最大重试次数")
        return {
            "status": 408, 
            "error": "达到最大重试次数",
            "task_status": "max_retries_exceeded"
        }

    async def video_generation(
        self,
        messages: List[Dict[str, Any]],
        model: Optional[str] = None,
        size: Optional[str] = None,
        auth_token: Optional[str] = None,
        timeout: float = 60.0
    ) -> Any:
        """
        视频生成
        
        Args:
            messages: 消息列表
            model: 模型名称
            size: 尺寸
            auth_token: 认证令牌
            timeout: 超时时间
            
        Returns:
            Any: 响应数据
        """
        try:
            # 验证并处理尺寸参数
            size_map = config_manager.CONSTANTS["VIDEO_SIZES"]
            if not size or size not in size_map:
                size = '1280x720'  # 默认16:9
                
            # 处理模型名称
            if model:
                model = model.replace('-video', '').replace('-thinking', '').replace('-search', '').replace('-draw', '')
            else:
                model = config_manager.CONSTANTS["QWEN_VIDEO_MODEL"]
                
            # 处理消息列表
            processed_messages = []
            for message in messages:
                # 如果是助手消息，只保留必要字段
                if message.get('role') == 'assistant':
                    processed_message = {
                        "role": "assistant",
                        "chat_type": "t2v"
                    }
                    
                    # 处理消息内容
                    content = message.get('content', '')
                    if isinstance(content, str):
                        processed_message['content'] = content
                else:
                    # 非助手消息保持原有格式
                    processed_message = {
                        "role": message.get('role', 'user'),
                        "chat_type": "t2v",
                        "extra": message.get('extra', {}),
                        "feature_config": {
                            "thinking_enabled": False
                        }
                    }
                    
                    # 处理消息内容
                    content = message.get('content', '')
                    if isinstance(content, list):
                        # 处理多模态消息
                        processed_content = []
                        for item in content:
                            if item.get('type') == 'text':
                                processed_content.append({
                                    "type": "text",
                                    "text": item.get('text'),
                                    "chat_type": "t2v",
                                    "feature_config": {
                                        "thinking_enabled": False
                                    }
                                })
                            elif item.get('type') == 'image_url':
                                # 获取图片数据
                                image_data = item.get('image_url', {}).get('url', '')
                                if image_data:
                                    # 使用upload服务处理图片上传
                                    from .upload import upload_service
                                    uploaded_url = await upload_service.save_url(image_data, auth_token)
                                    if uploaded_url:
                                        processed_content.append({
                                            "type": "image",
                                            "image": uploaded_url
                                        })
                            elif item.get('type') == 'image':
                                # 直接处理base64数据
                                image_data = item.get('image', '')
                                if image_data:
                                    # 使用upload服务处理图片上传
                                    from .upload import upload_service
                                    uploaded_url = await upload_service.save_url(image_data, auth_token)
                                    if uploaded_url:
                                        processed_content.append({
                                            "type": "image",
                                            "image": uploaded_url
                                        })
                        processed_message['content'] = processed_content
                    else:
                        processed_message['content'] = content

                processed_messages.append(processed_message)
                
            # 构建请求数据
            data = {
                "stream": False,
                "incremental_output": True,
                "chat_type": "t2v",
                "model": model,
                "messages": processed_messages,
                "session_id": str(uuid.uuid4()),
                "chat_id": str(uuid.uuid4()),
                "id": str(uuid.uuid4()),
                "size": size
            }
            
            logger.info(f"发送视频生成请求，参数：{json.dumps(data, ensure_ascii=False, indent=2)}")
            
            response = await self._request(
                method="POST",
                endpoint="chat/completions",
                data=data,
                auth_token=auth_token,
                timeout=timeout
            )
            
            if not response:
                logger.error("视频生成请求返回空响应")
                return {
                    "status": 500,
                    "error": "视频生成请求返回空响应"
                }
                
            if 'messages' not in response:
                logger.error(f"响应中缺少 messages 字段：{json.dumps(response, ensure_ascii=False, indent=2)}")
                return {
                    "status": 500,
                    "error": "响应格式错误：缺少 messages 字段"
                }
            
            # 提取任务ID
            try:
                # 查找包含任务ID的助手消息
                assistant_messages = [
                    msg for msg in response['messages'] 
                    if msg.get('role') == 'assistant' 
                    and msg.get('extra') 
                    and isinstance(msg['extra'], dict)
                    and msg['extra'].get('wanx')
                    and isinstance(msg['extra']['wanx'], dict)
                    and msg['extra']['wanx'].get('task_id')
                ]
                
                if not assistant_messages:
                    logger.error(f"未找到包含任务ID的助手消息，响应内容：{json.dumps(response, ensure_ascii=False, indent=2)}")
                    return {
                        "status": 500,
                        "error": "未找到包含任务ID的助手消息"
                    }
                    
                task_id = assistant_messages[0]['extra']['wanx']['task_id']
                logger.info(f"成功获取任务ID：{task_id}")
                return {
                    "status": 200,
                    "task_id": task_id
                }
            except Exception as e:
                logger.error(f"提取任务ID失败：{str(e)}")
                logger.error(f"响应内容：{json.dumps(response, ensure_ascii=False, indent=2)}")
                return {
                    "status": 500,
                    "error": f"提取任务ID失败：{str(e)}"
                }
                
        except Exception as e:
            error_stack = traceback.format_exc()
            logger.error(f"视频生成请求异常：{str(e)}\n堆栈跟踪：\n{error_stack}")
            return {
                "status": 500,
                "error": f"视频生成请求异常：{str(e)}"
            }
        
    async def await_video(
        self,
        task_id: str,
        auth_token: Optional[str] = None,
        timeout: float = 1800.0,  # 视频生成可能需要更长时间
        max_retries: int = 360,  # 最大重试次数
        retry_interval: float = 5.0  # 重试间隔(秒)
    ) -> Any:
        """
        等待视频生成完成
        
        Args:
            task_id: 任务ID
            auth_token: 认证令牌
            timeout: 超时时间
            max_retries: 最大重试次数
            retry_interval: 重试间隔(秒)
            
        Returns:
            Any: 响应数据
        """
        start_time = time.time()
        retry_count = 0
        
        logger.info(f"开始等待视频生成完成，任务ID：{task_id}")
        
        while retry_count < max_retries:
            try:
                response = await self._request(
                    method="GET",
                    endpoint=f"v1/tasks/status/{task_id}",  # 使用与图片相同的端点
                    auth_token=auth_token,
                    timeout=30.0
                )
                # 有bug，报错translate algoResult error, result is null.，到时候要用再处理
                logger.info(f"第 {retry_count + 1} 次检查状态，响应：{json.dumps(response, ensure_ascii=False, indent=2)}")
                
                # 检查任务状态
                task_status = response.get('task_status', '')
                
                # 处理失败状态
                if task_status == 'failed':
                    error_message = response.get('message', '未知错误')
                    logger.error(f"视频生成失败：{error_message}")
                    return {
                        "status": 500,
                        "error": f"视频生成失败：{error_message}",
                        "task_status": "failed"
                    }
                
                # 处理成功状态
                if task_status == 'success' and response.get('content'):
                    logger.info("视频生成成功")
                    return {
                        "status": 200,
                        "url": response['content'],
                        "task_status": "success"
                    }
                    
                # 检查是否超时
                if time.time() - start_time > timeout:
                    logger.error("等待超时")
                    return {
                        "status": 408, 
                        "error": "等待超时",
                        "task_status": "timeout"
                    }
                    
                # 等待一段时间后重试
                await asyncio.sleep(retry_interval)
                retry_count += 1
                
            except Exception as e:
                error_stack = traceback.format_exc()
                logger.error(f"检查视频生成状态时出错：{str(e)}\n堆栈跟踪：\n{error_stack}")
                await asyncio.sleep(retry_interval)
                retry_count += 1
                
        logger.error("达到最大重试次数")
        return {
            "status": 408, 
            "error": "达到最大重试次数",
            "task_status": "max_retries_exceeded"
        }

# 创建全局请求服务实例
request_service = RequestService() 