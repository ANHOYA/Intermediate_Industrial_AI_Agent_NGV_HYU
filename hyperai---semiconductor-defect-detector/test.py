import re
import json
import time
import random
import requests
import pandas as pd

# =========================
# 설정
# =========================
# 참가자 안내:
# - 아래 API_KEY / BRIDGE_URL / MODEL은 솔트룩스 "LLM API 호출 설정" 문법을 따릅니다.
# - (1) 이미지 관찰(LLM) -> (2) 규칙 기반 판단 -> (3) 애매하면 1회 재검토의 아주 기초적인 AI Agent 구조를 보여주는 예시입니다.
import luxia_api
from luxia_api import chat_completion

# 입력(test.csv) / 출력(submission.csv) 경로
TEST_CSV_PATH = "./dev.csv" # 1일차 예시 샘플 데이터 20장
OUT_PATH = "./submission.csv"

# 대회 라벨 정의: 0=정상, 1=비정상
LABEL_NORMAL = 0
LABEL_ABNORMAL = 1

# =========================
# 관찰 항목
# =========================
# 참가자 안내:
# - "관찰할 결함 항목"을 정의하는 곳입니다.
# - (항목_key, 항목_설명) 형태로 되어 있어, 여기에 줄만 추가/삭제하면
#   프롬프트와 파싱 키(KEYS)가 자동으로 맞춰집니다.
OBS_ITEMS = [
    ("package_damage", "크랙/파손/깨짐 등 패키지 손상"),
    ("lead_missing_or_broken", "리드 결손/단선"),
    ("lead_severe_bend_or_contact", "심한 휨 또는 리드끼리 접촉"),
    ("solder_bridge_or_blob", "솔더 브리지 또는 납땜 뭉침"),
    ("misalignment_severe", "소자 위치가 과도하게 틀어짐"),
]

# OBS_ITEMS에서 key만 뽑아, 결과 JSON에서 가져올 항목 목록으로 사용합니다.
KEYS = [k for k, _ in OBS_ITEMS]

# =========================
# 시스템 프롬프트
# =========================
# 참가자 안내:
# - SYSTEM은 "모델의 역할/출력 규칙"을 고정하는 부분입니다.
# - JSON만 출력하도록 강제하여, 파싱 오류를 줄이려는 목적입니다.
SYSTEM = (
    "너는 반도체 소자 검사 이미지 분석기다.\n"
    "반드시 요청한 JSON만 출력한다. 다른 텍스트는 절대 출력하지 않는다.\n"
)

# =========================
# build_prompt(strict)
# =========================
# 역할:
# - OBS_ITEMS 기반으로 "관찰 프롬프트"를 자동 생성합니다.
# - strict=False: 일반 관찰(너무 애매하면 false)
# - strict=True : 더 보수적인 관찰(애매하면 무조건 false)
#
# 참가자 확장 포인트:
# - OBS_ITEMS를 바꾸면 프롬프트도 자동으로 바뀝니다.
# - strict 모드의 rule 문구를 바꾸면 "재검토 정책"을 쉽게 튜닝할 수 있습니다.
def build_prompt(strict: bool = False) -> str:
    header = (
        "아래 항목을 이미지에서 관찰해 true/false로 채워 JSON만 출력해.\n"
        "형식은 반드시 아래와 동일해야 한다.\n"
    )

    # JSON 템플릿을 자동 생성합니다.
    # 예) { "package_damage": false, ... }
    json_template = "{\n" + ",\n".join([f'  "{k}": false' for k, _ in OBS_ITEMS]) + "\n}"

    # strict 여부에 따라 판단 기준 문구만 다르게 줍니다.
    if strict:
        rule = "\n판단 기준:\n- 매우 보수적으로 판단한다. 애매하면 무조건 false.\n"
    else:
        rule = "\n판단 기준:\n- 아주 명확할 때만 true. 애매하면 false.\n"

    # 각 항목에 대한 간단한 설명을 붙입니다.
    criteria = "\n".join([f"- {k}: {desc}" for k, desc in OBS_ITEMS])

    return header + json_template + rule + criteria

# 일반 관찰 프롬프트 / 보수적 관찰 프롬프트를 미리 만들어둡니다.
PROMPT_NORMAL = build_prompt(strict=False)
PROMPT_STRICT = build_prompt(strict=True)

# =========================
# _post_chat(messages) -> Replaced by luxia_api.chat_completion
# =========================
def _post_chat(messages, timeout=90):
    # Wrapper to maintain compatibility with existing calls if needed, 
    # but we will just call chat_completion direct in observe() or map it here.
    return chat_completion(messages)

# =========================
# _safe_json_extract(s)
# =========================
# 역할:
# - LLM이 JSON만 출력하도록 요청했지만, 간혹 설명 문장이 섞일 수 있습니다.
# - 1차: json.loads로 바로 파싱 시도
# - 실패하면: 문자열에서 {...} 구간만 정규식으로 찾아 파싱 시도
#
# 참가자 확장 포인트:
# - 출력이 자주 깨진다면, 이 부분을 더 강하게 보정할 수 있습니다.
def _safe_json_extract(s: str) -> dict:
    try:
        return json.loads(s)
    except Exception:
        m = re.search(r"\{.*\}", s, flags=re.S)
        if m:
            return json.loads(m.group(0))
    raise ValueError(f"JSON parse failed: {s[:200]}")

