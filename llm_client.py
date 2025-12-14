#!/usr/bin/env python3
"""
General LLM client for local LM Studio instance.
Can be used throughout the pipeline for LLM interactions.
"""

import json
import urllib.request
import urllib.parse
import urllib.error
from typing import Dict, List, Optional


class LLMClient:
    """Client for interacting with local LLM (LM Studio)."""
    
    def __init__(self, base_url: str = "http://127.0.0.1:1234"):
        """
        Initialize LLM client.
        
        Args:
            base_url: Base URL of the LLM server (default: LM Studio local)
        """
        self.base_url = base_url.rstrip('/')
        self.chat_endpoint = f"{self.base_url}/v1/chat/completions"
        self.completion_endpoint = f"{self.base_url}/v1/completions"
    
    def chat(self, messages: List[Dict[str, str]], model: str = "local-model", 
             temperature: float = 0.7, max_tokens: int = 1000) -> str:
        """
        Send a chat completion request.
        
        Args:
            messages: List of message dicts with 'role' and 'content'
            model: Model name (default: "local-model")
            temperature: Sampling temperature
            max_tokens: Maximum tokens to generate
            
        Returns:
            Response text from the LLM
        """
        payload = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens
        }
        
        return self._make_request(self.chat_endpoint, payload)
    
    def complete(self, prompt: str, model: str = "local-model",
                 temperature: float = 0.7, max_tokens: int = 1000) -> str:
        """
        Send a simple text completion request.
        
        Args:
            prompt: The prompt text
            model: Model name
            temperature: Sampling temperature
            max_tokens: Maximum tokens to generate
            
        Returns:
            Response text from the LLM
        """
        payload = {
            "model": model,
            "prompt": prompt,
            "temperature": temperature,
            "max_tokens": max_tokens
        }
        
        return self._make_request(self.completion_endpoint, payload)
    
    def _make_request(self, url: str, payload: Dict) -> str:
        """
        Make HTTP request to LLM API.
        
        Args:
            url: API endpoint URL
            payload: Request payload
            
        Returns:
            Response text
        """
        # Try httpx first, then requests, then urllib
        try:
            import httpx
            with httpx.Client(timeout=60.0) as client:
                response = client.post(url, json=payload)
                if response.status_code == 200:
                    data = response.json()
                    return self._extract_response(data)
                else:
                    raise Exception(f"API returned status {response.status_code}: {response.text}")
        except ImportError:
            try:
                import requests
                response = requests.post(url, json=payload, timeout=60.0)
                if response.status_code == 200:
                    data = response.json()
                    return self._extract_response(data)
                else:
                    raise Exception(f"API returned status {response.status_code}: {response.text}")
            except ImportError:
                # Use built-in urllib
                req_data = json.dumps(payload).encode('utf-8')
                req = urllib.request.Request(
                    url,
                    data=req_data,
                    headers={'Content-Type': 'application/json'}
                )
                try:
                    with urllib.request.urlopen(req, timeout=60) as response:
                        data = json.loads(response.read().decode('utf-8'))
                        return self._extract_response(data)
                except urllib.error.HTTPError as e:
                    error_body = e.read().decode('utf-8')
                    raise Exception(f"API returned status {e.code}: {error_body}")
    
    def _extract_response(self, data: Dict) -> str:
        """
        Extract text response from API response data.
        
        Args:
            data: Response JSON data
            
        Returns:
            Extracted text
        """
        # Handle OpenAI-compatible format
        if "choices" in data:
            if isinstance(data["choices"], list) and len(data["choices"]) > 0:
                choice = data["choices"][0]
                if "message" in choice:
                    return choice["message"].get("content", "")
                elif "text" in choice:
                    return choice["text"]
        
        # Handle other formats
        if "text" in data:
            return data["text"]
        if "content" in data:
            return data["content"]
        if "response" in data:
            return data["response"]
        
        # Fallback: return string representation
        return str(data)


# Global client instance
_default_client: Optional[LLMClient] = None


def get_llm_client(base_url: str = "http://127.0.0.1:1234") -> LLMClient:
    """
    Get or create the default LLM client.
    
    Args:
        base_url: Base URL of the LLM server
        
    Returns:
        LLMClient instance
    """
    global _default_client
    if _default_client is None:
        _default_client = LLMClient(base_url)
    return _default_client


def chat(messages: List[Dict[str, str]], **kwargs) -> str:
    """
    Convenience function for chat completion.
    
    Args:
        messages: List of message dicts
        **kwargs: Additional arguments passed to chat()
        
    Returns:
        Response text
    """
    return get_llm_client().chat(messages, **kwargs)


def complete(prompt: str, **kwargs) -> str:
    """
    Convenience function for text completion.
    
    Args:
        prompt: The prompt text
        **kwargs: Additional arguments passed to complete()
        
    Returns:
        Response text
    """
    return get_llm_client().complete(prompt, **kwargs)
