#!/usr/bin/env python3
"""
General LLM client for Tzafon API.
Can be used throughout the pipeline for LLM interactions.
"""

import os
from typing import Dict, List, Optional
from dotenv import load_dotenv
from openai import OpenAI

# Load environment variables
load_dotenv()


class LLMClient:
    """Client for interacting with Tzafon API."""
    
    def __init__(self, api_key: Optional[str] = None, base_url: str = "https://api.tzafon.ai/v1", 
                 model: str = "tzafon.northstar.cua.sft"):
        """
        Initialize LLM client.
        
        Args:
            api_key: Tzafon API key (default: from TZAFON_API_KEY env var)
            base_url: Base URL of the API (default: Tzafon API)
            model: Model name to use (default: tzafon.northstar.cua.sft)
        """
        self.api_key = api_key or os.getenv("TZAFON_API_KEY")
        if not self.api_key:
            raise ValueError("TZAFON_API_KEY not found in environment variables")
        
        self.base_url = base_url
        self.model = model
        self.client = OpenAI(
            api_key=self.api_key,
            base_url=self.base_url
        )
    
    def chat(self, messages: List[Dict[str, str]], model: Optional[str] = None, 
             temperature: float = 0.7, max_tokens: int = 1000, response_format: Optional[Dict] = None) -> str:
        """
        Send a chat completion request.
        
        Args:
            messages: List of message dicts with 'role' and 'content'
            model: Model name (default: uses instance default)
            temperature: Sampling temperature
            max_tokens: Maximum tokens to generate
            response_format: Optional response format (for structured output)
            
        Returns:
            Response text from the LLM
        """
        model = model or self.model
        
        try:
            kwargs = {
                "model": model,
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_tokens
            }
            
            # Add response_format if provided (for structured output/JSON schema)
            if response_format:
                kwargs["response_format"] = response_format
            
            response = self.client.chat.completions.create(**kwargs)
            return response.choices[0].message.content
        except Exception as e:
            raise Exception(f"Tzafon API error: {str(e)}")
    
    def complete(self, prompt: str, model: Optional[str] = None,
                 temperature: float = 0.7, max_tokens: int = 1000) -> str:
        """
        Send a simple text completion request (converted to chat format).
        
        Args:
            prompt: The prompt text
            model: Model name (default: uses instance default)
            temperature: Sampling temperature
            max_tokens: Maximum tokens to generate
            
        Returns:
            Response text from the LLM
        """
        # Convert to chat format
        messages = [{"role": "user", "content": prompt}]
        return self.chat(messages, model=model, temperature=temperature, max_tokens=max_tokens)


# Global client instance
_default_client: Optional[LLMClient] = None


def get_llm_client(api_key: Optional[str] = None, base_url: str = "https://api.tzafon.ai/v1",
                   model: str = "tzafon.northstar.cua.sft") -> LLMClient:
    """
    Get or create the default LLM client.
    
    Args:
        api_key: Tzafon API key (default: from TZAFON_API_KEY env var)
        base_url: Base URL of the API (default: Tzafon API)
        model: Model name to use (default: tzafon.northstar.cua.sft)
        
    Returns:
        LLMClient instance
    """
    global _default_client
    if _default_client is None:
        _default_client = LLMClient(api_key=api_key, base_url=base_url, model=model)
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
