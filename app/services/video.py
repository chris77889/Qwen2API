"""
视频服务
"""
from typing import Dict, Any, Optional, List
from pathlib import Path
import traceback

from ..core.logger import logger
from ..core.config import config_manager
from .request import request_service


class VideoService:
    """视频服务"""
    
    def __init__(self):
        """初始化视频服务"""
        self.save_path = Path("videos")
        self.save_path.mkdir(exist_ok=True)
        
    async def generate_video(
        self,
        messages: List[Dict[str, Any]],
        model: Optional[str] = None,
        size: Optional[str] = None,
        auth_token: Optional[str] = None,
        save: bool = True
    ) -> Dict[str, Any]:
        """
        生成视频
        
        Args:
            messages: 消息列表
            model: 模型名称
            size: 尺寸
            auth_token: 认证令牌
            save: 是否保存视频
            
        Returns:
            Dict[str, Any]: 生成结果
        """
        try:
            # 发送视频生成请求
            response = await request_service.video_generation(
                messages=messages,
                model=model,
                size=size,
                auth_token=auth_token
            )
            
            if response['status'] != 200:
                error_msg = response.get('error', '视频生成请求失败')
                logger.error(f"视频生成请求失败：{error_msg}")
                return {
                    "status": 500,
                    "error": error_msg
                }
                
            if not response.get('task_id'):
                error_msg = "未获取到任务ID"
                logger.error(error_msg)
                return {
                    "status": 500,
                    "error": error_msg
                }
                
            # 等待视频生成完成
            result = await request_service.await_video(
                task_id=response['task_id'],
                auth_token=auth_token
            )
            
            if result.get('status') != 200:
                error_msg = result.get('error', '视频生成失败')
                logger.error(f"视频生成失败：{error_msg}")
                return {
                    "status": 500,
                    "error": error_msg
                }
                
            if not result.get('url'):
                error_msg = "未获取到生成的视频URL"
                logger.error(error_msg)
                return {
                    "status": 500,
                    "error": error_msg
                }
                
            logger.info(f"视频生成成功，URL：{result['url']}")
            return {
                "status": 200,
                "url": result['url']
            }
            
        except Exception as e:
            error_msg = f"视频生成失败: {str(e)}"
            return {"error": error_msg, "status": 500}
    
    def get_video_path(self, file_name: str) -> Optional[Path]:
        """
        获取视频路径
        
        Args:
            file_name: 文件名
            
        Returns:
            Optional[Path]: 视频路径
        """
        video_path = self.save_path / file_name
        return video_path if video_path.exists() else None
    
    def list_videos(self) -> List[str]:
        """
        获取所有视频列表
        
        Returns:
            List[str]: 视频文件名列表
        """
        return [f.name for f in self.save_path.glob("*.mp4")]
    
    def delete_video(self, file_name: str) -> bool:
        """
        删除视频
        
        Args:
            file_name: 文件名
            
        Returns:
            bool: 是否成功删除
        """
        video_path = self.get_video_path(file_name)
        if video_path:
            video_path.unlink()
            return True
        return False


# 创建全局视频服务实例
video_service = VideoService() 