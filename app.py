import streamlit as st
import json, os, re, base64
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

def clamp(x, lo, hi):
    return max(lo, min(hi, x))

# =========================
# Sidebar
# =========================
with st.sidebar:
    st.header("👤 사용자")
    user_id = safe_slug(st.text_input("사용자 ID(닉네임/이메일)", value="guest"))
    st.caption("ID가 다르면 옷장/피드백/취향학습이 분리 저장돼요.")

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
# Data paths
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
    # ✅ 취향 학습 구조 포함
    PROFILE.write_text(json.dumps({
        "temp_bias": 0.0,
        "taste": {
            "color_pref": {}, "color_avoid": {},
            "pattern_pref": {}, "pattern_avoid": {},
            "vibe_pref": {}, "vibe_avoid": {},
            "avg_rating": 0.0,
            "rating_count": 0
        }
    }, ensure_ascii=False, indent=2), encoding="utf-8")

def load_closet():
    return load_json(CLOSET, [])

def save_closet(c):
    save_json(CLOSET, c)

def load_feedback():
    return load_json(FEEDBACK, [])

def save_feedback(fb):
    save_json(FEEDBACK, fb)

def load_profile():
    return load_json(PROFILE, {
        "temp_bias": 0.0,
        "taste": {
            "color_pref": {}, "color_avoid": {},
            "pattern_pref": {}, "pattern_avoid": {},
            "vibe_pref": {}, "vibe_avoid": {},
            "avg_rating": 0.0,
            "rating_count": 0
        }
    })

def save_profile(p):
    save_json(PROFILE, p)

# =========================
# OpenAI client
# =========================
client = None
if use_openai and openai_key:
    try:
        from openai import OpenAI
        client = OpenAI()
    except:
        client = None

# =========================
# Free APIs
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
# Vocab
# =========================
CATEGORIES = ["top", "bottom", "outer", "shoes"]
STYLES = ["casual", "dandy", "hiphop", "sporty"]

COLORS = ["black","white","gray","navy","beige","brown","blue","green","red","pink","purple","yellow","orange","multi","unknown"]
PATTERNS = ["solid","stripe","check","denim","logo","graphic","dot","floral","leather","knit","unknown"]
WARMTH = ["thin","normal","thick","unknown"]
VIBES = ["casual","dandy","hiphop","sporty","minimal","street","formal","cute","unknown"]

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
# Placeholder image generator
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
    nm = (name or "item").strip() or "item"
    draw.text((60, 450), nm[:28], fill=(245, 245, 245), font=font)

    draw.rounded_rectangle([60, size[1]-120, size[0]-60, size[1]-58], radius=26, fill=(79, 127, 255))
    draw.text((80, size[1]-105), "auto-generated", fill=(255, 255, 255), font=font_small)
    img.save(out_path)

