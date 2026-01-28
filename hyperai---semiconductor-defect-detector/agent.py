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

# Golden Image URL (정상 제품 기준 이미지 - User Provided)
GOLDEN_IMAGE_URL = "https://cfiles.dacon.co.kr/competitions/236680_dev/DEV_000.png"

# --- OpenCV Pre-processing Helpers ---
def preprocess_image_for_diff(img):
    """
    Apply standard preprocessing for edge comparison:
    1. Grayscale
    2. Gaussian Blur (5x5)
    3. Canny Edge Detection
    4. Dilate (to connect broken edges)
    """
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)
    edges = cv2.Canny(blurred, 50, 150)
    kernel = np.ones((3,3), np.uint8)
    dilated = cv2.dilate(edges, kernel, iterations=1)
    return dilated

def compute_edge_difference(img1, img2):
    """
    Compute similarity score based on edge difference.
    Returns: pixel_diff_count (lower is more similar)
    """
    # Ensure same size
    if img1.shape != img2.shape:
        img2 = cv2.resize(img2, (img1.shape[1], img1.shape[0]))
        
    p1 = preprocess_image_for_diff(img1)
    p2 = preprocess_image_for_diff(img2)
    
    # Compute Absolute Difference
    diff = cv2.absdiff(p1, p2)
    
    # Threshold to ignore minor noise (optional, but good for stability)
    _, diff_thresh = cv2.threshold(diff, 127, 255, cv2.THRESH_BINARY)
    
    # Count different pixels
    non_zero = cv2.countNonZero(diff_thresh)
    return non_zero, diff_thresh # Return visual diff too if needed for debugging

# Detailed Prompt Criteria (Granular for LLM Accuracy)
BASE_CRITERIA = """
Verify if the undamaged transistor is correctly installed.
The transistor consists of a black package with 3 silver pins at the bottom.
Each of the 3 pins must be correctly inserted into one of the 3 holes at the bottom center.
The black package must be installed in the center without being skewed.
Return False if normal, True if defective.

Detailed Judgment Guide:
    Package Judgment [key: package_damage or misalignment_severe]:
        - True if the body edges are not parallel to the image frame and are skewed.
        - True if the device is significantly off-center.
        - True if the body corners are broken or chipped.
        - True if there are deep cracks or holes on the surface.
        - (Note: Simple rotation or slight tilt does not apply here unless severe)
   
    Pin Judgment [key: pin_missing_or_broken_or_short]:
        - True if pins are touching or overlapping each other.
        - True if the tips of the pins are off the correct position of the pads (holes).
        - True if a pin is broken or only the root remains.
        - True if a pin is completely missing.
        - True if there are fewer than the normal number of pins (3).
        - True if each pin does not connect from the transistor package to the hole.
"""

OBS_ITEMS = [
  {"key": "package_damage", "desc": "Package Damage/Crack"},
  {"key": "pin_missing_or_broken_or_short", "desc": "Pin Missing/Broken/Short"},
  {"key": "misalignment_severe", "desc": "Severe Misalignment"}
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
# --- Helper Functions for Pin Connectivity Check (Ported from roi_edges_only_single.py) ---
from dataclasses import dataclass
from typing import Iterable

@dataclass
class GridModel:
    col_centers: list[float]
    row_centers: list[float]
    pitch_x: float
    pitch_y: float
    bottom_row_y: float

def detect_holes(gray: np.ndarray) -> list[tuple[float, float]]:
    """Detect circular holes using adaptive threshold + connected components."""
    blur = cv2.GaussianBlur(gray, (5, 5), 0)
    thr = cv2.adaptiveThreshold(
        blur, 255, cv2.ADAPTIVE_THRESH_MEAN_C, cv2.THRESH_BINARY_INV, 31, 7
    )
    # Reduce thin vertical-line influence.
    hor_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (9, 3))
    thr = cv2.morphologyEx(thr, cv2.MORPH_OPEN, hor_kernel, iterations=1)

    num, labels, stats, centroids = cv2.connectedComponentsWithStats(thr, connectivity=8)
    holes: list[tuple[float, float]] = []
    for i in range(1, num):
        x, y, w, h, area = stats[i].tolist()
        if area < 120 or area > 2200:
            continue
        ratio = max(w, h) / max(1, min(w, h))
        if ratio > 1.6:
            continue
        cx, cy = centroids[i]
        holes.append((float(cx), float(cy)))
    return holes

