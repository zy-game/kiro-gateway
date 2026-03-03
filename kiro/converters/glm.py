# -*- coding: utf-8 -*-
"""
GLM (智谱AI) format converter.

Converts between OpenAI format and GLM API format.
Handles both request conversion and streaming response conversion.
"""

import json
import time
from typing import Any, Dict, List, Optional

from loguru import logger


class GLMConverter:
    """
    Converter for GLM API format.
    
    GLM API is mostly compatible with OpenAI format, but has some differences:
    - May return reasoning_content field that needs to be merged with content
    - Tool format is compatible with OpenAI
    """
    
    @staticmethod
    def convert_to_glm_format(
        messages: List[Dict[str, Any]],
        model: str,
        stream: bool = True,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        tools: Optional[List[Dict[str, Any]]] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Convert OpenAI request format to GLM format.
        
        GLM API is mostly compatible with OpenAI, so minimal conversion needed.
        
        Args:
            messages: Chat messages in OpenAI format
            model: Model name
            stream: Whether to stream response
            temperature: Sampling temperature
            max_tokens: Maximum tokens to generate
            tools: Tool definitions in OpenAI format
            **kwargs: Additional parameters
        
        Returns:
            Request dict in GLM format
        """
        glm_data = {
            "model": model,
            "messages": messages,
            "stream": stream
        }
        
        # Optional parameters
        if temperature is not None:
            glm_data["temperature"] = temperature
        if max_tokens is not None:
            glm_data["max_tokens"] = max_tokens
        if tools:
            # Ensure tools have correct format
            formatted_tools = GLMConverter._ensure_tools_format(tools)
            if formatted_tools:
                glm_data["tools"] = formatted_tools
        
        # Pass through other parameters
        for key, value in kwargs.items():
            if key not in glm_data and value is not None:
                glm_data[key] = value
        
        return glm_data
    
    @staticmethod
    def _ensure_tools_format(tools: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Ensure tools have the correct format for GLM API.
        
        GLM expects: {"type": "function", "function": {...}}
        
        Args:
            tools: Tool definitions
        
        Returns:
            Formatted tools list
        """
        formatted_tools = []
        for tool in tools:
            if isinstance(tool, dict):
                formatted_tool = tool.copy()
                if "type" not in formatted_tool:
                    formatted_tool["type"] = "function"
                if formatted_tool.get("type") == "function" and "function" in formatted_tool:
                    func = formatted_tool["function"]
                    if isinstance(func, dict) and "name" in func:
                        formatted_tools.append(formatted_tool)
                elif "name" in formatted_tool:
                    # Convert flat format to nested format
                    formatted_tools.append({
                        "type": "function",
                        "function": formatted_tool
                    })
                else:
                    formatted_tools.append(formatted_tool)
        return formatted_tools
    
    @staticmethod
    def convert_glm_chunk_to_openai(glm_line: str) -> Optional[str]:
        """
        Convert GLM SSE chunk to OpenAI SSE format.
        
        GLM returns SSE in format: "data: {...}"
        May include reasoning_content field that needs to be merged with content.
        
        Args:
            glm_line: Single line from GLM SSE stream
        
        Returns:
            OpenAI-formatted SSE chunk or None if not a data line
        """
        try:
            chunk_str = glm_line.strip()
        except Exception:
            return None
        
        if not chunk_str:
            return None
        
        # Parse "data: {...}" format
        if chunk_str.startswith("data: "):
            data_str = chunk_str[6:].strip()
        else:
            data_str = chunk_str
        
        # Handle [DONE] marker
        if data_str == "[DONE]":
            return "data: [DONE]\n\n"
        
        # Parse JSON data
        try:
            data = json.loads(data_str)
        except json.JSONDecodeError:
            return None
        
        choices = data.get("choices", [])
        if not choices:
            return None
        
        delta = choices[0].get("delta", {})
        
        # Merge reasoning_content and content
        # GLM may return both fields, we combine them for OpenAI compatibility
        combined_content = ""
        if "reasoning_content" in delta and delta["reasoning_content"]:
            combined_content += delta["reasoning_content"]
        if "content" in delta and delta["content"]:
            combined_content += delta["content"]
        
        # Only output chunk if there's content, tool_calls, or finish_reason
        if combined_content or "tool_calls" in delta or choices[0].get("finish_reason"):
            openai_chunk = {
                "id": data.get("id", "chatcmpl-stream"),
                "object": "chat.completion.chunk",
                "created": data.get("created", int(time.time())),
                "model": data.get("model", ""),
                "choices": [{
                    "index": 0,
                    "delta": {},
                    "finish_reason": choices[0].get("finish_reason")
                }]
            }
            
            # Add combined content
            if combined_content:
                openai_chunk["choices"][0]["delta"]["content"] = combined_content
            
            # Add role if present (usually first chunk)
            if "role" in delta and not combined_content:
                openai_chunk["choices"][0]["delta"]["role"] = delta["role"]
            
            # Add tool_calls if present
            if "tool_calls" in delta:
                openai_chunk["choices"][0]["delta"]["tool_calls"] = delta["tool_calls"]
            
            # Add usage if present (usually last chunk)
            if "usage" in data:
                openai_chunk["usage"] = data["usage"]
            
            return f'data: {json.dumps(openai_chunk)}\n\n'
        
        return None


class GLMStreamConverter:
    """
    Stream converter for GLM API.
    
    Converts GLM SSE stream chunks to OpenAI format.
    This is a convenience wrapper around GLMConverter.convert_glm_chunk_to_openai.
    """
    
    @staticmethod
    def convert_stream_chunk(glm_chunk: bytes) -> Optional[str]:
        """
        Convert GLM stream chunk (bytes) to OpenAI SSE format.
        
        Args:
            glm_chunk: Raw bytes from GLM stream
        
        Returns:
            OpenAI-formatted SSE chunk or None
        """
        try:
            chunk_str = glm_chunk.decode("utf-8", errors="ignore").strip()
        except Exception:
            return None
        
        if not chunk_str:
            return None
        
        return GLMConverter.convert_glm_chunk_to_openai(chunk_str)