# =========================
# observe(img_url, strict)
# =========================
# Agent Step 1: Observe (관찰 단계)
#
# 역할:
# - 이미지 URL을 LLM에 전달하여, OBS_ITEMS에 정의된 결함 항목을 true/false로 관찰하게 합니다.
# - strict=False: 1차 관찰
# - strict=True : 애매하면 false로 보는 "재검토 관찰"
#
# 참가자 확장 포인트:
# - 관찰 항목을 더 추가하거나(예: surface_defect 등)
# - 프롬프트 문구를 더 구체화할 수 있습니다.
def observe(img_url: str, strict: bool = False) -> dict:
    prompt = PROMPT_STRICT if strict else PROMPT_NORMAL

    content = _post_chat([
        {"role": "system", "content": SYSTEM},
        {"role": "user", "content": [
            {"type": "text", "text": prompt},
            {"type": "image_url", "image_url": {"url": img_url}},
        ]},
    ])

    obs = _safe_json_extract(content)

    # 키 누락 대비:
    # - 어떤 키가 빠져도 기본값 false로 채워서 안정적으로 처리합니다.
    return {k: bool(obs.get(k, False)) for k in KEYS}

# =========================
# decide(obs)
# =========================
# Agent Step 2: Decide (판단 단계)
#
# 역할:
# - 관찰 결과(obs)에서 true 개수를 세고,
#   "하나라도 결함이면 비정상(1)"이라는 가장 단순한 규칙으로 라벨을 결정합니다.
#
# uncertain(재검토 대상) 정책:
# - 결함이 0개: 혹시 놓쳤을 수 있으니 재검토
# - 결함이 1개: 경계 케이스일 수 있으니 재검토
#
# 참가자 확장 포인트:
# - uncertain 조건을 바꾸면 호출 횟수/정확도 트레이드오프를 조정할 수 있습니다.
#   예) defect_count==0일 때만 재검토(더 빠름)
#   예) defect_count<=2일 때 재검토(더 보수적)
def decide(obs: dict):
    defect_count = sum(1 for v in obs.values() if v)
    label = LABEL_ABNORMAL if defect_count >= 1 else LABEL_NORMAL

    # 베이스라인용 "간단 재검토" 조건
    uncertain = (defect_count == 0) or (defect_count == 1)
    return label, uncertain

# =========================
# classify_agent(img_url)
# =========================
# Agent Step 3: Review (재검토 단계 포함)
#
# 역할:
# - 1차 관찰 -> decide
# - 애매하면(strict=True)로 1회 재검토 관찰 -> decide
# - 재검토에서 비정상으로 잡히면 비정상 확정
# - 그렇지 않으면 1차 결과를 유지합니다.
#
# max_retries:
# - 네트워크 오류, API 오류 등 일시적인 실패에 대비해 재시도합니다.
def classify_agent(img_url: str, max_retries=3) -> int:
    for attempt in range(max_retries):
        try:
            # 1) 1차 관찰
            obs1 = observe(img_url, strict=False)
            label1, uncertain = decide(obs1)

            # 2) 애매하지 않으면 바로 종료(불필요한 호출 방지)
            if not uncertain:
                return label1

            # 3) 애매하면 1회 재검토(더 보수적으로 판단)
            obs2 = observe(img_url, strict=True)
            label2, _ = decide(obs2)

            # 4) 재검토에서도 결함이 잡히면 비정상 확정
            if label2 == LABEL_ABNORMAL:
                return LABEL_ABNORMAL

            # 5) 재검토에서 결함이 없으면 1차 결과 유지
            return label1

        except Exception as e:
            # 마지막 시도까지 실패하면 예외를 그대로 올립니다.
            if attempt == max_retries - 1:
                raise

            # 간단한 backoff(재시도 간격 증가)로 서버/네트워크 불안정에 대응
            time.sleep((0.5 * (2 ** attempt)) + random.uniform(0, 0.2))

# =========================
# main()
# =========================
# 역할:
# - test.csv를 읽고(id, img_url 필요)
# - 각 이미지에 대해 classify_agent 실행
# - 최종 submission.csv를 (id, label) 컬럼으로 생성
#
# 참가자 확장 포인트:
# - time.sleep(0.2)를 조정하면 호출 속도를 바꿀 수 있습니다.
# - fallback label(기본값)을 바꿀 수도 있습니다(기본은 정상=0).
def main():
    test_df = pd.read_csv(TEST_CSV_PATH)

    # test.csv에 필수 컬럼이 있는지 확인
    if "id" not in test_df.columns or "img_url" not in test_df.columns:
        raise ValueError(f"columns: {test_df.columns.tolist()}")

    preds = []
    n = len(test_df)

    for i, row in test_df.iterrows():
        _id = row["id"]
        img_url = row["img_url"]

        try:
            label = classify_agent(img_url)
            print(f"[{i+1}/{n}] id={_id} -> {label}")
        except Exception as e:
            # 오류 발생 시 정상(0) 판단으로 예외 처리
            print(f"[{i+1}/{n}] id={_id} ERROR -> fallback 0 | {e}")
            label = LABEL_NORMAL

        # 제출 형식: 무조건 id, label 컬럼
        preds.append({"id": _id, "label": label})

        # 너무 빠른 연속 호출로 인한 'API 호출 오류'를 피하기 위한 최소 sleep 설정
        time.sleep(0.2)

    # 최종 제출 파일 생성
    out_df = pd.DataFrame(preds, columns=["id", "label"])
    out_df.to_csv(OUT_PATH, index=False)

    print(f"\n✅ Saved: {OUT_PATH}")
    print(out_df.head())

# 스크립트 실행 시 main() 수행
if __name__ == "__main__":
    main()