from fastapi import APIRouter, Depends, Request, Response,  HTTPException
from fastapi.responses import StreamingResponse
import uuid
import time
import json
import traceback
from datetime import datetime

from app.models.api import ChatRequest
from app.core.security import verify_auth
from app.core.config import config_manager
from app.services.account import account_manager
from app.services.request import request_service
from app.services.upload import upload_service
from app.services.media import image_service, video_service  # ← 用统一media服务
from app.core.logger import logger

router = APIRouter()

@router.post("/completions")
async def chat_completions(
    request: ChatRequest,
    raw_request: Request,
    token: str = Depends(verify_auth)
):
    auth_token = account_manager.get_account_token()
    stream = request.stream if request.stream is not None else False
    model = request.model

    # === [1] 保证原messages所有历史全保留 ===
    messages = [m.dict() for m in request.messages]

    # === [2] 只对messages中每条需要的内容做变更，尤其最后一轮图片特殊处理 ===
    if messages and isinstance(messages[-1].get('content', ''), list):
        last_content = messages[-1]['content']
        # 逐item做图片url本地上传改写，其它内容均原样保留
        for idx, item in enumerate(last_content):
            if item.get('type') == 'image_url' and item.get('image_url', {}).get('url'):
                file_url = await upload_service.save_url(item['image_url']['url'], auth_token)
                # 替换本条为 image
                messages[-1]['content'][idx] = {
                    "type": "image",
                    "image": file_url
                }

    try:
        # -------- 图像请求 --------
        if '-draw' in model:
            size = config_manager.get('image.size', '1024*1024')
            resp = await image_service.generate(
                messages=messages,        # << 全量messages, 允许被自定义结构规整
                model=model,
                size=size,
                auth_token=auth_token
            )
            if resp.get('status') != 200:
                return Response(
                    content=json.dumps({
                        "error": resp.get('error', '未知错误'),
                        "type": "image_generation_error"
                    }), status_code=500, media_type="application/json"
                )
            if stream:
                return StreamingResponse(
                    image_service.draw_stream_template(resp['url']),
                    media_type="text/event-stream",
                    headers={"Cache-Control": "no-cache", "Connection": "keep-alive"}
                )
            else:
                return Response(
                    content=json.dumps(image_service.image_nonstream_response(model, messages, resp['url'])),
                    media_type="application/json"
                )

        # -------- 视频请求 --------
        if '-video' in model:
            size = config_manager.get('video.size', '1280x720')
            # ===【不要拼接prompt！全量messages传递】===
            resp = await video_service.generate(
                messages=messages,    # << 也是全量，每条可带图片/文本等结构，底层保证够用
                model=model,
                size=size,
                auth_token=auth_token
            )
            if resp.get('status') != 200:
                return Response(
                    content=json.dumps({
                        "error": resp.get('error', '未知错误'),
                        "type": "video_generation_error"
                    }), status_code=500, media_type="application/json"
                )
            if stream:
                return StreamingResponse(
                    video_service.video_stream_template(resp['url']),
                    media_type="text/event-stream",
                    headers={"Cache-Control": "no-cache", "Connection": "keep-alive"}
                )
            else:
                return Response(
                    content=json.dumps(video_service.video_nonstream_response(model, resp['url'])),
                    media_type="application/json"
                )

        # -------- 普通对话 --------
        response_data = await request_service.chat_completion(
            model=model,
            messages=messages,         # << 全量上下文！
            stream=stream,
            auth_token=auth_token,
            temperature=request.temperature
        )
        if response_data.get('status') != 200:
            err = response_data.get('response', {}).get('error', {})
            return Response(
                content=json.dumps({
                    "error": {
                        "message": err.get('message', '未知错误'),
                        "type": err.get('type', 'internal_server_error'),
                        "stack_trace": err.get('stack_trace', '')
                    }
                }),
                status_code=500,
                media_type="application/json"
            )
        if stream:
            return StreamingResponse(
                response_data.get('response'),
                media_type="text/event-stream",
                headers={
                    "Cache-Control": "no-cache",
                    "Connection": "keep-alive"
                }
            )
        else:
            resp = response_data.get('response')
            body_template = {
                "id": f"chatcmpl-{uuid.uuid4()}",
                "object": "chat.completion",
                "created": int(time.time() * 1000),
                "model": model,
                "choices": [
                    {
                        "index": 0,
                        "message": {
                            "role": "assistant",
                            "content": resp['choices'][0]['message']['content'] if resp and resp.get('choices') else ''
                        },
                        "finish_reason": "stop"
                    }
                ],
                "usage": {
                    "prompt_tokens": len(json.dumps(messages)),
                    "completion_tokens": len(resp['choices'][0]['message']['content']) if resp and resp.get('choices') else 0,
                    "total_tokens": len(json.dumps(messages)) + (len(resp['choices'][0]['message']['content']) if resp and resp.get('choices') else 0)
                }
            }
            return Response(content=json.dumps(body_template), media_type="application/json")
    except Exception as e:
        logger.error(f"chat_completions error: {e}\n{traceback.format_exc()}")
        return Response(
            content=json.dumps({"error": str(e), "stack_trace": traceback.format_exc()}),
            status_code=500,
            media_type="application/json"
        )