"""
任务服务
"""
from typing import Dict, Any, Optional
import asyncio
import json
from app.core.logger.logger import get_logger
from app.core.cookie_service import CookieService
import httpx
import time
from app.core.config_manager import ConfigManager
import uuid
config_manager = ConfigManager()
logger = get_logger(__name__)

class TaskService:
    """任务服务，处理异步任务状态查询"""
    
    def __init__(self, cookie_service: CookieService):
        """
        初始化任务服务
        
        Args:
            cookie_service: CookieService实例，用于获取认证信息
        """
        self.cookie_service = cookie_service
        self.base_url = config_manager.get("api.url","https://chat.qwen.ai/api")
        
    async def poll_image_task(
        self,
        task_id: str,
        auth_token: str,
        max_retries: int = 60,
        retry_interval: float = 3.0,
        timeout: float = 180.0
    ) -> Dict[str, Any]:
        """
        轮询图片生成任务状态
        
        Args:
            task_id: 任务ID
            auth_token: 认证Token
            max_retries: 最大重试次数
            retry_interval: 重试间隔（秒）
            timeout: 超时时间（秒）
            
        Returns:
            Dict[str, Any]: 任务状态和结果
        """
        return await self._poll_task(
            task_id=task_id,
            auth_token=auth_token,
            task_type="t2i",
            max_retries=max_retries,
            retry_interval=retry_interval,
            timeout=timeout
        )
        
    async def poll_video_task(
        self,
        task_id: str,
        auth_token: str,
        max_retries: int = 120,
        retry_interval: float = 5.0,
        timeout: float = 600.0
    ) -> Dict[str, Any]:
        """
        轮询视频生成任务状态
        
        Args:
            task_id: 任务ID
            auth_token: 认证Token
            max_retries: 最大重试次数
            retry_interval: 重试间隔（秒）
            timeout: 超时时间（秒）
            
        Returns:
            Dict[str, Any]: 任务状态和结果
        """
        return await self._poll_task(
            task_id=task_id,
            auth_token=auth_token,
            task_type="t2v",
            max_retries=max_retries,
            retry_interval=retry_interval,
            timeout=timeout
        )
    
    async def _poll_task(
        self,
        task_id: str,
        auth_token: str,
        task_type: str,
        max_retries: int,
        retry_interval: float,
        timeout: float
    ) -> Dict[str, Any]:
        """
        通用任务轮询实现
        
        Args:
            task_id: 任务ID
            auth_token: 认证Token
            task_type: 任务类型（t2i或t2v）
            max_retries: 最大重试次数
            retry_interval: 重试间隔（秒）
            timeout: 超时时间（秒）
            
        Returns:
            Dict[str, Any]: 任务状态和结果
        """

        
        start_time = time.time()
        retry_count = 0
        
        while retry_count < max_retries:
            try:
                status = await self.get_task_status(task_id, auth_token)
                logger.info(f"第{retry_count + 1}次检查任务状态: {json.dumps(status, ensure_ascii=False)}")
                
                # 检查任务是否完成
                task_status = status.get("task_status", "")
                
                # 任务失败
                if task_status == "failed":
                    error_message = status.get("message", "未知错误")
                    logger.error(f"任务失败: {error_message}")
                    return self.format_task_response(
                        task_type=task_type,
                        status="failed",
                        message=error_message
                    )
                
                # 任务成功
                if status.get("content"):
                    logger.info("任务完成")
                    return self.format_task_response(
                        task_type=task_type,
                        status="success",
                        content=status["content"]
                    )
                
                # 检查是否超时
                if time.time() - start_time > timeout:
                    logger.error("任务超时")
                    return self.format_task_response(
                        task_type=task_type,
                        status="timeout",
                        message="任务超时"
                    )
                
                # 继续等待
                await asyncio.sleep(retry_interval)
                retry_count += 1
                
            except Exception as e:
                logger.error(f"查询任务状态出错: {str(e)}")
                await asyncio.sleep(retry_interval)
                retry_count += 1
        
        # 达到最大重试次数
        return self.format_task_response(
            task_type=task_type,
            status="max_retries_exceeded",
            message="达到最大重试次数"
        )
    
    async def get_task_status(self, task_id: str, auth_token: str) -> Dict[str, Any]:
        """
        获取任务状态
        
        Args:
            task_id: 任务ID
            auth_token: 认证Token
            
        Returns:
            Dict[str, Any]: 任务状态信息
        """
        import httpx
        
        headers = self.cookie_service.get_headers(auth_token)
        
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.base_url}/v1/tasks/status/{task_id}",
                headers=headers,
                timeout=30.0
            )
            
            if response.status_code != 200:
                raise Exception(f"获取任务状态失败: {response.text}")
                
            return response.json()
    
    def format_task_response(
        self,
        task_type: str,
        status: str,
        message: str = "",
        content: str = ""
    ) -> Dict[str, Any]:
        """
        格式化任务响应
        
        Args:
            task_type: 任务类型（t2i或t2v）
            status: 任务状态
            message: 状态消息
            content: 任务结果内容
            
        Returns:
            Dict[str, Any]: 格式化的响应
        """
        response = {
            "chat_type": task_type,
            "task_status": status,
            "message": message,
            "remaining_time": "",
            "content": content
        }
        
        # 如果是成功的图片任务，使用openai格式返回
        if status == "success" and task_type == "t2i" and content:
            response = {
                'id': 'chatcmpl-'+uuid.uuid4().hex,
                'object': 'chat.completion',
                'created': int(time.time()*1000),
                'model': 'qwen-turbo', 
                'choices': [
                    {'index': 0, 
                     'message':
                       {
                           'role': 'assistant', 
                           'content': f"![Generated Image]({content})"
                           }, 
                           'finish_reason': 'stop'
                           }
                           ], 'usage': {'prompt_tokens': 0, 'completion_tokens': 0, 'total_tokens': 0}}
        elif status == "success" and task_type == "t2v" and content:
            response = {
                'id': 'chatcmpl-'+uuid.uuid4().hex,
                'object': 'chat.completion',
                'created': int(time.time()*1000),
                'model': 'qwen-turbo', 
                'choices': [
                    {'index': 0, 
                     'message':
                       {
                           'role': 'assistant', 
                           'content': f"[链接]({content})"
                           }, 
                           'finish_reason': 'stop'
                           }
                           ], 
                           'usage': 
                           {'prompt_tokens': 0, 'completion_tokens': 0, 'total_tokens': 0}}
            
        return response