# =========================
# OpenAI Vision: photo -> meta
# =========================
def analyze_clothing_image_with_openai(image_bytes: bytes, fallback_name: str = ""):
    if not client:
        return {"color":"unknown","pattern":"unknown","warmth":"unknown","vibe":"unknown","desc":""}
    b64 = base64.b64encode(image_bytes).decode("utf-8")
    prompt = f"""
너는 의류 사진 분석기야. 아래 선택지 중에서만 골라 JSON만 반환해.
- color: {COLORS}
- pattern: {PATTERNS}
- warmth: {WARMTH}
- vibe: {VIBES}

규칙:
- 확실치 않으면 unknown
- desc는 한국어 1문장(짧게)
JSON만 반환.

힌트: {fallback_name}
반환:
{{"color":"black","pattern":"solid","warmth":"normal","vibe":"dandy","desc":"..."}}
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
# Taste learning helpers (AI 중심)
# =========================
def inc(d: dict, key: str, delta: int = 1):
    if not key: return
    d[key] = int(d.get(key, 0)) + delta

def update_taste_from_feedback(profile: dict, outfit: dict, rating: int, fb_temp: str,
                               color_fb: str, pattern_fb: str, vibe_fb: str):
    """
    - rating: 1~5
    - fb_temp: 추움/딱 좋음/더움
    - color_fb/pattern_fb/vibe_fb: 좋음/별로/상관없음
    """
    taste = profile.setdefault("taste", {
        "color_pref": {}, "color_avoid": {},
        "pattern_pref": {}, "pattern_avoid": {},
        "vibe_pref": {}, "vibe_avoid": {},
        "avg_rating": 0.0, "rating_count": 0
    })

    # 1) 별점 평균 업데이트
    cnt = int(taste.get("rating_count", 0))
    avg = float(taste.get("avg_rating", 0.0))
    new_avg = (avg * cnt + rating) / (cnt + 1)
    taste["avg_rating"] = round(new_avg, 3)
    taste["rating_count"] = cnt + 1

    # 2) 온도 보정 학습(기존 유지)
    bias = float(profile.get("temp_bias", 0.0))
    if fb_temp == "추움":
        bias += 1.0
    elif fb_temp == "더움":
        bias -= 1.0
    profile["temp_bias"] = clamp(bias, -5.0, 5.0)

    # 3) 색/패턴/분위기 학습: 코디에 등장한 값들에 대해 누적
    colors = [it.get("color","unknown") for it in outfit.values()]
    patterns = [it.get("pattern","unknown") for it in outfit.values()]
    vibes = [it.get("vibe","unknown") for it in outfit.values()]

    if color_fb == "좋음":
        for c in colors:
            if c != "unknown": inc(taste["color_pref"], c)
    elif color_fb == "별로":
        for c in colors:
            if c != "unknown": inc(taste["color_avoid"], c)

    if pattern_fb == "좋음":
        for p in patterns:
            if p != "unknown": inc(taste["pattern_pref"], p)
    elif pattern_fb == "별로":
        for p in patterns:
            if p != "unknown": inc(taste["pattern_avoid"], p)

    if vibe_fb == "좋음":
        for v in vibes:
            if v != "unknown": inc(taste["vibe_pref"], v)
    elif vibe_fb == "별로":
        for v in vibes:
            if v != "unknown": inc(taste["vibe_avoid"], v)

    return profile

def taste_score_for_outfit(profile: dict, outfit: dict):
    """
    사용자 taste를 기반으로 outfit에 가산/감점
    """
    taste = profile.get("taste", {})
    cp = taste.get("color_pref", {})
    ca = taste.get("color_avoid", {})
    pp = taste.get("pattern_pref", {})
    pa = taste.get("pattern_avoid", {})
    vp = taste.get("vibe_pref", {})
    va = taste.get("vibe_avoid", {})

    score = 0
    reasons = []

    colors = [it.get("color","unknown") for it in outfit.values()]
    patterns = [it.get("pattern","unknown") for it in outfit.values()]
    vibes = [it.get("vibe","unknown") for it in outfit.values()]

    # 너무 강하게 하지 말고 "누적값의 log-like"로 완만하게
    for c in colors:
        if c != "unknown":
            if c in cp:
                add = min(2, int(cp[c] // 3) + 1)  # 1~2
                score += add
                reasons.append(f"취향(색) 선호: {c} (+{add})")
            if c in ca:
                sub = min(2, int(ca[c] // 3) + 1)
                score -= sub
                reasons.append(f"취향(색) 비선호: {c} (-{sub})")

    for p in patterns:
        if p != "unknown":
            if p in pp:
                add = min(2, int(pp[p] // 3) + 1)
                score += add
                reasons.append(f"취향(패턴) 선호: {p} (+{add})")
            if p in pa:
                sub = min(2, int(pa[p] // 3) + 1)
                score -= sub
                reasons.append(f"취향(패턴) 비선호: {p} (-{sub})")

    for v in vibes:
        if v != "unknown":
            if v in vp:
                add = min(2, int(vp[v] // 3) + 1)
                score += add
                reasons.append(f"취향(vibe) 선호: {v} (+{add})")
            if v in va:
                sub = min(2, int(va[v] // 3) + 1)
                score -= sub
                reasons.append(f"취향(vibe) 비선호: {v} (-{sub})")

    return score, reasons[:10]

# =========================
# Color/pattern/vibe scoring
# =========================
NEUTRALS = {"black","white","gray","navy","beige","brown"}

def color_compat_score(colors: dict):
    vals = [c for c in colors.values() if c and c != "unknown"]
    if not vals:
        return 0, ["색 정보 부족(unknown)"]
    reasons = []
    score = 0
    neutral_cnt = sum(1 for c in vals if c in NEUTRALS)
    multi_cnt = sum(1 for c in vals if c == "multi")
    if neutral_cnt >= 3:
        score += 2; reasons.append("뉴트럴 중심이라 안정적")
    elif neutral_cnt >= 2:
        score += 1; reasons.append("뉴트럴 베이스라 매치 쉬움")
    if multi_cnt >= 1 and neutral_cnt < 3:
        score -= 1; reasons.append("멀티가 많으면 복잡할 수 있음")
    return score, reasons

def pattern_compat_score(patterns: dict):
    vals = [p for p in patterns.values() if p and p != "unknown"]
    if not vals:
        return 0, ["패턴 정보 부족(unknown)"]
    non_solid = [p for p in vals if p != "solid"]
    if len(non_solid) == 0:
        return 1, ["전체 무지라 깔끔"]
    if len(non_solid) == 1:
        return 2, ["패턴 1개 포인트"]
    unique = set(non_solid)
    if len(unique) >= 2:
        return -1, ["서로 다른 패턴이 많으면 산만"]
    return 0, ["같은 계열 패턴 다수(중립)"]

def vibe_fit_score(vibes: dict, situation: str):
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
        return 0, ["vibe 정보 부족/상황 목표 없음"]
    hit = sum(1 for v in vals if v in desired)
    if hit >= 2:
        return 2, ["상황과 vibe 다수 일치"]
    if hit == 1:
        return 1, ["상황과 vibe 일부 일치"]
    return -1, ["상황 vibe와 다소 다름"]

# =========================
# AI rerank (선택)
# =========================
def ai_rerank_outfits(weather, situation, profile, candidates):
    if not client or not candidates:
        return None

    taste = profile.get("taste", {})
    taste_summary = {
        "color_pref_top": sorted(taste.get("color_pref", {}).items(), key=lambda x: x[1], reverse=True)[:5],
        "color_avoid_top": sorted(taste.get("color_avoid", {}).items(), key=lambda x: x[1], reverse=True)[:5],
        "pattern_pref_top": sorted(taste.get("pattern_pref", {}).items(), key=lambda x: x[1], reverse=True)[:5],
        "pattern_avoid_top": sorted(taste.get("pattern_avoid", {}).items(), key=lambda x: x[1], reverse=True)[:5],
        "vibe_pref_top": sorted(taste.get("vibe_pref", {}).items(), key=lambda x: x[1], reverse=True)[:5],
        "vibe_avoid_top": sorted(taste.get("vibe_avoid", {}).items(), key=lambda x: x[1], reverse=True)[:5],
    }

    simplified = []
    for c in candidates[:6]:
        outfit = c["outfit"]
        simplified.append({
            "id": c["id"],
            "score": c["score"],
            "items": {k: {
                "name": outfit[k].get("name"),
                "type": outfit[k].get("type"),
                "color": outfit[k].get("color"),
                "pattern": outfit[k].get("pattern"),
                "warmth": outfit[k].get("warmth"),
                "vibe": outfit[k].get("vibe"),
            } for k in outfit.keys()}
        })

    prompt = f"""
