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

# Golden Image URL (정상 제품 기준 이미지)
GOLDEN_IMAGE_URL = "https://cfiles.dacon.co.kr/competitions/236680_dev/DEV_003.png"

# Detailed Prompt Criteria (Granular for LLM Accuracy)
BASE_CRITERIA = """
상세 판단 가이드:
    1. 핀 체결 판단 (Category: pin):
        - 하단 중앙의 세개의 구멍에 모든 핀이 체결되어잇으면 False
        - [중요] 하나라도 빠져나가거나 누락된 핀이 있으면 True
    
    2. 패키지(Body) [파손] 판단 (Category: package_damage):
        - 본체 모서리가 깨져서 날아갔거나(Chipped)
        - 표면에 깊은 균열(Crack)이나 구멍이 뚫린 경우
        - (주의: 단순 회전이나 기울어짐은 여기에 해당하지 않음)

    3. 소자 [정렬] 판단 (Category: misalignment_severe):
        - [회전/Rotation]: 검은색 사각형이 반듯하지 않고, 시계/반시계 방향으로 5도 이상 비스듬하게 회전되어 있습니까?
        - [기울어짐/Tilt]: 본체의 모서리가 이미지 프레임과 평행하지 않고 삐뚤어져 있습니까?
        - [위치 이탈]: 소자가 중앙 정위치를 크게 벗어나 있습니까?
   
    4. 리드 [결손/단선] 판단 (Category: lead_missing_or_broken):
        - 핀이 절단(Broken)되어 있거나, 뿌리 부분만 남고 잘려 나간 경우.
        - 핀 자체가 아예 없는(Missing) 경우.
        - 정상적인 핀 개수(3개)보다 적은 경우.

    5. 리드 판단 (Category: lead_severe_bend_or_contact):
        - 핀끼리 서로 닿거나(Touching) 겹쳐 있는 경우.
        - 핀의 끝부분이 패드(구멍)의 정위치에서 벗어나(Off-pad) 있는 경우.
        
    6. 솔더 판단 (Category: solder_bridge_or_blob):
        - 핀 사이가 납(Solder)으로 이어져 있어 합선(Short)이 의심되는 경우.
        - 솔더가 뭉쳐서(Blob) 핀 사이를 메우고 있는 경우.
"""

