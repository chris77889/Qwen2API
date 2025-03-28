"""
图像服务
"""
from typing import Dict, Any, Optional, List
import base64
from pathlib import Path
import traceback

from ..core.logger import logger    
from ..core.config import config_manager
from .request import request_service


class ImageService:
    """图像服务"""
    
    def __init__(self):
        """初始化图像服务"""
        self.save_path = Path("images")
        self.save_path.mkdir(exist_ok=True)
        
    async def generate_image(
        self,
        messages: List[Dict[str, Any]],
        model: Optional[str] = None,
        size: Optional[str] = None,
        auth_token: Optional[str] = None,
        save: bool = True
    ) -> Dict[str, Any]:
        """
        生成图像
        
        Args:
            messages: 消息列表
            model: 模型名称
            size: 尺寸
            auth_token: 认证令牌
            save: 是否保存图像
            
        Returns:
            Dict[str, Any]: 生成结果
        """
        try:
            # 发送图像生成请求
            response = await request_service.image_generation(
                model=model,
                size=size,
                auth_token=auth_token,
                messages=messages
            )
            
            if response.get('status') != 200:
                error_msg = response.get('error', '图像生成请求失败')
                logger.error(f"图像生成请求失败：{error_msg}")
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
                
            # 等待图像生成完成
            result = await request_service.await_image(
                task_id=response['task_id'],
                auth_token=auth_token
            )
            
            if result.get('status') != 200:
                error_msg = result.get('error', '图像生成失败')
                logger.error(f"图像生成失败：{error_msg}")
                return {
                    "status": 500,
                    "error": error_msg
                }
                
            if not result.get('url'):
                error_msg = "未获取到生成的图像URL"
                logger.error(error_msg)
                return {
                    "status": 500,
                    "error": error_msg
                }
                
            logger.info(f"图像生成成功，URL：{result['url']}")
            return {
                "status": 200,
                "url": result['url']
            }
            
        except Exception as e:
            error_stack = traceback.format_exc()
            error_msg = f"图像生成失败: {str(e)}"
            logger.error(f"{error_msg}\n堆栈跟踪：\n{error_stack}")
            return {
                "status": 500,
                "error": error_msg
            }
    
    def get_image_path(self, file_name: str) -> Optional[Path]:
        """
        获取图像路径
        
        Args:
            file_name: 文件名
            
        Returns:
            Optional[Path]: 图像路径
        """
        image_path = self.save_path / file_name
        return image_path if image_path.exists() else None
    
    def list_images(self) -> List[str]:
        """
        获取所有图像列表
        
        Returns:
            List[str]: 图像文件名列表
        """
        return [f.name for f in self.save_path.glob("*.png")]
    
    def delete_image(self, file_name: str) -> bool:
        """
        删除图像
        
        Args:
            file_name: 文件名
            
        Returns:
            bool: 是否成功删除
        """
        image_path = self.get_image_path(file_name)
        if image_path:
            image_path.unlink()
            return True
        return False


# 创建全局图像服务实例
image_service = ImageService() 