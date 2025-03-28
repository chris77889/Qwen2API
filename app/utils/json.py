"""
JSON工具模块
"""
import json
from typing import Any


def is_json(text: Any) -> bool:
    """
    检查文本是否为有效的JSON
    
    Args:
        text: 要检查的文本
        
    Returns:
        bool: 是否为有效的JSON
    """
    try:
        if not isinstance(text, (str, bytes, bytearray)):
            return False
        json.loads(text)
        return True
    except ValueError:
        return False 