OBS_ITEMS = [
  {"key": "package_damage", "desc": "패키지 파손/크랙"},
  {"key": "lead_missing_or_broken", "desc": "리드 결손/단선"},
  {"key": "lead_severe_bend_or_contact", "desc": "심한 휨/접촉"},
  {"key": "solder_bridge_or_blob", "desc": "솔더 브리지/뭉침"},
  {"key": "misalignment_severe", "desc": "패키지 위치 틀어짐"},
  {"key": "pin", "desc": "핀이 체결되지 않음"}
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

def crop_image_split_vertical(img):
    """
    Split image into:
    1. Top 70%: Focus on Body & Alignment
    2. Bottom 60% (from 40% height to bottom): Focus on Pins
    """
    h, w = img.shape[:2]
    split_top_end = int(h * 0.7)
    split_bottom_start = int(h * 0.4)
    
    img_top = img[0:split_top_end, :]       # Top region
    img_bottom = img[split_bottom_start:, :] # Bottom region
    
    return [
        (img_top, "top"), 
        (img_bottom, "bottom")
    ]

def encode_image(img):
    _, buffer = cv2.imencode('.jpg', img)
    return base64.b64encode(buffer).decode('utf-8')

def build_prompt_text(strict=False):
    criteria_text = "\n".join([f"- {item['key']}: {item['desc']}" for item in OBS_ITEMS])
    rule = "\n판단 기준:\n- 구조적 결함이 명확할 때만 true. 애매하면 false."
    return f"Image 1은 검사 대상 이미지입니다.\n이 이미지에 결함이 있는지 아래 항목별로 판단해 JSON으로 출력하세요.\n{criteria_text}\n{rule}\n{BASE_CRITERIA}"

def map_to_consolidated(details: dict) -> dict:
    """Map granular LLM keys to Simplified Frontend keys"""
    consolidated = {}
    
    # Mapping Rules
    pkg_keys = ["package_damage", "misalignment_severe"]
    
    # Check for Package Defects
    if any(details.get(k, False) for k in pkg_keys):
        consolidated["defect_package"] = True
        
    # Check for Pin Defects (Everything else)
    pin_found = False
    for k, v in details.items():
        if v and k not in pkg_keys:
            pin_found = True
            break
    if pin_found:
        consolidated["defect_pin"] = True
            
    return consolidated

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

    log(f"Processing {img_url} (Single Image Scan)...")

    # Download image (Single Download)
    try:
        target_img = download_image(img_url)
        if target_img is None:
            raise Exception("Failed to download image")
    except Exception as e:
        log(f"Image download failed: {e}")
        return {"label": 0, "confidence": 0.0, "logs": logs, "status": "error", "details": {}}

    # --- Step 1: Global Scan ---
    prompt_text_1 = build_prompt_text(strict=False)
    user_content_1 = [
        {"type": "text", "text": prompt_text_1 + "\n" + parser.get_format_instructions()},
        {"type": "image_url", "image_url": {"url": img_url}}
    ]
    
    try:
        resp_1 = llm.invoke([HumanMessage(content=user_content_1)])
        result_1 = parser.parse(resp_1)
        
        raw_details = result_1.get('details', {})
        detected = result_1.get('detected', False) or any(raw_details.values())
        confidence = result_1.get('confidence', 0.5)
        
        log(f"Step 1 Result: {detected} ({confidence})")

        # High confidence Defect -> Stop immediately
        if detected and confidence >= 0.6:
            log("Defect confirm (Global).")
            # Map granular details to consolidated keys for Frontend
            final_details = map_to_consolidated(raw_details)
            return {"label": 1, "confidence": confidence, "logs": logs, "status": "completed", "details": final_details}
    
    except Exception as e:
        log(f"Global scan failed: {e}")
        return {"label": 0, "confidence": 0.0, "logs": logs, "status": "error", "details": {}}
    
    # 2. Relaxed threshold for Clean (Global)
    if not detected and confidence >= 0.75:
        log("Clear normal (Global).")
        return {"label": 0, "confidence": confidence, "logs": logs, "status": "completed", "details": {}}

    # --- Step 2: Ambiguous -> Precision Scan (Vertical Split - Single Image) ---
    log("Ambiguous result. Starting Precision Scan (Vertical Split)...")
    
    try:
        # Note: Target image is already downloaded in target_img

        target_crops = crop_image_split_vertical(target_img)
        
        final_details = {} # Accumulate consolidated details
        detected_count = 0
        
        for i in range(2):
            t_crop, region = target_crops[i]
            
            t_b64 = encode_image(t_crop)
            
            # Select Prompt
            if region == "top":
                current_consolidated_key = "defect_package"
                region_prompt = """
                [Region: TOP (Body Alignment Analysis)]
                Image 1: 검사 대상 (Top Part)
                
                판단 기준 (One of below -> True):
                1. [회전/Rotation]: 검은색 본체가 프레임에 대해 5도 이상 비스듬하게 회전되어 있습니까?
                2. [기울어짐/Tilt]: 본체 모서리가 프레임과 평행하지 않고 삐뚤어져 있습니까?
                3. [파손/Breakage]: Body 표면에 명확한 크랙/깨짐이 있습니까?
                """
            else: # bottom
                current_consolidated_key = "defect_pin"
                region_prompt = """
                [Region: BOTTOM (Pins Comparison)]
                Image 1: 검사 대상 (Bottom Part)
                
                판단 기준 (One of below -> True):
                1. [누락/Missing]: 핀이 부러지거나(Broken) 아예 없습니까(Missing)?
                2. [쇼트/Short]: 핀끼리 서로 닿아 있거나(Touching) 납땜이 뭉쳐 있습니까(Solder Blob)?
                3. [이탈/Misplace]: 핀이 정위치(Pad 중앙)에서 벗어나 있습니까?
                """
            
            # Standard output format
            user_content_2 = [
                {"type": "text", "text": f"{region_prompt}\n정밀 분석하여 JSON으로 응답하세요 ({current_consolidated_key}: true/false).\n" + parser.get_format_instructions()},
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{t_b64}"}}  # Single Image
            ]
            
            resp_crop = llm.invoke([HumanMessage(content=user_content_2)])
            res_crop = parser.parse(resp_crop)
            
            crop_detected = res_crop.get('detected', False) or any(res_crop.get('details', {}).values())
            crop_conf = res_crop.get('confidence', 0)
            
            log(f"Region {region.upper()}: {crop_detected} ({crop_conf})")
            
            if crop_detected and crop_conf > 0.65:
                detected_count += 1
                final_details[current_consolidated_key] = True
                log(f"Defect found in {region.upper()}. Stopping further checks.")
                break # Optimize: Stop scanning if defect is already found

        final_label = 1 if detected_count > 0 else 0
        log(f"Final Decision: {final_label} (Defects in {detected_count}/2 regions)")
        
        return {"label": final_label, "confidence": 1.0 if final_label else 0.5, "logs": logs, "status": "completed", "details": final_details}

    except Exception as e:
        log(f"Precision scan failed: {e}")
        return {"label": 0, "confidence": 0.0, "logs": logs, "status": "error", "details": {}}

if __name__ == "__main__":
    run_agent_logic("https://cfiles.dacon.co.kr/competitions/236680_dev/DEV_000.png")
