import streamlit as st
import json, os, re, csv, base64
from pathlib import Path
from datetime import datetime
import requests
from PIL import Image, ImageDraw, ImageFont

# =========================
# UI (Instagram-style Dark)
# =========================
st.set_page_config(page_title="ootd", layout="wide")

st.markdown("""
<style>
.stApp { background-color: #121212; color: #EAEAEA; }
section[data-testid="stSidebar"] { background-color: #1A1A1A; }
.card {
    background-color: #1E1E1E;
    border-radius: 18px;
    padding: 16px;
    margin-bottom: 16px;
}
.smallcard {
    background-color: #1E1E1E;
    border-radius: 14px;
    padding: 12px;
    margin-bottom: 10px;
}
.stButton>button {
    background-color: #4F7FFF;
    color: white;
    border-radius: 20px;
}
hr { border: none; border-top: 1px solid #2A2A2A; margin: 14px 0; }
</style>
""", unsafe_allow_html=True)

# =========================
# Helpers
# =========================
def load_json(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except:
        return default

def save_json(path: Path, obj):
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")

def safe_slug(s: str) -> str:
    s = (s or "").strip()
    s = re.sub(r"[^a-zA-Z0-9._-]", "_", s)
    return s or "guest"

# =========================
# Sidebar: User + API + Location
# =========================
with st.sidebar:
    st.header("👤 사용자")
    user_id = safe_slug(st.text_input("사용자 ID(닉네임/이메일)", value="guest"))
    st.caption("ID가 다르면 옷장/피드백이 완전히 분리 저장돼요.")

    st.markdown("---")
    st.header("🔑 API 설정")
    openai_key = st.text_input("OpenAI API Key", type="password", value=os.environ.get("OPENAI_API_KEY", ""))
    use_openai = st.toggle("OpenAI 기능 사용", value=bool(openai_key))
    use_vision = st.toggle("사진 분석(Vision) 사용", value=bool(openai_key))
    use_ai_rerank = st.toggle("추천 마지막 단계 AI 리랭크", value=bool(openai_key))
    if openai_key:
        os.environ["OPENAI_API_KEY"] = openai_key

    st.markdown("---")
    st.header("📍 위치/날씨")
    lat = st.number_input("위도(lat)", value=37.5665, format="%.6f")
    lon = st.number_input("경도(lon)", value=126.9780, format="%.6f")

# =========================
# User-scoped Data Paths
# =========================
BASE = Path("data") / "users" / user_id
IMG_DIR = BASE / "images"
CLOSET = BASE / "closet.json"
FEEDBACK = BASE / "feedback.json"
PROFILE = BASE / "profile.json"

BASE.mkdir(parents=True, exist_ok=True)
IMG_DIR.mkdir(parents=True, exist_ok=True)

if not CLOSET.exists():
    CLOSET.write_text("[]", encoding="utf-8")
if not FEEDBACK.exists():
    FEEDBACK.write_text("[]", encoding="utf-8")
if not PROFILE.exists():
    PROFILE.write_text(json.dumps({"temp_bias": 0.0}, ensure_ascii=False, indent=2), encoding="utf-8")

def load_closet():
    return load_json(CLOSET, [])

def save_closet(c):
    save_json(CLOSET, c)

def load_feedback():
    return load_json(FEEDBACK, [])

def save_feedback(fb):
    save_json(FEEDBACK, fb)

def load_profile():
    return load_json(PROFILE, {"temp_bias": 0.0})

def save_profile(p):
    save_json(PROFILE, p)

# =========================
# Optional OpenAI client
# =========================
client = None
if use_openai and openai_key:
    try:
        from openai import OpenAI
        client = OpenAI()
    except:
        client = None

# =========================
# Free APIs: Weather + Reverse geocode
# =========================
def reverse_geocode(lat, lon):
    try:
        url = "https://nominatim.openstreetmap.org/reverse"
        params = {"format": "jsonv2", "lat": lat, "lon": lon}
        headers = {"User-Agent": "ootd-streamlit-demo/1.0"}
        r = requests.get(url, params=params, headers=headers, timeout=10)
        r.raise_for_status()
        return r.json().get("display_name", "")
    except:
        return ""

def get_weather(lat, lon):
    url = "https://api.open-meteo.com/v1/forecast"
    params = {"latitude": lat, "longitude": lon, "current_weather": "true", "timezone": "auto"}
    data = requests.get(url, params=params, timeout=10).json()
    w = data.get("current_weather", {}) or {}
    return {
        "temperature": w.get("temperature"),
        "windspeed": w.get("windspeed"),
        "weathercode": w.get("weathercode"),
        "time": w.get("time"),
    }

# =========================
# Categories / style
# =========================
CATEGORIES = ["top", "bottom", "outer", "shoes"]
STYLES = ["casual", "dandy", "hiphop", "sporty"]

# Vision meta vocab (간단하게 고정)
COLORS = ["black","white","gray","navy","beige","brown","blue","green","red","pink","purple","yellow","orange","multi","unknown"]
PATTERNS = ["solid","stripe","check","denim","logo","graphic","dot","floral","leather","knit","unknown"]
WARMTH = ["thin","normal","thick","unknown"]
VIBES = ["casual","dandy","hiphop","sporty","minimal","street","formal","cute","unknown"]

# =========================
# Situations
# =========================
SITUATIONS = [
    "학교/수업(무난 & 편함)",
    "데이트(호감/깔끔)",
    "친구 약속(꾸안꾸)",
    "소개팅/첫만남(호감/단정)",
    "면접/발표/중요한 날(힘줘야 함)",
    "동아리/모임/회식(적당히 갖춘)",
    "출근/미팅(단정/실용)",
    "여행/나들이(활동/사진)",
    "운동/러닝(스포티)",
    "집콕/근처 마실(편안)",
    "결혼식/격식(포멀)",
    "장례식/예의(차분)",
]

def situation_hint(s):
    mapping = {
        "학교/수업(무난 & 편함)": "편안하지만 깔끔. 너무 과한 포인트는 X",
        "데이트(호감/깔끔)": "깔끔+포인트 1개. 실루엣 정돈",
        "친구 약속(꾸안꾸)": "편안하지만 센스 있게. 베이직 + 포인트",
        "소개팅/첫만남(호감/단정)": "단정·깔끔·과하지 않게",
        "면접/발표/중요한 날(힘줘야 함)": "정돈된 느낌/신뢰감. 포멀 쪽",
        "동아리/모임/회식(적당히 갖춘)": "캐주얼+단정 중간. 무난한 신발",
        "출근/미팅(단정/실용)": "실용 + 단정. 과한 로고는 X",
        "여행/나들이(활동/사진)": "활동성 + 사진발. 레이어드/색 조합",
        "운동/러닝(스포티)": "기능성·움직임·땀 고려",
        "집콕/근처 마실(편안)": "편안 최우선 + 최소한의 깔끔",
        "결혼식/격식(포멀)": "격식. 어두운 톤/단정한 신발",
        "장례식/예의(차분)": "무채색·단정·튀지 않게",
    }
    return mapping.get(s, "")

# =========================
# Placeholder image generator (카테고리 간단 그림)
# =========================
def _get_font(size: int):
    try:
        return ImageFont.truetype("DejaVuSans.ttf", size)
    except:
        return ImageFont.load_default()

def draw_simple_icon(draw: ImageDraw.ImageDraw, category: str, x: int, y: int, w: int, h: int):
    stroke = (220, 220, 220)
    fill = (50, 50, 50)

    if category == "top":
        draw.rectangle([x+w*0.30, y+h*0.30, x+w*0.70, y+h*0.85], outline=stroke, width=4, fill=fill)
        draw.polygon([(x+w*0.30, y+h*0.35), (x+w*0.18, y+h*0.48), (x+w*0.30, y+h*0.55)],
                     outline=stroke, fill=fill)
        draw.polygon([(x+w*0.70, y+h*0.35), (x+w*0.82, y+h*0.48), (x+w*0.70, y+h*0.55)],
                     outline=stroke, fill=fill)
    elif category == "bottom":
        draw.rectangle([x+w*0.35, y+h*0.30, x+w*0.65, y+h*0.85], outline=stroke, width=4, fill=fill)
        draw.line([x+w*0.50, y+h*0.30, x+w*0.50, y+h*0.85], fill=stroke, width=3)
        draw.rectangle([x+w*0.35, y+h*0.85, x+w*0.47, y+h*0.95], outline=stroke, width=4, fill=fill)
        draw.rectangle([x+w*0.53, y+h*0.85, x+w*0.65, y+h*0.95], outline=stroke, width=4, fill=fill)
    elif category == "outer":
        draw.rectangle([x+w*0.32, y+h*0.25, x+w*0.68, y+h*0.95], outline=stroke, width=4, fill=fill)
        draw.line([x+w*0.50, y+h*0.25, x+w*0.50, y+h*0.95], fill=stroke, width=3)
        draw.polygon([(x+w*0.32, y+h*0.25), (x+w*0.40, y+h*0.42), (x+w*0.50, y+h*0.25)],
                     outline=stroke, fill=fill)
        draw.polygon([(x+w*0.68, y+h*0.25), (x+w*0.60, y+h*0.42), (x+w*0.50, y+h*0.25)],
                     outline=stroke, fill=fill)
    elif category == "shoes":
        draw.rounded_rectangle([x+w*0.25, y+h*0.60, x+w*0.80, y+h*0.78], radius=18,
                               outline=stroke, width=4, fill=fill)
        draw.rounded_rectangle([x+w*0.25, y+h*0.75, x+w*0.82, y+h*0.86], radius=18,
                               outline=stroke, width=4, fill=fill)

def make_placeholder_image(name: str, category: str, out_path: Path, size=(640, 640)):
    img = Image.new("RGB", size, (24, 24, 24))
    draw = ImageDraw.Draw(img)
    draw.rounded_rectangle([24, 18, size[0]-24, 82], radius=22, fill=(36, 36, 36))
    font_small = _get_font(20)
    draw.text((44, 38), f"ootd • {category}", fill=(230, 230, 230), font=font_small)

    icon_box = (60, 120, size[0]-60, 420)
    draw.rounded_rectangle(icon_box, radius=34, fill=(30, 30, 30), outline=(70, 70, 70), width=2)
    x1, y1, x2, y2 = icon_box
    draw_simple_icon(draw, category, x1, y1, x2-x1, y2-y1)

    font = _get_font(28)
    name = (name or "item").strip() or "item"
    lines = [name[:28]]
    y = 450
    for ln in lines:
        draw.text((60, y), ln, fill=(245, 245, 245), font=font)
        y += 46

    draw.rounded_rectangle([60, size[1]-120, size[0]-60, size[1]-58], radius=26, fill=(79, 127, 255))
    draw.text((80, size[1]-105), "auto-generated", fill=(255, 255, 255), font=font_small)
    img.save(out_path)

# =========================
# OpenAI Vision: clothing photo -> meta 추출
# =========================
def analyze_clothing_image_with_openai(image_bytes: bytes, fallback_name: str = ""):
    """
    return dict:
      {"color":"black", "pattern":"solid", "warmth":"normal", "vibe":"dandy", "desc":"..."}
    """
    if not client:
        return {"color":"unknown","pattern":"unknown","warmth":"unknown","vibe":"unknown","desc":""}

    b64 = base64.b64encode(image_bytes).decode("utf-8")
    prompt = f"""
너는 의류 사진 분석기야. 아래 선택지 중에서만 골라 JSON만 반환해.
- color: {COLORS}
- pattern: {PATTERNS}
- warmth(두께감): {WARMTH}
- vibe(분위기): {VIBES}

규칙:
- 확실치 않으면 unknown
- desc는 한국어로 1문장(짧게)
- JSON만 반환

추가 힌트(있으면 참고): {fallback_name}
반환 형식:
{{
  "color":"black",
  "pattern":"solid",
  "warmth":"normal",
  "vibe":"dandy",
  "desc":"..."
}}
""".strip()

    try:
        resp = client.responses.create(
            model="gpt-4.1-mini",
            input=[{
                "role":"user",
                "content":[
                    {"type":"input_text","text":prompt},
                    {"type":"input_image","image_url":f"data:image/png;base64,{b64}"}
                ]
            }]
        )
        text = resp.output_text
        m = re.search(r"\{.*\}", text, re.DOTALL)
        if not m:
            return {"color":"unknown","pattern":"unknown","warmth":"unknown","vibe":"unknown","desc":""}
        data = json.loads(m.group(0))

        c = data.get("color","unknown")
        p = data.get("pattern","unknown")
        w = data.get("warmth","unknown")
        v = data.get("vibe","unknown")
        d = str(data.get("desc",""))[:120]

        if c not in COLORS: c = "unknown"
        if p not in PATTERNS: p = "unknown"
        if w not in WARMTH: w = "unknown"
        if v not in VIBES: v = "unknown"
        return {"color":c, "pattern":p, "warmth":w, "vibe":v, "desc":d}
    except:
        return {"color":"unknown","pattern":"unknown","warmth":"unknown","vibe":"unknown","desc":""}

# =========================
# OpenAI: receipt -> names, names -> category (이전 방식 유지)
# =========================
def extract_names_from_receipt_image(image_bytes: bytes):
    if not client:
        return []
    b64 = base64.b64encode(image_bytes).decode("utf-8")
    prompt = """
너는 영수증/구매내역 이미지에서 '의류/신발' 품목명만 뽑는 도우미야.
의류/신발로 보이는 것만 최대 20개.
반환은 JSON만:
{"items":["상품명1","상품명2",...]}
""".strip()
    try:
        resp = client.responses.create(
            model="gpt-4.1-mini",
            input=[{
                "role":"user",
                "content":[
                    {"type":"input_text","text":prompt},
                    {"type":"input_image","image_url":f"data:image/png;base64,{b64}"}
                ]
            }]
        )
        m = re.search(r"\{.*\}", resp.output_text, re.DOTALL)
        if not m:
            return []
        data = json.loads(m.group(0))
        names = [str(x).strip()[:80] for x in data.get("items", []) if str(x).strip()]
        return names[:20]
    except:
        return []

def classify_items_with_openai(item_names):
    if not client or not item_names:
        return [{"name": n, "type": "unknown", "confidence": 0.0} for n in item_names]

    prompt = f"""
너는 패션 상품명을 카테고리로 분류하는 분류기야.
가능한 type: top, bottom, outer, shoes, unknown
규칙: 확실하지 않으면 unknown / JSON만 / confidence 0~1
입력: {item_names}
반환:
{{"items":[{{"name":"...","type":"top","confidence":0.82}}]}}
""".strip()
    try:
        resp = client.responses.create(model="gpt-4.1-mini", input=prompt)
        m = re.search(r"\{.*\}", resp.output_text, re.DOTALL)
        if not m:
            return [{"name": n, "type": "unknown", "confidence": 0.0} for n in item_names]
        data = json.loads(m.group(0))
        out = []
        for it in data.get("items", []):
            nm = (it.get("name") or "").strip()[:80]
            tp = it.get("type","unknown")
            conf = it.get("confidence", 0.0)
            if tp not in ["top","bottom","outer","shoes","unknown"]:
                tp = "unknown"
            try:
                conf = float(conf)
            except:
                conf = 0.0
            conf = max(0.0, min(1.0, conf))
            if nm:
                out.append({"name": nm, "type": tp, "confidence": conf})
        return out[:20] if out else [{"name": n, "type": "unknown", "confidence": 0.0} for n in item_names]
    except:
        return [{"name": n, "type": "unknown", "confidence": 0.0} for n in item_names]

# =========================
# Color/pattern/vibe scoring rules
# =========================
NEUTRALS = {"black","white","gray","navy","beige","brown"}

def color_compat_score(colors: dict):
    """
    colors: {"top": "black", "bottom":"gray", "outer":"navy", "shoes":"black"}
    간단 룰:
      - neutral+neutral: +2
      - neutral+color: +1
      - color+color: 동일계열/무난 판단 어려우니 +0
      - multi 있으면 과해질 수 있어 -1 (단, 나머지 다 neutral이면 0)
    """
    vals = [c for c in colors.values() if c and c != "unknown"]
    if not vals:
        return 0, ["색 정보 부족(unknown)"]

    reasons = []
    score = 0
    neutral_cnt = sum(1 for c in vals if c in NEUTRALS)
    multi_cnt = sum(1 for c in vals if c == "multi")

    if neutral_cnt >= 3:
        score += 2; reasons.append("무채색/뉴트럴 중심이라 안정적")
    elif neutral_cnt >= 2:
        score += 1; reasons.append("뉴트럴 베이스라 매치 쉬움")

    if multi_cnt >= 1:
        if neutral_cnt >= 3:
            score += 0; reasons.append("포인트(멀티) + 뉴트럴로 밸런스")
        else:
            score -= 1; reasons.append("멀티 아이템이 많으면 복잡해질 수 있음")

    return score, reasons

def pattern_compat_score(patterns: dict):
    """
    patterns: {"top":"stripe", "bottom":"solid", ...}
    룰:
      - 패턴 1개 + 나머지 solid/unknown: +2
      - 패턴 2개 이상(서로 다르면): -1
      - all solid: +1
    """
    vals = [p for p in patterns.values() if p and p != "unknown"]
    if not vals:
        return 0, ["패턴 정보 부족(unknown)"]

    non_solid = [p for p in vals if p != "solid"]
    if len(non_solid) == 0:
        return 1, ["전체 무지(solid)라 깔끔"]
    if len(non_solid) == 1:
        return 2, ["패턴 1개 포인트 + 나머지 깔끔"]
    # 2개 이상 패턴
    unique = set(non_solid)
    if len(unique) >= 2:
        return -1, ["서로 다른 패턴이 여러 개면 산만할 수 있음"]
    return 0, ["같은 계열 패턴 여러 개(중립)"]

def vibe_fit_score(vibes: dict, situation: str):
    """
    vibes: {"top":"dandy", ...}
    situation 기반으로 원하는 vibe가 있으면 가산
    """
    desired = set()
    if any(x in situation for x in ["면접","발표","중요","출근","미팅","결혼식","장례식"]):
        desired |= {"formal","minimal","dandy"}
    if any(x in situation for x in ["데이트","소개팅","첫만남"]):
        desired |= {"dandy","minimal","cute"}
    if any(x in situation for x in ["운동","러닝"]):
        desired |= {"sporty"}
    if any(x in situation for x in ["학교","수업","꾸안꾸","집콕","근처 마실"]):
        desired |= {"casual","minimal"}
    if "여행" in situation or "나들이" in situation:
        desired |= {"casual","street","minimal"}

    vals = [v for v in vibes.values() if v and v != "unknown"]
    if not vals or not desired:
        return 0, ["분위기 정보 부족/상황 목표 없음"]

    hit = sum(1 for v in vals if v in desired)
    if hit >= 2:
        return 2, [f"상황({situation})에 어울리는 분위기(vibe) 다수 일치"]
    if hit == 1:
        return 1, [f"상황에 맞는 분위기(vibe) 일부 일치"]
    return -1, ["상황 분위기와 vibe가 다소 다름"]

# =========================
# OpenAI: final rerank (선택)
# =========================
def ai_rerank_outfits(weather, situation, candidates):
    """
    candidates: list of dict
      [{"id":"c1","outfit":{"top":{...},"bottom":{...},...}, "rule_score": 7, "reasons":[...]}]
    return: chosen candidate id + short reason
    """
    if not client or not candidates:
        return None

    simplified = []
    for c in candidates[:6]:
        outfit = c["outfit"]
        simplified.append({
            "id": c["id"],
            "rule_score": c["rule_score"],
            "items": {
                k: {
                    "name": outfit[k].get("name"),
                    "type": outfit[k].get("type"),
                    "color": outfit[k].get("color"),
                    "pattern": outfit[k].get("pattern"),
                    "warmth": outfit[k].get("warmth"),
                    "vibe": outfit[k].get("vibe"),
                } for k in outfit.keys()
            }
        })

    prompt = f"""
너는 OOTD 코디 선택 심사위원이야.
날씨/상황에 가장 잘 맞고 색/패턴/분위기 밸런스가 좋은 후보 1개를 고르자.
반환은 JSON만.

- 날씨: {weather}
- 상황: {situation}
- 후보: {simplified}

반환 형식:
{{
  "best_id":"c1",
  "why":"짧게 1~2문장"
}}
""".strip()

    try:
        resp = client.responses.create(model="gpt-4.1-mini", input=prompt)
        m = re.search(r"\{.*\}", resp.output_text, re.DOTALL)
        if not m:
            return None
        data = json.loads(m.group(0))
        return {"best_id": data.get("best_id"), "why": str(data.get("why",""))[:140]}
    except:
        return None

# =========================
# Recommendation Engine (업그레이드)
# =========================
def recommend(closet, weather, situation, temp_bias=0.0, user_style_primary=None, do_ai_rerank=False):
    temp = weather.get("temperature")
    effective_temp = None if temp is None else (temp + temp_bias)

    # 상황 플래그
    wants_formal = any(x in situation for x in ["면접", "발표", "중요", "출근", "미팅", "결혼식", "장례식"])
    wants_comfy  = any(x in situation for x in ["집콕", "학교", "꾸안꾸", "근처", "수업"])
    wants_sporty = any(x in situation for x in ["운동", "러닝"])
    wants_date   = any(x in situation for x in ["데이트", "소개팅", "첫만남"])

    # 1) 아이템별 점수(기존 룰 + warmth/vibe 약간 반영)
    item_scores = {}
    item_reasons = {}

    for item in closet:
        s = 0
        r = []
        name = item.get("name","")
        tp = item.get("type")

        # 날씨(두께)
        if effective_temp is not None:
            if effective_temp < 10:
                if tp == "outer":
                    s += 4; r.append("기온 낮음 → 아우터 가산")
                if item.get("warmth") == "thick":
                    s += 2; r.append("두께감(thick) → 추운 날 가산")
                if item.get("warmth") == "thin":
                    s -= 1; r.append("얇음(thin) → 추운 날 감점")
            if effective_temp >= 22:
                if tp == "outer":
                    s -= 3; r.append("기온 높음 → 아우터 감점")
                if item.get("warmth") == "thin":
                    s += 1; r.append("얇음(thin) → 더운 날 가산")
                if item.get("warmth") == "thick":
                    s -= 1; r.append("두꺼움(thick) → 더운 날 감점")

        # 상황 키워드 (이름)
        if wants_sporty:
            if tp == "shoes":
                s += 2; r.append("운동/러닝 → 신발 중요")
            if any(k in name for k in ["운동", "트레이닝", "러닝", "조거", "스니커", "레깅스"]):
                s += 3; r.append("운동 키워드 매칭")

        if wants_formal:
            if any(k in name for k in ["셔츠", "슬랙", "코트", "자켓", "블레이저", "로퍼"]):
                s += 3; r.append("격식 키워드 매칭")
            if any(k in name for k in ["후드", "트랙", "조거", "볼캡"]):
                s -= 2; r.append("격식 상황에 캐주얼 감점")

        if wants_date:
            if any(k in name for k in ["셔츠", "니트", "코트", "자켓", "로퍼", "가디건"]):
                s += 2; r.append("데이트/첫만남 → 깔끔 가산")

        if wants_comfy:
            if any(k in name for k in ["후드", "맨투맨", "티", "청바지", "가디건", "스니커"]):
                s += 2; r.append("편한 상황 → 캐주얼 가산")

        # (선택) 스타일 태그
        if user_style_primary:
            if item.get("primary_style") == user_style_primary or item.get("secondary_style") == user_style_primary:
                s += 1; r.append("선택 스타일 태그 일치(선택사항)")

        # vibe도 가볍게 반영(상황과 어울리면 가산)
        vibe = item.get("vibe","unknown")
        if wants_formal and vibe in ["formal","minimal","dandy"]:
            s += 1; r.append("상황(격식)과 vibe 어울림")
        if wants_sporty and vibe == "sporty":
            s += 1; r.append("상황(운동)과 vibe 어울림")
        if wants_date and vibe in ["dandy","minimal","cute"]:
            s += 1; r.append("상황(데이트)와 vibe 어울림")

        item_scores[item["id"]] = s
        item_reasons[item["id"]] = r if r else ["기본 점수"]

    # 2) 카테고리별 상위 후보 뽑기(조합 후보 생성)
    def topk(cat, k=4):
        cand = [i for i in closet if i.get("type")==cat]
        cand.sort(key=lambda x: item_scores.get(x["id"], 0), reverse=True)
        return cand[:k]

    top_c = topk("top", 4)
    bot_c = topk("bottom", 4)
    out_c = topk("outer", 4) if closet else []
    sh_c  = topk("shoes", 4)

    # outer는 날씨/보유에 따라 선택적으로
    include_outer = True
    if effective_temp is not None and effective_temp >= 22:
        include_outer = False  # 더우면 기본은 아우터 제외(있어도 후보로만)

    # 3) 조합 후보 만들고 색/패턴/분위기 점수 반영
    candidates = []
    cid = 0
    for t in top_c:
        for b in bot_c:
            for s in sh_c:
                # outer를 포함한 조합 + 포함하지 않은 조합 모두 고려(상황/날씨에 따라)
                outs = out_c[:3] if out_c else [None]
                for o in outs:
                    outfit = {"top": t, "bottom": b, "shoes": s}
                    if o is not None:
                        outfit["outer"] = o

                    # rule score 합
                    rule_score = sum(item_scores.get(x["id"], 0) for x in outfit.values())
                    reasons = []
                    for x in outfit.values():
                        reasons += item_reasons.get(x["id"], [])

                    # 색/패턴/분위기 점수
                    colors = {k: outfit[k].get("color","unknown") for k in outfit.keys()}
                    patterns = {k: outfit[k].get("pattern","unknown") for k in outfit.keys()}
                    vibes = {k: outfit[k].get("vibe","unknown") for k in outfit.keys()}

                    c_sc, c_rs = color_compat_score(colors)
                    p_sc, p_rs = pattern_compat_score(patterns)
                    v_sc, v_rs = vibe_fit_score(vibes, situation)

                    total = rule_score + c_sc + p_sc + v_sc
                    reasons2 = list(dict.fromkeys(reasons + c_rs + p_rs + v_rs))  # 중복 제거

                    # 더운 날 아우터 포함은 약간 감점
                    if effective_temp is not None and effective_temp >= 22 and "outer" in outfit:
                        total -= 1
                        reasons2.append("더운 날 아우터는 선택적으로(감점)")

                    # include_outer가 False면 outer 없는 조합 우선이 되도록 보정
                    if not include_outer and "outer" in outfit:
                        total -= 1

                    cid += 1
                    candidates.append({
                        "id": f"c{cid}",
                        "outfit": outfit,
                        "rule_score": total,
                        "reasons": reasons2
                    })

    # 후보 정렬
    candidates.sort(key=lambda x: x["rule_score"], reverse=True)
    top_candidates = candidates[:6]

    # 4) (선택) AI가 후보 조합 리랭크
    chosen = top_candidates[0] if top_candidates else None
    ai_pick = None
    if do_ai_rerank and client and top_candidates:
        ai_pick = ai_rerank_outfits(weather, situation, top_candidates)
        if ai_pick and ai_pick.get("best_id"):
            found = next((c for c in top_candidates if c["id"] == ai_pick["best_id"]), None)
            if found:
                chosen = found

    meta = {"temp_bias": temp_bias, "effective_temp": effective_temp, "ai_rerank": bool(ai_pick)}
    return chosen, top_candidates, meta, ai_pick

# =========================
# Header
# =========================
st.title("🧥 ootd")

loc_name = reverse_geocode(lat, lon)
weather = get_weather(lat, lon)

st.markdown("<div class='smallcard'>", unsafe_allow_html=True)
st.write("👤 사용자:", user_id)
st.write("📍 위치:", loc_name if loc_name else f"{lat:.4f}, {lon:.4f}")
st.write("🌦️ 현재:", f"{weather.get('temperature')}°C", f"💨 바람 {weather.get('windspeed')}km/h")
st.caption(f"시간: {weather.get('time')}")
st.markdown("</div>", unsafe_allow_html=True)

profile = load_profile()
temp_bias = float(profile.get("temp_bias", 0.0))

# =========================
# 1) Closet register
# =========================
st.markdown("## 1) 📸 옷장 등록 (사진 분석으로 색/패턴/분위기 저장)")
tabA, tabB = st.tabs(["옷 사진 등록(추천)", "영수증 등록(카테고리만)"])

with tabA:
    col1, col2 = st.columns([1,1])
    with col1:
        img = st.file_uploader("옷 사진 업로드", type=["jpg","png"], key="cloth_img")
        item_type = st.selectbox("카테고리", CATEGORIES, key="cloth_type")
        name = st.text_input("아이템 이름(권장)", placeholder="예: 검정 셔츠, 슬랙스", key="cloth_name")

        auto_analyze = st.toggle("사진에서 색/패턴/분위기 자동 분석(Vision)", value=True)

    with col2:
        st.markdown("### 🎯 스타일 태그(선택)")
        style_use = st.toggle("스타일 태그 입력(선택)", value=False)
        primary_style = None
        secondary_style = None
        if style_use:
            ps = st.selectbox("주 스타일(선택)", ["선택안함"] + STYLES, index=0)
            ss = st.selectbox("보조 스타일(선택)", ["없음"] + STYLES, index=0)
            primary_style = None if ps == "선택안함" else ps
            secondary_style = None if ss == "없음" else ss
            if primary_style and secondary_style == primary_style:
                secondary_style = None

        st.markdown("### 🧠 AI 분석 결과(미리보기)")
        if img and use_openai and use_vision and client and auto_analyze:
            if st.button("AI로 사진 분석(미리보기)"):
                meta = analyze_clothing_image_with_openai(img.getvalue(), fallback_name=name)
                st.session_state["vision_preview"] = meta
        meta_prev = st.session_state.get("vision_preview")
        if meta_prev:
            st.write(meta_prev)

    if st.button("옷장에 저장", key="cloth_save"):
        closet = load_closet()
        iid = f"item_{datetime.now().timestamp()}"
        img_path = IMG_DIR / f"{iid}.png"

        # 이미지 저장
        if img:
            image = Image.open(img)
            image.save(img_path)
        else:
            make_placeholder_image(name if name else item_type, item_type, img_path)

        # Vision 분석 (저장 시점)
        vision_meta = {"color":"unknown","pattern":"unknown","warmth":"unknown","vibe":"unknown","desc":""}
        if img and use_openai and use_vision and client and auto_analyze:
            vision_meta = analyze_clothing_image_with_openai(img.getvalue(), fallback_name=name)

        closet.append({
            "id": iid,
            "type": item_type,
            "name": name if name else item_type,
            "primary_style": primary_style,
            "secondary_style": secondary_style,
            "image": str(img_path),
            # ✅ 핵심: 추천에 쓰일 메타데이터 저장
            "color": vision_meta.get("color","unknown"),
            "pattern": vision_meta.get("pattern","unknown"),
            "warmth": vision_meta.get("warmth","unknown"),
            "vibe": vision_meta.get("vibe","unknown"),
            "desc": vision_meta.get("desc",""),
            "created_at": datetime.now().isoformat(),
            "source": "manual_photo"
        })
        save_closet(closet)
        st.success("저장 완료! (색/패턴/분위기 메타가 추천에 반영됩니다)")

with tabB:
    st.caption("영수증은 품목명이어서 색/패턴은 알기 어렵고, 카테고리만 자동 등록해요(이미지는 기본 그림).")
    receipt_img = st.file_uploader("영수증 사진 업로드", type=["jpg","png"], key="receipt_img")

    if st.button("영수증 분석하기(AI)", key="receipt_analyze"):
        if not (use_openai and client):
            st.error("OpenAI API Key가 필요해요.")
        elif not receipt_img:
            st.error("영수증 이미지를 올려줘.")
        else:
            names = extract_names_from_receipt_image(receipt_img.getvalue())
            classified = classify_items_with_openai(names)
            for it in classified:
                if it.get("type") in ["top","bottom","outer","shoes"] and it.get("confidence", 0) < 0.55:
                    it["type"] = "unknown"
            st.session_state["receipt_preview"] = classified
            st.success("분석 완료! 아래에서 수정 후 추가해줘.")

    preview = st.session_state.get("receipt_preview", [])
    if preview:
        edited = []
        for idx, it in enumerate(preview):
            with st.expander(f"{idx+1}. {it['name']}"):
                nm = st.text_input("상품명", value=it["name"], key=f"rc_nm_{idx}")
                tp_list = ["unknown"] + CATEGORIES
                cur = it.get("type","unknown")
                if cur not in tp_list: cur = "unknown"
                tp = st.selectbox("카테고리", tp_list, index=tp_list.index(cur), key=f"rc_tp_{idx}")
                add_flag = st.checkbox("추가", value=(tp != "unknown"), key=f"rc_add_{idx}")
                edited.append({"name": nm.strip()[:80], "type": tp, "add": add_flag})

        col_yes, col_no = st.columns(2)
        with col_yes:
            if st.button("✅ 예, 옷장에 추가"):
                closet = load_closet()
                added = 0
                for idx, it in enumerate(edited):
                    if not it["add"] or it["type"] == "unknown":
                        continue
                    iid = f"item_{datetime.now().timestamp()}_rc{idx}"
                    img_path = IMG_DIR / f"{iid}.png"
                    make_placeholder_image(it["name"], it["type"], img_path)
                    closet.append({
                        "id": iid,
                        "type": it["type"],
                        "name": it["name"],
                        "primary_style": None,
                        "secondary_style": None,
                        "image": str(img_path),
                        # 영수증은 색/패턴/분위기 unknown
                        "color":"unknown","pattern":"unknown","warmth":"unknown","vibe":"unknown","desc":"",
                        "created_at": datetime.now().isoformat(),
                        "source": "receipt_ai"
                    })
                    added += 1
                save_closet(closet)
                st.success(f"{added}개 추가 완료!")
                st.session_state.pop("receipt_preview", None)
                st.rerun()

        with col_no:
            if st.button("❌ 아니오, 취소"):
                st.session_state.pop("receipt_preview", None)
                st.rerun()

st.markdown("---")

# =========================
# 2) Closet view + Delete confirmation
# =========================
st.markdown("## 2) 👕 내 옷장 (메타 포함)")
closet = load_closet()

if "pending_delete_id" not in st.session_state:
    st.session_state["pending_delete_id"] = None

if not closet:
    st.info("아직 옷이 없어. 위에서 등록해줘!")
else:
    cols = st.columns(4)
    for i, item in enumerate(closet):
        with cols[i % 4]:
            st.markdown("<div class='smallcard'>", unsafe_allow_html=True)
            if item.get("image"):
                st.image(item["image"], use_container_width=True)
            st.caption(item.get("name",""))
            st.caption(f"{item.get('type')} | color:{item.get('color')} | pattern:{item.get('pattern')}")
            st.caption(f"warmth:{item.get('warmth')} | vibe:{item.get('vibe')}")
            if item.get("desc"):
                st.caption("AI: " + item["desc"])

            item_id = item.get("id")
            is_pending = (st.session_state["pending_delete_id"] == item_id)

            if not is_pending:
                if st.button("🗑️ 삭제", key=f"del_{item_id}"):
                    st.session_state["pending_delete_id"] = item_id
                    st.rerun()
            else:
                st.warning("정말 삭제할까?")
                c1, c2 = st.columns(2)
                with c1:
                    if st.button("✅ 예", key=f"del_yes_{item_id}"):
                        img_path = item.get("image")
                        if img_path:
                            try:
                                p = Path(img_path)
                                if p.exists():
                                    p.unlink()
                            except:
                                pass
                        new_closet = [x for x in closet if x.get("id") != item_id]
                        save_closet(new_closet)
                        st.session_state["pending_delete_id"] = None
                        st.success("삭제 완료!")
                        st.rerun()
                with c2:
                    if st.button("❌ 아니오", key=f"del_no_{item_id}"):
                        st.session_state["pending_delete_id"] = None
                        st.rerun()

            st.markdown("</div>", unsafe_allow_html=True)

st.markdown("---")

# =========================
# 3) Recommendation (AI 색/패턴/분위기 반영)
# =========================
st.markdown("## 3) 🗓️ 오늘 상황 기반 코디 추천 (색/패턴/분위기 반영)")
profile = load_profile()
temp_bias = float(profile.get("temp_bias", 0.0))
st.caption(f"개인 온도 보정값(temp_bias): {temp_bias:+.1f}°C")

situation = st.selectbox("오늘 상황을 선택해줘", SITUATIONS)
st.caption("상황 힌트: " + situation_hint(situation))

optional_style = st.selectbox("스타일도 고려할래? (선택)", ["선택안함"] + STYLES, index=0)
user_style_primary = None if optional_style == "선택안함" else optional_style

if st.button("OOTD 추천"):
    closet_now = load_closet()
    if not closet_now:
        st.error("옷장이 비어있어. 먼저 옷을 등록해줘!")
        st.stop()

    chosen, top_candidates, meta, ai_pick = recommend(
        closet=closet_now,
        weather=weather,
        situation=situation,
        temp_bias=temp_bias,
        user_style_primary=user_style_primary,
        do_ai_rerank=(use_openai and use_ai_rerank and client)
    )

    if not chosen:
        st.error("추천 후보를 만들지 못했어(카테고리 부족일 수 있음). top/bottom/shoes를 최소 1개씩 등록해줘.")
        st.stop()

    outfit = chosen["outfit"]
    reasons = chosen["reasons"]

    st.session_state["last_outfit"] = outfit
    st.session_state["last_reasons"] = reasons
    st.session_state["last_meta"] = meta
    st.session_state["last_ctx"] = {
        "user_id": user_id, "weather": weather, "situation": situation,
        "user_style_primary": user_style_primary,
    }

    st.markdown("### ✨ 추천 결과")
    for k, v in outfit.items():
        st.markdown("<div class='card'>", unsafe_allow_html=True)
        if v.get("image"):
            st.image(v["image"], width=220)
        st.markdown(f"**{k.upper()} | {v.get('name','')}**")
        st.caption(f"color: {v.get('color','unknown')} | pattern: {v.get('pattern','unknown')} | warmth: {v.get('warmth','unknown')} | vibe: {v.get('vibe','unknown')}")
        if v.get("desc"):
            st.caption("AI: " + v["desc"])
        st.markdown("</div>", unsafe_allow_html=True)

    st.markdown("### ✅ 추천 근거(요약)")
    for rr in reasons[:14]:
        st.caption("• " + rr)

    if ai_pick and ai_pick.get("why"):
        st.markdown("### 🤖 AI 리랭크 한 줄 이유")
        st.write(ai_pick["why"])

    with st.expander("상위 후보 5개 보기(점수 비교)", expanded=False):
        for c in top_candidates[:5]:
            o = c["outfit"]
            st.write(f"- 점수 {c['rule_score']}: ",
                     {k: o[k].get("name") for k in o.keys()})

st.markdown("---")

# =========================
# 4) Feedback
# =========================
st.markdown("## 4) 🧊🔥 피드백(추움/딱좋음/더움)")
last_outfit = st.session_state.get("last_outfit")
if not last_outfit:
    st.info("먼저 3)에서 OOTD 추천을 받아야 피드백을 남길 수 있어요.")
else:
    fb = st.radio("체감 온도 피드백", ["추움", "딱 좋음", "더움"], horizontal=True)
    note = st.text_input("한 줄 코멘트(선택)", placeholder="예: 아우터가 너무 두꺼웠어 / 색 조합이 별로였어")

    if st.button("피드백 저장"):
        logs = load_feedback()
        ctx = st.session_state.get("last_ctx", {})
        meta = st.session_state.get("last_meta", {})
        reasons = st.session_state.get("last_reasons", [])

        logs.append({
            "time": datetime.now().isoformat(),
            "feedback": fb,
            "note": note,
            "context": ctx,
            "meta": meta,
            "reasons": reasons,
            "outfit": {k: v.get("id") for k, v in last_outfit.items()}
        })
        save_feedback(logs)

        prof = load_profile()
        bias = float(prof.get("temp_bias", 0.0))
        if fb == "추움":
            bias += 1.0
        elif fb == "더움":
            bias -= 1.0
        bias = max(-5.0, min(5.0, bias))
        prof["temp_bias"] = bias
        save_profile(prof)

        st.success(f"피드백 저장 완료! 다음 추천부터 보정값이 {bias:+.1f}°C로 반영돼.")
        st.session_state.pop("last_outfit", None)
        st.rerun()

st.markdown("---")

# =========================
# 5) Feedback stats
# =========================
st.markdown("## 5) 📊 피드백 통계(간단)")
logs = load_feedback()
if not logs:
    st.info("아직 피드백 로그가 없어.")
else:
    cnt = {"추움": 0, "딱 좋음": 0, "더움": 0}
    for l in logs[-100:]:
        v = l.get("feedback")
        if v in cnt:
            cnt[v] += 1
    st.write("최근 피드백(최대 100개):", cnt)
