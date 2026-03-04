# -*- coding: utf-8 -*-
"""
Helper functions for converting between different API formats.
"""

from typing import Any, Dict, List


def anthropic_to_unified_messages(messages: List[Any]) -> List[Dict[str, Any]]:
    """
    Convert Anthropic messages to simple OpenAI-compatible format.
    
    Anthropic format:
    - role: "user" | "assistant"
    - content: string | list of content blocks
    
    OpenAI format:
    - role: "user" | "assistant" | "system"
    - content: string
    
    Args:
        messages: List of Anthropic messages
    
    Returns:
        List of OpenAI-compatible messages
    """
    result = []
    
    for msg in messages:
        # Handle both dict and Pydantic objects
        if isinstance(msg, dict):
            role = msg.get("role", "user")
            content = msg.get("content", "")
        else:
            role = msg.role
            content = msg.content
        
        # Extract text from content
        if isinstance(content, str):
            text = content
        elif isinstance(content, list):
            # Extract text from content blocks
            text_parts = []
            for block in content:
                if isinstance(block, dict):
                    if block.get("type") == "text":
                        text_parts.append(block.get("text", ""))
                elif hasattr(block, "type") and block.type == "text":
                    text_parts.append(block.text)
            text = "".join(text_parts)
        else:
            text = str(content)
        
        result.append({
            "role": role,
            "content": text
        })
    
    return result
