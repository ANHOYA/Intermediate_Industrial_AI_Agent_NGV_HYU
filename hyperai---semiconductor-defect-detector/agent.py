import os
import cv2
import json
import base64
import numpy as np
import requests
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import JsonOutputParser
from langchain_core.runnables import RunnableLambda
from langchain_core.messages import HumanMessage
from pydantic import BaseModel, Field

# Load environment variables
load_dotenv()

# Configuration
BRIDGE_URL = "https://bridge.luxiacloud.com/llm/openai/" # LangChain appends chat/completions usually, but ChatOpenAI base_url handling can be tricky.
# ChatOpenAI with custom base_url often needs the full path or root. 
# Saltlux Bridge URL for gpt-4o-mini is specific: .../chat/completions/gpt-4o-mini/create
# We might need to subclass or configure carefully. 
# Actually, the user's `luxia_api.py` used `requests`. 
# Let's try to set `base_url` to the bridge root and see if `model` param maps correctly.
# The user's bridge URL in `constants.ts` was `.../gpt-4o-mini/create`.
# This is a non-standard OpenAI endpoint structure. 
# Standard is `/v1/chat/completions`.
# If the bridge expects exactly `.../create`, standard ChatOpenAI might fail.
# We might need to override the `openai_api_base` and `model_name`.

API_KEY = os.getenv("API_KEY", "").strip("'").strip('"')
MODEL_NAME = "gpt-4o-mini-2024-07-18"
BRIDGE_ENDPOINT = "https://bridge.luxiacloud.com/llm/openai/chat/completions/gpt-4o-mini/create" 

# Since the endpoint is non-standard (ends with /create), we might need to use a generic HTTP wrapper or configure OpenAI client carefully.
# However, `langchain_openai` allows passing a custom `openai_api_base`. 
# But usually it appends `/chat/completions`.
# Let's assume for now we can wrap the existing logic or use a custom Runnable for the LLM call if ChatOpenAI fails.
# Actually, looking at `luxia_api.py`, it does a POST to the exact URL.
# Let's try to use standard ChatOpenAI with `base_url` set to the parent of `chat/completions`? 
# No, the URL path is `.../gpt-4o-mini/create`. 
# Let's define a Custom Runnable for Luxia if needed, but first let's see if we can trick ChatOpenAI.
# Better yet, let's just make a custom Runnable wrapper around the working `requests` call to ensure compatibility.

class LuxiaLLM:
    def __init__(self):
        self.url = BRIDGE_ENDPOINT
        self.headers = {
            "apikey": API_KEY,
            "Content-Type": "application/json"
        }
    
    def invoke(self, inputs):
        # input is usually a list of messages or a prompt string
        # We expect inputs to be formatted messages
        messages = []
        if isinstance(inputs, list):
            for msg in inputs:
                if isinstance(msg, HumanMessage):
                    content = msg.content
                    # Handle image content blocks if they exist
                    # LangChain message content can be a list for multimodal
                    messages.append({"role": "user", "content": content})
                elif hasattr(msg, 'type') and msg.type == 'system':
                    messages.append({"role": "system", "content": msg.content})
                # ... handle other types
        
        payload = {
            "model": MODEL_NAME,
            "messages": messages,
            "stream": False
        }
        
        resp = requests.post(self.url, headers=self.headers, json=payload)
        resp_json = resp.json()
        
        try:
            content = resp_json['choices'][0]['message']['content']
            return content
        except KeyError:
            raise Exception(f"Luxia API Error: {resp.text}")

# Helper: Download Image
def download_image(url):
    resp = requests.get(url)
    arr = np.asarray(bytearray(resp.content), dtype=np.uint8)
    return cv2.imdecode(arr, -1)

# Helper: Crop Image (4 quadrants)
def crop_image_4(img):
    h, w = img.shape[:2]
    cx, cy = w // 2, h // 2
    tl = img[0:cy, 0:cx]
    tr = img[0:cy, cx:w]
    bl = img[cy:h, 0:cx]
    br = img[cy:h, cx:w]
    return [tl, tr, bl, br]

# Helper: Encode Image to Base64 for API
def encode_image(img):
    _, buffer = cv2.imencode('.jpg', img)
    return base64.b64encode(buffer).decode('utf-8')

# Output Model
class DefectOutput(BaseModel):
    detected: bool = Field(description="Whether a defect is detected")
    confidence: float = Field(description="Confidence score between 0.0 and 1.0")
    description: str = Field(description="Brief description of the defect or image")

parser = JsonOutputParser(pydantic_object=DefectOutput)

# Core Logic
def run_agent(img_url):
    llm = LuxiaLLM()
    
    # --- Step 1: Global Scan ---
    print(f"Processing {img_url}...")
    
    # Prompt for Global Scan
    # We construct the message payload manually for our custom wrapper
    # In a real LangChain integration we'd use PromptTemplate.format_messages
    
    global_system = """You are a semiconductor QC expert.
    Analyze the image for ANY defects (scratches, particles, discoloration).
    Be conservative: if ensuring, say detected=true.
    Output JSON only."""
    
    user_content = [
        {"type": "text", "text": "Analyze this image.\n" + parser.get_format_instructions()},
        {"type": "image_url", "image_url": {"url": img_url}}
    ]
    
    # We need to bridge LangChain's message format to our custom LLM's expected JSON format
    # Or just simplify for this Proof of Concept
    
    # Let's use the custom invoke directly for now
    resp_str = llm.invoke([
        HumanMessage(content=user_content) # Wait, our custom wrapper expects LangChain messages or dicts?
        # Let's adjust wrapper above to handle dicts in content list for multimodal
    ])
    
    try:
        result_phase1 = parser.parse(resp_str)
    except:
        # Fallback parsing
        import json
        result_phase1 = json.loads(resp_str.replace("```json", "").replace("```", ""))

    print(f"Phase 1 Result: {result_phase1}")

    # --- Step 2: Router ---
    if result_phase1['detected'] and result_phase1['confidence'] > 0.9:
        print("Defect confirmed with high confidence. Finalizing.")
        return 1
    
    if not result_phase1['detected'] and result_phase1['confidence'] > 0.9:
        print("Clean image confirmed. Finalizing.")
        return 0
        
    # If ambiguous, proceed to Step 3
    print("Ambiguous result. Starting Precision Scan (Cropping)...")
    
    # --- Step 3: Precision Scan ---
    img = download_image(img_url)
    crops = crop_image_4(img)
    
    detected_count = 0
    for i, crop in enumerate(crops):
        b64_img = encode_image(crop)
        img_data_url = f"data:image/jpeg;base64,{b64_img}"
        
        # Reuse same prompt or stricter one?
        # PDF says "Stricter prompt"
        strict_content = [
            {"type": "text", "text": "This is a magnified crop of a semiconductor. Look very closely for defects.\n" + parser.get_format_instructions()},
            {"type": "image_url", "image_url": {"url": img_data_url}}
        ]
        
        resp_crop = llm.invoke([HumanMessage(content=strict_content)])
        try:
            res_crop = parser.parse(resp_crop)
        except:
            res_crop = {"detected": False} # Fail safe
            
        print(f"  Crop {i}: {res_crop['detected']}")
        if res_crop['detected']:
            detected_count += 1

    final_decision = 1 if detected_count > 0 else 0
    print(f"Phase 3 Result: {final_decision} (Defects found in {detected_count} crops)")
    
    return final_decision

if __name__ == "__main__":
    # Test with a known URL
    test_url = "https://cfiles.dacon.co.kr/competitions/236680_dev/DEV_000.png"
    run_agent(test_url)
