from typing import Optional
import uuid
import httpx
import json
import traceback
import alibabacloud_oss_v2 as oss
import base64
from hmac import HMAC
from hashlib import sha256
import aiofiles
import hashlib
import asyncio
import os
from app.core.config_manager import ConfigManager
from app.core.account_manager import AccountManager
from app.core.cookie_service import CookieService
from app.core.logger.logger import get_logger

config_manager = ConfigManager()
account_manager = AccountManager()
cookie_service = CookieService(account_manager)
logger = get_logger(__name__)

UPLOAD_CACHE_FILE = os.path.join('data', 'upload.json')

class UploadService:
    """
    上传服务，不依赖initialize，缓存操作fire&forget，主流程100%不会阻塞/卡死/报协程警告
    """
    def __init__(self):
        self.upload_cache = {}
        self.cache_loaded = False
        self.cache_lock = asyncio.Lock()
        self._load_cache_launched = False

        if not os.path.exists('data'):
            os.makedirs('data', exist_ok=True)
        # 不要在 __init__ 调用任何异步任务！

    async def _file_sha256(self, image_bytes: bytes) -> str:
        return hashlib.sha256(image_bytes).hexdigest()

    async def _background_load_cache(self):
        # 后台真正懒加载缓存（只在事件循环内调用，不会在__init__强制调动）
        if self.cache_loaded or self._load_cache_launched:
            return
        self._load_cache_launched = True
        try:
            async with self.cache_lock:
                if os.path.exists(UPLOAD_CACHE_FILE):
                    async with aiofiles.open(UPLOAD_CACHE_FILE, 'r', encoding='utf-8') as f:
                        content = await f.read()
                        self.upload_cache = json.loads(content) if content.strip() else {}
                else:
                    self.upload_cache = {}
        except Exception as e:
            logger.warning(f"后台加载upload_cache失败: {e}")
            self.upload_cache = {}
        self.cache_loaded = True

    def _save_cache_background(self):
        async def _do_save():
            try:
                async with self.cache_lock:
                    async with aiofiles.open(UPLOAD_CACHE_FILE, 'w', encoding='utf-8') as f:
                        await f.write(json.dumps(self.upload_cache, ensure_ascii=False, indent=2))
            except Exception as e:
                logger.warning(f"异步写upload_cache失败: {e}")
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(_do_save())
        except RuntimeError:
            # 事件循环未开启，直接跳过
            pass

    async def _check_or_set_upload_cache(self, image_bytes: bytes, url: str = None) -> Optional[str]:
        # 永远不等待缓存加载，没加载就fire一次后台（只fire不等，安全）
        if not self.cache_loaded and not self._load_cache_launched:
            try:
                loop = asyncio.get_running_loop()
                loop.create_task(self._background_load_cache())
            except RuntimeError:
                pass # 没有事件循环，服务启动期不用缓存
            return None
        if not self.cache_loaded:
            return None
        try:
            sha256_digest = await self._file_sha256(image_bytes)
            if sha256_digest in self.upload_cache:
                return self.upload_cache[sha256_digest]
            if url:
                self.upload_cache[sha256_digest] = url
                self._save_cache_background()
        except Exception as e:
            logger.warning(f'上传缓存操作异常: {e}')
        return None

    def _calculate_signature(self, sts_response: dict, date: str) -> str:
        date_stamp = date[:8]
        region = sts_response['region'].replace('oss-', '')
        credential_scope = f"{date_stamp}/{region}/oss/aliyun_v4_request"
        canonical_headers = (
            f"content-type:image/jpeg\n"
            f"host:{sts_response['bucketname']}.{sts_response['region']}.aliyuncs.com\n"
            f"x-oss-content-sha256:UNSIGNED-PAYLOAD\n"
            f"x-oss-date:{date}\n"
            f"x-oss-security-token:{sts_response['security_token']}"
        )
        signed_headers = "content-type;host;x-oss-content-sha256;x-oss-date;x-oss-security-token"
        canonical_request = (
            "PUT\n"
            f"/{sts_response['file_path']}\n"
            "\n"
            f"{canonical_headers}\n"
            f"{signed_headers}\n"
            "UNSIGNED-PAYLOAD"
        )
        string_to_sign = (
            "OSS4-HMAC-SHA256\n"
            f"{date}\n"
            f"{credential_scope}\n"
            f"{sha256(canonical_request.encode('utf-8')).hexdigest()}"
        )
        k_date = HMAC(("aliyun_v4" + sts_response['access_key_secret']).encode('utf-8'),
                      date_stamp.encode('utf-8'), sha256).digest()
        k_region = HMAC(k_date, region.encode('utf-8'), sha256).digest()
        k_service = HMAC(k_region, b'oss', sha256).digest()
        k_signing = HMAC(k_service, b'aliyun_v4_request', sha256).digest()
        signature = HMAC(k_signing, string_to_sign.encode('utf-8'), sha256).hexdigest()
        return signature

    async def _upload_to_oss(self, image_bytes: bytes, auth_token: str) -> Optional[str]:
        try:
            logger.info("正在获取STS Token...")
            async with httpx.AsyncClient(timeout=15) as client:
                sts_response = await client.post(
                    f"{config_manager.get('api.url', 'https://chat.qwen.ai/api')}/v1/files/getstsToken",
                    headers=cookie_service.get_headers(auth_token),
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
                #logger.info(f"获取到的STS Token响应: {json.dumps(sts_data, indent=2)}")

            credentials_provider = oss.credentials.StaticCredentialsProvider(
                access_key_id=sts_data['access_key_id'],
                access_key_secret=sts_data['access_key_secret'],
                security_token=sts_data['security_token']
            )
            cfg = oss.config.load_default()
            cfg.credentials_provider = credentials_provider
            region = sts_data['region'].replace('oss-', '')
            cfg.region = region
            client = oss.Client(cfg)
            put_object_request = oss.models.PutObjectRequest(
                bucket=sts_data['bucketname'],
                key=sts_data['file_path'],
                body=image_bytes,
                content_type='image/jpeg'
            )
            #logger.info(f"开始上传图片到OSS: {sts_data['bucketname']}/{sts_data['file_path']}")
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
        try:
            if not auth_token or not url:
                return None

            if 'cdn.qwen.ai' in url:
                logger.info("检测到OSS URL，直接返回")
                return url

            if url.startswith('data:'):
                logger.info("处理base64格式的图像数据")
                matches = url.split(';base64,')
                if len(matches) == 2:
                    base64_data = matches[1]
                else:
                    base64_data = url.split(',')[1]
                image_bytes = base64.b64decode(base64_data)
            else:
                logger.info(f"从URL下载图像: {url}")
                async with httpx.AsyncClient(timeout=15) as client:
                    response = await client.get(url)
                    if response.status_code != 200:
                        logger.error(f"下载图像失败: 状态码={response.status_code}, 响应内容={response.text}")
                        return None
                    image_bytes = response.content

            # 判重（缓存未加载/失败不影响业务）
            cached_url = await self._check_or_set_upload_cache(image_bytes)
            if cached_url:
                logger.info(f"缓存命中：SHA256={await self._file_sha256(image_bytes)} / URL={cached_url}")
                return cached_url

            uploaded_url = await asyncio.wait_for(self._upload_to_oss(image_bytes, auth_token), timeout=30)
            if uploaded_url:
                try:
                    await self._check_or_set_upload_cache(image_bytes, url=uploaded_url)
                except Exception as e:
                    logger.warning(f"上传后写缓存失败: {e}")
                return uploaded_url

            return None
        except Exception as e:
            error_stack = traceback.format_exc()
            logger.error(f"处理图像URL失败: {str(e)}\n堆栈跟踪:\n{error_stack}")
            return None