너는 OOTD 코디 선택 심사위원이야.
아래 "사용자 취향 요약"을 강하게 반영해서, 날씨/상황에 가장 적합한 후보 1개를 골라.
반환은 JSON만.

- 날씨: {weather}
- 상황: {situation}
- 사용자 취향 요약: {taste_summary}
- 후보: {simplified}

반환:
{{"best_id":"c1","why":"짧게 1~2문장"}}
""".strip()

    try:
        resp = client.responses.create(model="gpt-4.1-mini", input=prompt)
        m = re.search(r"\{.*\}", resp.output_text, re.DOTALL)
        if not m:
            return None
        data = json.loads(m.group(0))
        return {"best_id": data.get("best_id"), "why": str(data.get("why",""))[:160]}
    except:
        return None

# =========================
# Recommendation
# =========================
def recommend(profile, closet, weather, situation, user_style_primary=None, do_ai_rerank=False):
    temp_bias = float(profile.get("temp_bias", 0.0))
    temp = weather.get("temperature")
    effective_temp = None if temp is None else (temp + temp_bias)

    wants_formal = any(x in situation for x in ["면접","발표","중요","출근","미팅","결혼식","장례식"])
    wants_comfy  = any(x in situation for x in ["집콕","학교","꾸안꾸","근처","수업"])
    wants_sporty = any(x in situation for x in ["운동","러닝"])
    wants_date   = any(x in situation for x in ["데이트","소개팅","첫만남"])

    item_scores = {}
    item_reasons = {}

    for it in closet:
        s = 0
        r = []
        name = it.get("name","")
        tp = it.get("type","")
        warmth = it.get("warmth","unknown")
        vibe = it.get("vibe","unknown")

        if effective_temp is not None:
            if effective_temp < 10:
                if tp == "outer": s += 4; r.append("추움→아우터 가산")
                if warmth == "thick": s += 2; r.append("thick→추운날 가산")
                if warmth == "thin": s -= 1; r.append("thin→추운날 감점")
            if effective_temp >= 22:
                if tp == "outer": s -= 3; r.append("더움→아우터 감점")
                if warmth == "thin": s += 1; r.append("thin→더운날 가산")
                if warmth == "thick": s -= 1; r.append("thick→더운날 감점")

        # situation + name keyword
        if wants_formal:
            if any(k in name for k in ["셔츠","슬랙","코트","자켓","블레이저","로퍼"]):
                s += 3; r.append("격식 키워드 매칭")
            if any(k in name for k in ["후드","트랙","조거","볼캡"]):
                s -= 2; r.append("격식에 캐주얼 감점")
        if wants_date and any(k in name for k in ["셔츠","니트","코트","자켓","로퍼","가디건"]):
            s += 2; r.append("데이트/첫만남 깔끔 가산")
        if wants_comfy and any(k in name for k in ["후드","맨투맨","티","청바지","가디건","스니커"]):
            s += 2; r.append("편한상황 캐주얼 가산")
        if wants_sporty:
            if tp == "shoes": s += 2; r.append("운동→신발 중요")
            if any(k in name for k in ["운동","트레이닝","러닝","조거","스니커"]):
                s += 3; r.append("운동 키워드 매칭")

        # optional style tag
        if user_style_primary:
            if it.get("primary_style") == user_style_primary or it.get("secondary_style") == user_style_primary:
                s += 1; r.append("선택 스타일 태그 일치")

        # vibe quick boost
        if wants_formal and vibe in ["formal","minimal","dandy"]:
            s += 1; r.append("격식상황 vibe 일치")
        if wants_sporty and vibe == "sporty":
            s += 1; r.append("운동상황 vibe 일치")
        if wants_date and vibe in ["dandy","minimal","cute"]:
            s += 1; r.append("데이트상황 vibe 일치")

        item_scores[it["id"]] = s
        item_reasons[it["id"]] = r if r else ["기본 점수"]

    def topk(cat, k=4):
        cand = [i for i in closet if i.get("type")==cat]
        cand.sort(key=lambda x: item_scores.get(x["id"], 0), reverse=True)
        return cand[:k]

    tops = topk("top", 4)
    bottoms = topk("bottom", 4)
    outers = topk("outer", 4)
    shoes = topk("shoes", 4)

    if not tops or not bottoms or not shoes:
        return None, [], {"error":"카테고리 부족(top/bottom/shoes 필요)"}, None

    cid = 0
    candidates = []

    include_outer_default = True
    if effective_temp is not None and effective_temp >= 22:
        include_outer_default = False

    outer_options = outers[:3] if outers else [None]
    for t in tops:
        for b in bottoms:
            for s in shoes:
                for o in outer_options:
                    outfit = {"top": t, "bottom": b, "shoes": s}
                    if o is not None:
                        outfit["outer"] = o

                    base = sum(item_scores.get(x["id"], 0) for x in outfit.values())
                    rs = []
                    for x in outfit.values():
                        rs += item_reasons.get(x["id"], [])

                    colors = {k: outfit[k].get("color","unknown") for k in outfit.keys()}
                    patterns = {k: outfit[k].get("pattern","unknown") for k in outfit.keys()}
                    vibes = {k: outfit[k].get("vibe","unknown") for k in outfit.keys()}

                    c_sc, c_rs = color_compat_score(colors)
                    p_sc, p_rs = pattern_compat_score(patterns)
                    v_sc, v_rs = vibe_fit_score(vibes, situation)

                    # ✅ 학습된 취향 점수(개인화)
                    t_sc, t_rs = taste_score_for_outfit(profile, outfit)

                    total = base + c_sc + p_sc + v_sc + t_sc

                    # 더운 날 outer 감점
                    if effective_temp is not None and effective_temp >= 22 and "outer" in outfit:
                        total -= 1
                        rs.append("더운날 아우터 감점")
                    if not include_outer_default and "outer" in outfit:
                        total -= 1

                    cid += 1
                    candidates.append({
                        "id": f"c{cid}",
                        "score": total,
                        "outfit": outfit,
                        "reasons": list(dict.fromkeys(rs + c_rs + p_rs + v_rs + t_rs))[:20]
                    })

    candidates.sort(key=lambda x: x["score"], reverse=True)
    top_candidates = candidates[:6]
    chosen = top_candidates[0] if top_candidates else None

    ai_pick = None
    if do_ai_rerank and client and top_candidates:
        ai_pick = ai_rerank_outfits(weather, situation, profile, top_candidates)
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
profile = load_profile()

st.markdown("<div class='smallcard'>", unsafe_allow_html=True)
st.write("👤 사용자:", user_id)
st.write("📍 위치:", loc_name if loc_name else f"{lat:.4f}, {lon:.4f}")
st.write("🌦️ 현재:", f"{weather.get('temperature')}°C", f"💨 바람 {weather.get('windspeed')}km/h")
st.caption(f"시간: {weather.get('time')}")
taste = profile.get("taste", {})
st.caption(f"⭐ 평균 별점: {taste.get('avg_rating',0):.2f} (누적 {taste.get('rating_count',0)}회)")
st.markdown("</div>", unsafe_allow_html=True)

# =========================
# 1) Register
# =========================
st.markdown("## 1) 📸 옷장 등록(사진 분석으로 색/패턴/분위기 저장)")
closet = load_closet()

col1, col2 = st.columns([1,1])
with col1:
    img = st.file_uploader("옷 사진 업로드(권장)", type=["jpg","png"], key="cloth_img")
    item_type = st.selectbox("카테고리", CATEGORIES, key="cloth_type")
    name = st.text_input("아이템 이름(권장)", placeholder="예: 검정 셔츠, 슬랙스", key="cloth_name")
    auto_analyze = st.toggle("저장 시 사진 자동 분석(Vision)", value=True)

with col2:
    st.markdown("### 🎯 스타일 태그(선택)")
    st.caption("스타일은 모르면 안 해도 돼요. (상황+AI가 메인)")
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

    st.markdown("### 🧠 AI 분석 미리보기")
    if img and use_openai and use_vision and client:
        if st.button("AI로 사진 분석(미리보기)"):
            meta = analyze_clothing_image_with_openai(img.getvalue(), fallback_name=name)
            st.session_state["vision_preview"] = meta
    meta_prev = st.session_state.get("vision_preview")
    if meta_prev:
        st.write(meta_prev)

if st.button("옷장에 저장"):
    closet = load_closet()
    iid = f"item_{datetime.now().timestamp()}"
    img_path = IMG_DIR / f"{iid}.png"

    if img:
        Image.open(img).save(img_path)
    else:
        make_placeholder_image(name if name else item_type, item_type, img_path)

    vision_meta = {"color":"unknown","pattern":"unknown","warmth":"unknown","vibe":"unknown","desc":""}
    if img and auto_analyze and use_openai and use_vision and client:
        vision_meta = analyze_clothing_image_with_openai(img.getvalue(), fallback_name=name)

    closet.append({
        "id": iid,
        "type": item_type,
        "name": name if name else item_type,
        "primary_style": primary_style,
        "secondary_style": secondary_style,
        "image": str(img_path),
        "color": vision_meta.get("color","unknown"),
        "pattern": vision_meta.get("pattern","unknown"),
        "warmth": vision_meta.get("warmth","unknown"),
        "vibe": vision_meta.get("vibe","unknown"),
        "desc": vision_meta.get("desc",""),
        "created_at": datetime.now().isoformat(),
        "source": "manual_photo"
    })
    save_closet(closet)
    st.success("저장 완료! (이제 추천에서 색/패턴/분위기/취향 학습이 반영돼요)")

st.markdown("---")

# =========================
# 2) Closet + delete confirm
# =========================
st.markdown("## 2) 👕 내 옷장")
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
# 3) Recommend
# =========================
st.markdown("## 3) 🗓️ 오늘 상황 기반 코디 추천 (취향 학습 반영)")
st.caption(f"개인 온도 보정(temp_bias): {profile.get('temp_bias',0):+.1f}°C")
situation = st.selectbox("오늘 상황", SITUATIONS)
st.caption("상황 힌트: " + situation_hint(situation))
optional_style = st.selectbox("스타일도 고려할래? (선택)", ["선택안함"] + STYLES, index=0)
user_style_primary = None if optional_style == "선택안함" else optional_style

if st.button("OOTD 추천"):
    profile = load_profile()
    closet_now = load_closet()
    chosen, top_candidates, meta, ai_pick = recommend(
        profile=profile,
        closet=closet_now,
        weather=weather,
        situation=situation,
        user_style_primary=user_style_primary,
        do_ai_rerank=(use_openai and use_ai_rerank and client)
    )
    if not chosen:
        st.error("추천 실패: top/bottom/shoes를 최소 1개씩 등록해줘!")
        st.stop()

    outfit = chosen["outfit"]
    reasons = chosen["reasons"]

    st.session_state["last_outfit"] = outfit
    st.session_state["last_reasons"] = reasons
    st.session_state["last_meta"] = meta
    st.session_state["last_ctx"] = {"weather": weather, "situation": situation, "user_style_primary": user_style_primary}

    st.markdown("### ✨ 추천 결과")
    for k, v in outfit.items():
        st.markdown("<div class='card'>", unsafe_allow_html=True)
        if v.get("image"):
            st.image(v["image"], width=220)
        st.markdown(f"**{k.upper()} | {v.get('name','')}**")
        st.caption(f"color:{v.get('color')} | pattern:{v.get('pattern')} | warmth:{v.get('warmth')} | vibe:{v.get('vibe')}")
        if v.get("desc"):
            st.caption("AI: " + v["desc"])
        st.markdown("</div>", unsafe_allow_html=True)

    st.markdown("### ✅ 추천 근거(요약)")
    for rr in reasons[:14]:
        st.caption("• " + rr)

    if ai_pick and ai_pick.get("why"):
        st.markdown("### 🤖 AI 리랭크 이유")
        st.write(ai_pick["why"])

    with st.expander("상위 후보 5개(점수)", expanded=False):
        for c in top_candidates[:5]:
            o = c["outfit"]
            st.write(f"- 점수 {c['score']}: ",
                     {k: o[k].get("name") for k in o.keys()})

st.markdown("---")

# =========================
# 4) Feedback (AI 중심 강화)
# =========================
st.markdown("## 4) ⭐ 피드백 (온도 + 별점 + 색/패턴/분위기)")
last_outfit = st.session_state.get("last_outfit")
if not last_outfit:
    st.info("먼저 3)에서 OOTD 추천을 받아야 피드백을 남길 수 있어요.")
else:
    # ✅ 전체 만족도 별점
    rating = st.slider("전체 만족도(별점)", 1, 5, 4)

    # ✅ 기존 온도
    fb_temp = st.radio("체감 온도", ["추움", "딱 좋음", "더움"], horizontal=True)

    # ✅ 스타일 피드백(학습)
    colA, colB, colC = st.columns(3)
    with colA:
        color_fb = st.radio("색 조합", ["좋음", "상관없음", "별로"], index=1, horizontal=True)
    with colB:
        pattern_fb = st.radio("패턴 조합", ["좋음", "상관없음", "별로"], index=1, horizontal=True)
    with colC:
        vibe_fb = st.radio("분위기(vibe)", ["좋음", "상관없음", "별로"], index=1, horizontal=True)

    note = st.text_input("한 줄 코멘트(선택)", placeholder="예: 색은 좋은데 패턴이 과했어 / 더 포멀했으면")

    if st.button("피드백 저장"):
        logs = load_feedback()
        ctx = st.session_state.get("last_ctx", {})
        meta = st.session_state.get("last_meta", {})
        reasons = st.session_state.get("last_reasons", [])

        logs.append({
            "time": datetime.now().isoformat(),
            "rating": rating,
            "temp_feedback": fb_temp,
            "style_feedback": {"color": color_fb, "pattern": pattern_fb, "vibe": vibe_fb},
            "note": note,
            "context": ctx,
            "meta": meta,
            "reasons": reasons,
            "outfit": {k: v.get("id") for k, v in last_outfit.items()}
        })
        save_feedback(logs)

        profile = load_profile()
        profile = update_taste_from_feedback(profile, last_outfit, rating, fb_temp, color_fb, pattern_fb, vibe_fb)
        save_profile(profile)

        st.success("저장 완료! 이제 다음 추천부터 색/패턴/분위기 취향까지 반영돼요 ✅")
        st.session_state.pop("last_outfit", None)
        st.rerun()

st.markdown("---")

# =========================
# 5) Taste dashboard
# =========================
st.markdown("## 5) 📊 내 취향(학습 결과)")
profile = load_profile()
taste = profile.get("taste", {})
st.write("⭐ 평균 별점:", taste.get("avg_rating", 0), "(누적", taste.get("rating_count", 0), "회)")
st.write("🌡️ 온도 보정값:", f"{profile.get('temp_bias',0):+.1f}°C")

def top_items(d, n=6):
    return sorted(d.items(), key=lambda x: x[1], reverse=True)[:n]

col1, col2, col3 = st.columns(3)
with col1:
    st.markdown("### 🎨 색")
    st.write("선호:", top_items(taste.get("color_pref", {})))
    st.write("비선호:", top_items(taste.get("color_avoid", {})))
with col2:
    st.markdown("### 🧩 패턴")
    st.write("선호:", top_items(taste.get("pattern_pref", {})))
    st.write("비선호:", top_items(taste.get("pattern_avoid", {})))
with col3:
    st.markdown("### 🧠 분위기(vibe)")
    st.write("선호:", top_items(taste.get("vibe_pref", {})))
    st.write("비선호:", top_items(taste.get("vibe_avoid", {})))

logs = load_feedback()
if logs:
    st.caption(f"최근 피드백 {min(len(logs), 100)}개를 기반으로 취향이 누적됩니다.")
