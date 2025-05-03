from fastapi import FastAPI, Request, Depends, HTTPException, APIRouter
from fastapi.responses import JSONResponse, StreamingResponse
from app.service.model_service import ModelService
from app.service.completion_service import CompletionService
from app.service.message_service import MessageService
from app.core.cookie_service import CookieService
from app.core.security import verify_api_key
from app.core.account_manager import AccountManager
from app.models.chat import ChatRequest
from app.service.upload_service import UploadService
# 请确保已提前实例化 ModelService、CompletionService、MessageService
model_service = ModelService()
completion_service = CompletionService()
cookie_service = CookieService(AccountManager())
upload_service = UploadService()
message_service = MessageService(model_service, completion_service, cookie_service, upload_service)

router = APIRouter(prefix="/v1", tags=["chat"])

@router.post("/chat/completions")
async def openai_compatible_chat(
    request: ChatRequest,
    auth: str = Depends(verify_api_key)
):
    try:
        token = cookie_service.get_auth_token()
        result = await message_service.chat(request, token)  # 直接传 Pydantic 实例
        if hasattr(result, "body_iterator"):  # 判断是否为 StreamingResponse
            return result
        return JSONResponse(result)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))