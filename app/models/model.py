from pydantic import BaseModel
from typing import List, Dict, Any

class ModelResponse(BaseModel):
    id: str
    object: str
    created: int
    owned_by: str
