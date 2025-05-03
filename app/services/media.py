from typing import Dict, Any, Optional, List, AsyncGenerator
from pathlib import Path
import uuid
import time
import json
import traceback

from ..core.logger import logger
from .request import request_service

class MediaService:
    """
    统一处理图片/视频生成、文件管理、stream模板生成
    """
    folders = {
        "image": "images",
        "video": "videos"
    }
    ext_map = {
        "image": ["*.png"],
        "video": ["*.mp4"]
    }

    def __init__(self, mtype: str):
        assert mtype in self.folders
        self.mtype = mtype
        self.save_path = Path(self.folders[mtype])
        self.save_path.mkdir(exist_ok=True)
        self.exts = self.ext_map[mtype]

    def get_media_path(self, file_name: str) -> Optional[Path]:
        p = self.save_path / file_name
        return p if p.exists() else None

    def list_medias(self) -> List[str]:
        files = []
        for ext in self.exts:
            files.extend([f.name for f in self.save_path.glob(ext)])
        return files

    def delete_media(self, file_name: str) -> bool:
        p = self.get_media_path(file_name)
        if p:
            p.unlink()
            return True
        return False

    async def generate(
        self,
        messages: List[Dict[str, Any]],
        model: Optional[str] = None,
        size: Optional[str] = None,
        auth_token: Optional[str] = None,
        save: bool = True
    ) -> Dict[str, Any]:
        """
        统一生成图片或视频，并等待完成
        """
        return await request_service.generate_and_wait_media(
            media_type=self.mtype,
            messages=messages,
            model=model,
            size=size,
            auth_token=auth_token,
            save=save
        )

    @staticmethod
    async def draw_stream_template(image_url: str) -> AsyncGenerator[bytes, None]:
        chunk = {
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
        yield f"data: {json.dumps(chunk)}\n\n".encode()
        yield b"data: [DONE]\n\n"

    @staticmethod
    async def video_stream_template(video_url: str) -> AsyncGenerator[bytes, None]:
        chunk = {
            "id": f"chatcmpl-{uuid.uuid4()}",
            "object": "chat.completion.chunk",
            "created": int(time.time() * 1000),
            "choices": [
                {
                    "index": 0,
                    "delta": {
                        "content": f"<video controls='controls' src='{video_url}' data-src='{video_url}'></video>"
                    },
                    "finish_reason": None
                }
            ]
        }
        yield f"data: {json.dumps(chunk)}\n\n".encode()
        yield b"data: [DONE]\n\n"

    @staticmethod
    def image_nonstream_response(model: str, messages: List[dict], image_url: str) -> dict:
        content = f"![{image_url}]({image_url})"
        t = int(time.time() * 1000)
        body = {
            "id": f"chatcmpl-{uuid.uuid4()}",
            "object": "chat.completion",
            "created": t,
            "model": model,
            "choices": [{
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": content
                },
                "finish_reason": "stop"
            }],
            "usage": {
                "prompt_tokens": len(json.dumps(messages)),
                "completion_tokens": len(content),
                "total_tokens": len(json.dumps(messages)) + len(content)
            }
        }
        return body

    @staticmethod
    def video_nonstream_response(model: str, video_url: str) -> dict:
        content = f"<video controls='controls' src='{video_url}' data-src='{video_url}'></video>"
        t = int(time.time() * 1000)
        return {
            "id": f"chatcmpl-{uuid.uuid4()}",
            "object": "chat.completion",
            "created": t,
            "model": model,
            "choices": [{
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": content
                },
                "finish_reason": "stop"
            }],
            "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
        }


image_service = MediaService("image")
video_service = MediaService("video")