def kmeans_1d(values: Iterable[float], k: int) -> list[float]:
    arr = np.array(list(values), dtype=np.float32).reshape(-1, 1)
    if len(arr) < k:
        # Fallback: unique sorted values.
        uniq = sorted(set(float(v) for v in arr.flatten().tolist()))
        return uniq
    criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 50, 0.1)
    _compactness, labels, centers = cv2.kmeans(
        arr, k, None, criteria, 8, cv2.KMEANS_PP_CENTERS
    )
    centers = [float(c[0]) for c in centers]
    centers.sort()
    return centers

def median_pitch(centers: list[float]) -> float:
    if len(centers) < 2:
        return 1.0
    diffs = np.diff(np.array(centers, dtype=np.float32))
    return float(np.median(diffs))

def build_grid_model(holes: list[tuple[float, float]]) -> GridModel:
    if not holes:
        raise RuntimeError("No holes detected; cannot build grid model.")

    xs = [p[0] for p in holes]
    ys = [p[1] for p in holes]

    # We observe roughly 5 columns and 4 rows in these images.
    col_centers = kmeans_1d(xs, k=5)
    row_centers = kmeans_1d(ys, k=4)

    pitch_x = median_pitch(col_centers)
    pitch_y = median_pitch(row_centers)

    bottom_row_y = max(row_centers) if row_centers else float(max(ys))
    return GridModel(
        col_centers=col_centers,
        row_centers=row_centers,
        pitch_x=pitch_x,
        pitch_y=pitch_y,
        bottom_row_y=bottom_row_y,
    )

def clamp_roi(x0: int, y0: int, x1: int, y1: int, w: int, h: int) -> tuple[int, int, int, int]:
    x0 = max(0, min(x0, w - 1))
    y0 = max(0, min(y0, h - 1))
    x1 = max(x0 + 1, min(x1, w))
    y1 = max(y0 + 1, min(y1, h))
    return x0, y0, x1, y1

def hole_roi_above(col_x: float, row_y: float, pitch_x: float, pitch_y: float, w: int, h: int) -> tuple[int, int, int, int]:
    """ROI just above a bottom-row hole (avoid the row above)."""
    half_w = int(round(0.60 * pitch_x))
    x0 = int(round(col_x)) - half_w
    x1 = int(round(col_x)) + half_w
    y1 = int(np.ceil(row_y + 0.12 * pitch_y))
    y0 = int(round(row_y - 0.60 * pitch_y))
    return clamp_roi(x0, y0, x1, y1, w=w, h=h)

def edges_in_roi(gray: np.ndarray, roi: tuple[int, int, int, int]) -> np.ndarray:
    x0, y0, x1, y1 = roi
    patch = gray[y0:y1, x0:x1]
    blur = cv2.GaussianBlur(patch, (5, 5), 0)
    edges = cv2.Canny(blur, 40, 120)
    return edges

# Output models
class PinResult(BaseModel):
    pin: int
    label: str = Field(description="OK or FAIL")
    reason: str 

class PinCheckOutput(BaseModel):
    results: list[PinResult]

pin_parser = JsonOutputParser(pydantic_object=PinCheckOutput)

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
    rule = "\nJudgment Criteria:\n- Compare Image 1 (Target) with Image 2 (Golden Reference).\n- Return True ONLY if there is a significant structural difference (Defect).\n- Return False if they look similar or if the difference is ambiguous."
    return f"Image 1 is the inspection target.\nImage 2 is the Golden Reference (Normal Product).\nCompare them and determine if there are defects in Image 1 based on the items below.\nOutput as JSON.\n{criteria_text}\n{rule}\n{BASE_CRITERIA}"

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

