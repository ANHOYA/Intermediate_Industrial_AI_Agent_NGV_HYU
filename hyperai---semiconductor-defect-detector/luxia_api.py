import os
import requests
import json
from dotenv import load_dotenv

# Load env variables
load_dotenv()

# Constants based on User's CURL command and Specs
BRIDGE_URL = "https://bridge.luxiacloud.com/llm/openai/chat/completions/gpt-4o-mini/create"
DEFAULT_MODEL = "gpt-4o-mini-2024-07-18"

def get_api_key():
    """Retrieves API KEY from env, fallback to hardcoded if needed (not recommended)."""
    api_key = os.getenv("API_KEY") or os.getenv("LUXIA_API_KEY")
    if not api_key:
        raise ValueError("API_KEY not found in environment variables.")
    return api_key

def chat_completion(messages, model=DEFAULT_MODEL, max_tokens=1024, temperature=0.7):
    """
    Executes a chat completion request to the Luxia API.
    
    Args:
        messages (list): List of message dicts (role, content).
        model (str): Model name.
        max_tokens (int): Max tokens to generate.
        temperature (float): Sampling temperature.
        
    Returns:
        str: The content of the assistant's response.
    """
    api_key = get_api_key()
    
    headers = {
        "apikey": api_key,
        "Content-Type": "application/json"
    }
    
    payload = {
        "model": model,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": temperature
    }
    
    try:
        response = requests.post(BRIDGE_URL, headers=headers, json=payload, timeout=60)
        
        if response.status_code != 200:
            error_msg = f"API Error {response.status_code}: {response.text}"
            raise RuntimeError(error_msg)
            
        data = response.json()
        
        if "choices" in data and len(data["choices"]) > 0:
            return data["choices"][0]["message"]["content"].strip()
        else:
            raise RuntimeError(f"Unexpected API response format: {data}")
            
    except Exception as e:
        raise RuntimeError(f"Luxia API Request Failed: {str(e)}")
