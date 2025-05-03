"""
上传服务
"""
from typing import Optional
import uuid
import httpx
import json
import traceback
import alibabacloud_oss_v2 as oss
import base64
from hmac import HMAC
from hashlib import sha256

from ..core.config import config_manager
from .account import account_manager
from ..core.logger import logger


class UploadService:
    """上传服务 - 仅支持OSS上传"""
    
    def __init__(self):
        """初始化上传服务"""
        pass

    def _calculate_signature(self, sts_response: dict, date: str) -> str:
        """
        计算OSS签名
        
        Args:
            sts_response: STS返回的数据
            date: ISO8601格式的日期时间(YYYYMMDD'T'HHMMSS'Z')
            
        Returns:
            str: 计算得到的签名
        """
        # 获取日期和区域
        date_stamp = date[:8]  # 20250325
        region = sts_response['region'].replace('oss-', '')  # 从 'oss-ap-southeast-1' 提取为 'ap-southeast-1'
        
        # 构建凭证范围
        credential_scope = f"{date_stamp}/{region}/oss/aliyun_v4_request"
        
        # 构建规范请求 - 确保每个头部值前后没有多余空格
        canonical_headers = (
            f"content-type:image/jpeg\n"
            f"host:{sts_response['bucketname']}.{sts_response['region']}.aliyuncs.com\n"
            f"x-oss-content-sha256:UNSIGNED-PAYLOAD\n"
            f"x-oss-date:{date}\n"
            f"x-oss-security-token:{sts_response['security_token']}"  # 注意：最后一个头部后不加换行符
        )
        
        signed_headers = "content-type;host;x-oss-content-sha256;x-oss-date;x-oss-security-token"
        
        canonical_request = (
            "PUT\n"  # HTTP方法
            f"/{sts_response['file_path']}\n"  # 规范URI
            "\n"     # 规范查询字符串
            f"{canonical_headers}\n"  # 规范头
            f"{signed_headers}\n"  # 已签名的头
            "UNSIGNED-PAYLOAD"  # 负载哈希
        )
        
        # 构建签名字符串
        string_to_sign = (
            "OSS4-HMAC-SHA256\n"
            f"{date}\n"
            f"{credential_scope}\n"
            f"{sha256(canonical_request.encode('utf-8')).hexdigest()}"
        )
        
        # 计算签名密钥
        k_date = HMAC(("aliyun_v4" + sts_response['access_key_secret']).encode('utf-8'), 
                      date_stamp.encode('utf-8'), sha256).digest()
        k_region = HMAC(k_date, region.encode('utf-8'), sha256).digest()
        k_service = HMAC(k_region, b'oss', sha256).digest()
        k_signing = HMAC(k_service, b'aliyun_v4_request', sha256).digest()
        
        # 计算最终签名
        signature = HMAC(k_signing, string_to_sign.encode('utf-8'), sha256).hexdigest()
        
        return signature

    async def _upload_to_oss(self, image_bytes: bytes, auth_token: str) -> Optional[str]:
        """
        上传图片到OSS
        
        Args:
            image_bytes: 图片二进制数据
            auth_token: 认证Token
            
        Returns:
            Optional[str]: 上传成功返回图片URL，失败返回None
        """
        try:
            # 获取STS Token
            logger.info("正在获取STS Token...")
            async with httpx.AsyncClient() as client:
                sts_response = await client.post(
                    f"{config_manager.get('api.url', 'https://chat.qwen.ai/api')}/v1/files/getstsToken",
                    headers=account_manager.get_headers(auth_token),
                    json={
                        "filename": f"{uuid.uuid4()}.jpg",
                        "filesize": len(image_bytes),
                        "filetype": "image"
                    }
                )
                
                if sts_response.status_code != 200:
                    error_msg = f"获取STS Token失败: 状态码={sts_response.status_code}, 响应内容={sts_response.text}"
                    logger.error(error_msg)
                    return None
                    
                sts_data = sts_response.json()
                logger.info(f"获取到的STS Token响应: {json.dumps(sts_data, indent=2)}")

            # 创建静态凭证提供者
            credentials_provider = oss.credentials.StaticCredentialsProvider(
                access_key_id=sts_data['access_key_id'],
                access_key_secret=sts_data['access_key_secret'],
                security_token=sts_data['security_token']
            )

            # 加载SDK的默认配置，并设置凭证提供者
            cfg = oss.config.load_default()
            cfg.credentials_provider = credentials_provider
            
            # 设置region（去掉oss-前缀）
            region = sts_data['region'].replace('oss-', '')
            cfg.region = region

            # 创建OSS客户端
            client = oss.Client(cfg)

            # 构建上传请求
            put_object_request = oss.models.PutObjectRequest(
                bucket=sts_data['bucketname'],
                key=sts_data['file_path'],
                body=image_bytes,
                content_type='image/jpeg'
            )

            # 执行上传
            logger.info(f"开始上传图片到OSS: {sts_data['bucketname']}/{sts_data['file_path']}")
            response = client.put_object(put_object_request)
            
            if response.status_code == 200:
                logger.info(f"图片上传成功，URL: {sts_data['file_url']}")
                return sts_data['file_url']
            else:
                error_msg = f"上传图片失败: 状态码={response.status_code}"
                logger.error(error_msg)
                return None

        except Exception as e:
            error_stack = traceback.format_exc()
            logger.error(f"上传图片到OSS时出错: {str(e)}\n堆栈跟踪:\n{error_stack}")
            return None

    async def save_url(self, url: str, auth_token: Optional[str] = None) -> Optional[str]:
        """
        保存URL指向的图像到OSS
        
        Args:
            url: 图像URL
            auth_token: 认证Token
            
        Returns:
            Optional[str]: 上传成功返回图片URL，失败返回None
        """
        try:
            if not auth_token or not url:
                return None

            # 检查是否为OSS URL
            if 'cdn.qwenlm.ai' in url:
                logger.info("检测到OSS URL，直接返回")
                return url

            # 获取图片二进制数据
            if url.startswith('data:'):
                logger.info("处理base64格式的图像数据")
                # 从data URL中提取MIME类型和数据
                matches = url.split(';base64,')
                if len(matches) == 2:
                    base64_data = matches[1]
                else:
                    base64_data = url.split(',')[1]
                
                # 解码base64数据
                image_bytes = base64.b64decode(base64_data)
            else:
                # 从URL下载图像
                logger.info(f"从URL下载图像: {url}")
                async with httpx.AsyncClient() as client:
                    response = await client.get(url)
                    if response.status_code != 200:
                        error_msg = f"下载图像失败: 状态码={response.status_code}, 响应内容={response.text}"
                        logger.error(error_msg)
                        return None
                    image_bytes = response.content

            # 上传到OSS
            return await self._upload_to_oss(image_bytes, auth_token)
                
        except Exception as e:
            error_stack = traceback.format_exc()
            logger.error(f"处理图像URL失败: {str(e)}\n堆栈跟踪:\n{error_stack}")
            return None

# 创建服务实例
upload_service = UploadService() 