# Pin Check Logic
def run_pin_check(target_img, llm, log):
    try:
        gray = cv2.cvtColor(target_img, cv2.COLOR_BGR2GRAY)
        try:
            holes = detect_holes(gray)
            model = build_grid_model(holes)
        except Exception as e:
            log(f"Pin Logic Warning: Could not build grid model ({e}). Skipping Pin Check.")
            return None # Skip if detection fails

        h, w = gray.shape[:2]
        target_cols = (1, 2, 3) # Pins 1, 2, 3
        
        user_content_parts = []
        user_content_parts.append({"type": "text", "text": """
You are a Pin Connectivity Expert.
Image A: Zoomed Original (Brown background, Silver pin, Black hole)
Image B: Edge Map (Canny Edges)

Your job is to judge each pin separately (pin1, pin2, pin3).

Key rule:
The most important criterion is whether the silver pin is connected to its correct hole.
However, the judgment focuses on whether the TOP of the circular hole is connected,
even slightly, to the BOTTOM of the silver pin.
If the top of the pin looks broken/disconnected, you may ignore it.
The core is whether the hole top and the pin bottom meet.

For each pin:
1) Use Image A (zoomed original) to check:
   - The silver pin (and its shadow) connects naturally into the circular hole region.
   - If the pin is completely missing in Image A, mark FAIL.
2) Use Image B (edge map) for double-check:
   - If any edge from the pin touches the hole boundary (even one thin line), mark OK.
   - If the pin edge is not visible at all, mark FAIL.

If Image B is ambiguous, re-check Image A carefully and decide.

Return JSON in this format:
{
  "results": [
    { "pin": 1, "label": "OK|FAIL", "reason": "..." },
    { "pin": 2, "label": "OK|FAIL", "reason": "..." },
    { "pin": 3, "label": "OK|FAIL", "reason": "..." }
  ]
}
"""})

        for col_idx in target_cols:
            col_x = model.col_centers[col_idx]
            row_y = model.bottom_row_y
            roi = hole_roi_above(col_x, row_y, model.pitch_x, model.pitch_y, w=w, h=h)
            
            # Original ROI
            x0, y0, x1, y1 = roi
            roi_img = target_img[y0:y1, x0:x1]
            b64_orig = encode_image(roi_img)
            
            # Edge ROI
            edges = edges_in_roi(gray, roi)
            b64_edge = encode_image(edges)
            
            user_content_parts.append({"type": "text", "text": f"\n--- PIN {col_idx} ---\nImage A (Original) / Image B (Edge)"})
            user_content_parts.append({"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64_orig}"}})
            user_content_parts.append({"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64_edge}"}})

        user_content_parts.append({"type": "text", "text": "\nAnalyze all 3 pins and return JSON.\n" + pin_parser.get_format_instructions()})

    except Exception as e:
        log(f"Pin Check Failed: {e}")
        return None

    # Debug: Log the prompt part count
    log(f"Pin Check: Prepared {len(user_content_parts)} parts for LLM.")

    try:
        # Invoke LLM
        resp = llm.invoke([HumanMessage(content=user_content_parts)])
        log(f"Pin Check LLM Response: {resp.content}") # Debug Log
        result = pin_parser.parse(resp)
        return result
        
    except Exception as e:
        log(f"Pin Check LLM/Parse Failed: {e}")
        return None

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
            raise Exception("Failed to download target image")
            
        golden_img = download_image(GOLDEN_IMAGE_URL)
        if golden_img is None:
             raise Exception("Failed to download golden image")

    except Exception as e:
        log(f"Image download failed: {e}")
        return {"label": 0, "confidence": 0.0, "logs": logs, "status": "error", "details": {}}

    # --- Step 0: OpenCV Edge Density Check (Structural Anomaly) ---
    try:
        # Instead of absdiff (sensitive to alignment), use Edge Density Ratio
        golden_edges = preprocess_image_for_diff(golden_img)
        target_edges = preprocess_image_for_diff(target_img)
        
        g_count = cv2.countNonZero(golden_edges)
        t_count = cv2.countNonZero(target_edges)
        
        # Avoid division by zero
        if g_count == 0: g_count = 1
        
        ratio = t_count / g_count
        log(f"Step 0 (freq): Golden={g_count}, Target={t_count}, Ratio={ratio:.2f}")
        
        # Threshold:
        # If Ratio < 0.5: Likely Missing Component (Transistor body missing -> less edges)
        # If Ratio > 1.5: Likely Severe Noise/Shattered (Too many edges)
        if ratio < 0.5:
             log(f"Step 0: Edge Density Too Low ({ratio:.2f}). Missing Component likely.")
             return {
                "label": 1, 
                "confidence": 0.95, 
                "logs": logs, 
                "status": "completed", 
                "details": {"defect_package": True, "reason": "Severe Structural Missing"}
            }
        elif ratio > 1.5:
             log(f"Step 0: Edge Density Too High ({ratio:.2f}). Structural Damage likely.")
             return {
                "label": 1, 
                "confidence": 0.95, 
                "logs": logs, 
                "status": "completed", 
                "details": {"defect_package": True, "reason": "Severe Structural Damage"}
             }
            
    except Exception as e:
        log(f"Step 0 Failed: {e}. Proceeding to LLM.")

    # --- Step 1: Global Scan (Golden Comparison) ---
    prompt_text_1 = build_prompt_text(strict=False)
    
    # Enable Golden Image Comparison
    t_b64 = encode_image(target_img)
    g_b64 = encode_image(golden_img)
    
    user_content_1 = [
        {"type": "text", "text": prompt_text_1 + "\n" + parser.get_format_instructions()},
        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{t_b64}"}},   # Image 1 (Target)
        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{g_b64}"}}    # Image 2 (Golden)
    ]
    
    try:
        resp_1 = llm.invoke([HumanMessage(content=user_content_1)])
        result_1 = parser.parse(resp_1)
        
        raw_details = result_1.get('details', {})
        detected = result_1.get('detected', False) or any(raw_details.values())
        confidence = result_1.get('confidence', 0.5)
        
        log(f"Step 1 Result: {detected} ({confidence})")

        # High confidence Defect -> Stop immediately
        if detected and confidence >= 0.85:
            log("Defect confirm (Global).")
            # Map granular details to consolidated keys for Frontend
            final_details = map_to_consolidated(raw_details)
            return {"label": 1, "confidence": confidence, "logs": logs, "status": "completed", "details": final_details}
    
    except Exception as e:
        log(f"Global scan failed: {e}")
        return {"label": 0, "confidence": 0.0, "logs": logs, "status": "error", "details": {}}
    
    # 2. Relaxed threshold for Clean (Global)
    # Lowering slightly to 0.90 to avoid aggressive Step 2 for clearly good images.
    if not detected and confidence >= 0.90:
        log("Clear normal (Global).")
        return {"label": 0, "confidence": confidence, "logs": logs, "status": "completed", "details": {}}

    # --- Step 1.5: Pin Connectivity Check (Edge Detection) ---
    log("Ambiguous Global -> Starting Step 1.5: Pin Connectivity Check (Edge+ROI)...")
    pin_check_res = run_pin_check(target_img, llm, log)
    
    if pin_check_res:
        pin_defects = []
        for p in pin_check_res.get("results", []):
            if p.get("label") == "FAIL":
                pin_defects.append(p)
        
        if pin_defects:
            log(f"Pin Check Found Defects: {pin_defects}")
            return {
                "label": 1, 
                "confidence": 0.95, 
                "logs": logs, 
                "status": "completed", 
                "details": {"defect_pin": True} 
            }
        else:
            log("Pin Check Passed (All OK). Proceeding to Step 2.")

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
                [Region: TOP (Package Alignment Analysis)]
                Image 1: Inspection Target (Top Part)
                
                Judgment Criteria (One of below -> True):
                1. [Rotation]: Is the black body rotated more than 5 degrees relative to the frame?
                2. [Tilt]: Is the body edge not parallel to the frame and skewed?
                3. [Breakage]: Is there clear cracking/breakage on the package surface?
                """
            else: # bottom
                current_consolidated_key = "defect_pin"
                region_prompt = """
                - True if pins are touching or overlapping each other.
                - True if the tips of the pins are off the correct position of the pads (holes).
                - True if a pin is broken or only the root remains.
                - True if a pin is completely missing.
                - True if there are fewer than the normal number of pins (3).
                - True if 3 pins are not installed one by one in the 3 bottom center holes.
            """
            # Standard output format
            user_content_2 = [
                {"type": "text", "text": f"{region_prompt}\nAnalyze precisely and respond in JSON ({current_consolidated_key}: true/false).\n" + parser.get_format_instructions()},
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
                # 여기 효율성 올릴려고 추가한 부분 / 다 돌리고 싶으면 냅두면 됨
                # log(f"Defect found in {region.upper()}. Stopping further checks.")
                # break # Optimize: Stop scanning if defect is already found

        final_label = 1 if detected_count > 0 else 0
        log(f"Final Decision: {final_label} (Defects in {detected_count}/2 regions)")
        
        return {"label": final_label, "confidence": 1.0 if final_label else 0.5, "logs": logs, "status": "completed", "details": final_details}

    except Exception as e:
        log(f"Precision scan failed: {e}")
        return {"label": 0, "confidence": 0.0, "logs": logs, "status": "error", "details": {}}

if __name__ == "__main__":
    run_agent_logic("https://cfiles.dacon.co.kr/competitions/236680_dev/DEV_000.png")
