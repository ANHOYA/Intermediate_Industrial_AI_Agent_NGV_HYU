import os
import cv2
import json
import base64
import time
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
API_KEY = os.getenv("API_KEY", "").strip("'").strip('"')
MODEL_NAME = "gpt-4o-mini-2024-07-18"
BRIDGE_ENDPOINT = "https://bridge.luxiacloud.com/llm/openai/chat/completions/gpt-4o-mini/create" 

# Detailed Prompt Criteria (Synced from Frontend)
BASE_CRITERIA = """
상세 판단 가이드:
1. 핀이 확실하게 빠져있거나 절단 되거나 파손 된 경우에 해당 항목을 True로 설정한다.
2. 트랜지스터가 반듯하게 놓이지 않고 삐뚫은 경우, 파손 된 경우에는 해당 항목을 True로 설정한다.
"""

OBS_ITEMS = [
  {"key": "package_damage", "desc": "크랙/파손/깨짐 등 패키지 손상"},
  {"key": "lead_missing_or_broken", "desc": "리드 결손/단선"},
  {"key": "lead_severe_bend_or_contact", "desc": "심한 휨 또는 리드끼리 접촉"},
  {"key": "solder_bridge_or_blob", "desc": "솔더 브리지 또는 납땜 뭉침"},
  {"key": "misalignment_severe", "desc": "소자 위치가 과도하게 틀어짐"},
]

# Robust LLM Wrapper with Retry
class LuxiaLLM:
    def __init__(self):
        self.url = BRIDGE_ENDPOINT
        self.headers = {
            "apikey": API_KEY,
            "Content-Type": "application/json"
        }
    
    def invoke(self, inputs):
        max_retries = 5
        attempt = 0
        
        # Prepare messages
        messages = []
        if isinstance(inputs, list):
            for msg in inputs:
                if isinstance(msg, HumanMessage):
                    messages.append({"role": "user", "content": msg.content})
                elif hasattr(msg, 'type') and msg.type == 'system':
                    messages.append({"role": "system", "content": msg.content})

        payload = {
            "model": MODEL_NAME,
            "messages": messages,
            "stream": False
        }

        while attempt < max_retries:
            try:
                resp = requests.post(self.url, headers=self.headers, json=payload, timeout=30)
                
                if resp.status_code >= 500 or resp.status_code in [400, 429]:
                     print(f"API Warning: {resp.status_code} - {resp.text}. Retrying...")
                     raise Exception(f"Transient Error {resp.status_code}")
                
                resp.raise_for_status()
                resp_json = resp.json()
                return resp_json['choices'][0]['message']['content']
                
            except Exception as e:
                attempt += 1
                wait_time = 2 ** attempt
                print(f"Attempt {attempt} failed: {e}. Waiting {wait_time}s...")
                time.sleep(wait_time)
                if attempt >= max_retries:
                    raise e

# Helper Functions
def download_image(url):
    resp = requests.get(url, timeout=10)
    arr = np.asarray(bytearray(resp.content), dtype=np.uint8)
    return cv2.imdecode(arr, -1)

def crop_image_4(img):
    h, w = img.shape[:2]
    cx, cy = w // 2, h // 2
    return [img[0:cy, 0:cx], img[0:cy, cx:w], img[cy:h, 0:cx], img[cy:h, cx:w]]

def encode_image(img):
    _, buffer = cv2.imencode('.jpg', img)
    return base64.b64encode(buffer).decode('utf-8')

def build_prompt_text(strict=False):
    criteria_text = "\n".join([f"- {item['key']}: {item['desc']}" for item in OBS_ITEMS])
    rule = "\n판단 기준:\n- 매우 보수적으로 판단한다. 애매하면 무조건 false." if strict else "\n판단 기준:\n- 아주 명확할 때만 true. 애매하면 false."
    return f"아래 항목을 이미지에서 관찰해 true/false로 채워 JSON만 출력해.\n{criteria_text}\n{rule}\n{BASE_CRITERIA}"

# Output Model
class DefectOutput(BaseModel):
    detected: bool = Field(description="Total defect detected or not")
    confidence: float
    details: dict = Field(default={}, description="Detailed observation results")

parser = JsonOutputParser(pydantic_object=DefectOutput)

# Main Agent Logic
def run_agent_logic(img_url):
    llm = LuxiaLLM()
    logs = []
    
    def log(msg):
        print(msg)
        logs.append(msg)

    log(f"Processing {img_url}...")

    # --- Step 1: Global Scan ---
    prompt_text_1 = build_prompt_text(strict=False)
    user_content_1 = [
        {"type": "text", "text": prompt_text_1 + "\n" + parser.get_format_instructions()},
        {"type": "image_url", "image_url": {"url": img_url}}
    ]
    
    try:
        resp_1 = llm.invoke([HumanMessage(content=user_content_1)])
        result_1 = parser.parse(resp_1)
    except Exception as e:
        log(f"Global scan failed: {e}")
        return {"label": 0, "confidence": 0.0, "logs": logs, "status": "error"}

    log(f"Step 1 Result: {result_1}")

    # Check for direct pass/fail
    detected = result_1.get('detected', False) or any(result_1.get('details', {}).values())
    confidence = result_1.get('confidence', 0.5)

    # 1. High confidence Defect (Global)
    if detected and confidence > 0.8:
        log("Defect confirm (Global).")
        return {"label": 1, "confidence": confidence, "logs": logs, "status": "completed"}
    
    # 2. Relaxed threshold for Clean (Global)
    # Lowered from 0.9 to 0.75 to reduce unnecessary precision scans
    if not detected and confidence >= 0.75:
        log("Clear normal (Global).")
        return {"label": 0, "confidence": confidence, "logs": logs, "status": "completed"}

    # --- Step 2: Ambiguous -> Precision Scan ---
    log("Ambiguous result. Starting Precision Scan (Cropping)...")
    
    try:
        img = download_image(img_url)
        crops = crop_image_4(img)
        detected_count = 0
        
        prompt_text_2 = build_prompt_text(strict=True) # Stricter prompt
        
        for i, crop in enumerate(crops):
            b64_img = encode_image(crop)
            img_data_url = f"data:image/jpeg;base64,{b64_img}"
            
            user_content_2 = [
                {"type": "text", "text": f"Evaluate this CROP {i+1}/4 closely.\n{prompt_text_2}\n" + parser.get_format_instructions()},
                {"type": "image_url", "image_url": {"url": img_data_url}}
            ]
            
            resp_crop = llm.invoke([HumanMessage(content=user_content_2)])
            res_crop = parser.parse(resp_crop)
            
            # Stricter filter for crops: must be detected AND have decent confidence
            crop_detected = res_crop.get('detected', False) or any(res_crop.get('details', {}).values())
            crop_conf = res_crop.get('confidence', 0)
            
            log(f"Crop {i}: {crop_detected} ({crop_conf})")
            
            # Fix: Ignore low confidence defects in precision mode (hallucination filter)
            if crop_detected and crop_conf > 0.7:
                detected_count += 1


        final_label = 1 if detected_count > 0 else 0
        log(f"Final Decision: {final_label} (Defects in {detected_count}/4 crops)")
        
        return {"label": final_label, "confidence": 1.0 if final_label else 0.5, "logs": logs, "status": "completed"}

    except Exception as e:
        log(f"Precision scan failed: {e}")
        return {"label": 0, "confidence": 0.0, "logs": logs, "status": "error"}

if __name__ == "__main__":
    run_agent_logic("https://cfiles.dacon.co.kr/competitions/236680_dev/DEV_000.png")
