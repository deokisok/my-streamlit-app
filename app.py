import streamlit as st
import json, os, re, csv
from pathlib import Path
from datetime import datetime
import requests
from PIL import Image

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
# Helpers: JSON storage
# =========================
def load_json(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except:
        return default

def save_json(path: Path, obj):
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")

# =========================
# Sidebar: User + API + Location
# =========================
with st.sidebar:
    st.header("👤 사용자")
    user_id = st.text_input("사용자 ID(닉네임/이메일)", value="guest")
    user_id = re.sub(r"[^a-zA-Z0-9._-]", "_", user_id).strip() or "guest"
    st.caption("다른 ID를 입력하면 옷장/피드백이 완전히 분리 저장돼요.")

    st.markdown("---")
    st.header("🔑 API 설정")
    openai_key = st.text_input("OpenAI API Key", type="password", value=os.environ.get("OPENAI_API_KEY", ""))
    use_openai = st.toggle("OpenAI 기능 사용(상황기반 추천/설명)", value=bool(openai_key))
    if openai_key:
        os.environ["OPENAI_API_KEY"] = openai_key

    st.markdown("---")
    st.header("📍 위치/날씨")
    lat = st.number_input("위도(lat)", value=37.5665, format="%.6f")
    lon = st.number_input("경도(lon)", value=126.9780, format="%.6f")
    st.caption("팁: 휴대폰 GPS 값을 입력하면 더 정확해요.")

# =========================
# User-scoped Data Paths (요구사항 1번)
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
    PROFILE.write_text(json.dumps({"temp_bias": 0.0, "situation_pref": {}}, ensure_ascii=False, indent=2), encoding="utf-8")

def load_closet():
    return load_json(CLOSET, [])

def save_closet(c):
    save_json(CLOSET, c)

def load_feedback():
    return load_json(FEEDBACK, [])

def save_feedback(fb):
    save_json(FEEDBACK, fb)

def load_profile():
    return load_json(PROFILE, {"temp_bias": 0.0, "situation_pref": {}})

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
        data = r.json()
        return data.get("display_name", "")
    except:
        return ""

def get_weather(lat, lon):
    url = "https://api.open-meteo.com/v1/forecast"
    params = {
        "latitude": lat,
        "longitude": lon,
        "current_weather": "true",
        "timezone": "auto"
    }
    data = requests.get(url, params=params, timeout=10).json()
    w = data.get("current_weather", {}) or {}
    return {
        "temperature": w.get("temperature"),
        "windspeed": w.get("windspeed"),
        "weathercode": w.get("weathercode"),
        "time": w.get("time"),
    }

# =========================
# Closet item schema
# - style is OPTIONAL now (can be empty)
# =========================
CATEGORIES = ["top", "bottom", "outer", "shoes"]
STYLES = ["casual", "dandy", "hiphop", "sporty"]  # optional field

# =========================
# Situations (핵심: 사용자들이 더 잘 고를 수 있는 선택지)
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

def situation_hint(situation: str) -> str:
    """간단한 힌트(LLM 없이도 UX)"""
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
    return mapping.get(situation, "")

# =========================
# OpenAI: Situation-based guidance (optional)
# - Generates weighting rules for recommendation.
# =========================
def build_guidance_with_openai(weather, situation, closet_summary):
    """
    Returns dict of weights/preferences
    Example JSON:
    {
      "prefer": ["outer","shoes_clean","simple_color"],
      "avoid": ["flashy_logo"],
      "tone": "clean",
      "extra_note": "..."
    }
    """
    if not client:
        return None

    prompt = f"""
너는 '오늘 상황' 기반 코디 추천 룰을 만드는 도우미야.
아래 정보로 오늘 추천에 반영할 가이드(선호/회피/톤)를 만들어줘.
반환은 JSON만.

- 날씨: {weather}
- 오늘 상황: {situation}
- 옷장 요약(카테고리/이름만): {closet_summary}

JSON 스키마:
{{
  "tone": "clean|comfy|sporty|formal|street|minimal",
  "prefer_keywords": ["...","..."],   // 옷 이름에 포함되면 가산할 키워드
  "avoid_keywords": ["...","..."],    // 옷 이름에 포함되면 감점할 키워드
  "notes": "한 줄 조언"
}}
""".strip()

    try:
        resp = client.responses.create(model="gpt-4.1-mini", input=prompt)
        text = resp.output_text
        m = re.search(r"\{.*\}", text, re.DOTALL)
        if not m:
            return None
        data = json.loads(m.group(0))
        # sanitize
        tone = data.get("tone", "clean")
        if tone not in ["clean","comfy","sporty","formal","street","minimal"]:
            tone = "clean"
        pk = data.get("prefer_keywords", [])
        ak = data.get("avoid_keywords", [])
        pk = [str(x)[:30] for x in pk][:8] if isinstance(pk, list) else []
        ak = [str(x)[:30] for x in ak][:8] if isinstance(ak, list) else []
        notes = str(data.get("notes",""))[:120]
        return {"tone": tone, "prefer_keywords": pk, "avoid_keywords": ak, "notes": notes}
    except:
        return None

def explain_outfit_ai(weather, situation, outfit, reasons, meta, guidance):
    if not client:
        return None
    prompt = f"""
OOTD 앱 추천 결과를 3줄로 설명해줘. 인스타 느낌으로 짧고 친근하게.
오늘 '상황'을 중심으로 왜 이 조합인지 말해줘.

- 날씨: {weather}
- 상황: {situation}
- 추천 코디: { {k:v['name'] for k,v in outfit.items()} }
- 규칙 기반 이유: {reasons}
- 개인 보정(추움/더움 피드백): {meta}
- 상황 가이드: {guidance}

3줄 텍스트만 반환.
""".strip()
    try:
        resp = client.responses.create(model="gpt-4.1-mini", input=prompt)
        return resp.output_text.strip()
    except:
        return None

# =========================
# Recommendation Engine
# - style is optional (not required)
# - situation is primary driver
# - feedback temp_bias adjusts warmth preference
# - guidance keywords optionally from OpenAI
# =========================
def recommend(closet, weather, situation, temp_bias=0.0, guidance=None, user_style_primary=None):
    """
    guidance: dict from OpenAI (tone, prefer_keywords, avoid_keywords)
    user_style_primary: optional style chosen by user (not required)
    """
    temp = weather.get("temperature")
    effective_temp = None if temp is None else (temp + temp_bias)

    prefer_keywords = (guidance or {}).get("prefer_keywords", [])
    avoid_keywords = (guidance or {}).get("avoid_keywords", [])

    scores, reasons = {}, {}

    # situation heuristics (no-AI baseline)
    sit = situation
    wants_formal = any(x in sit for x in ["면접", "발표", "중요", "출근", "미팅", "결혼식", "장례식"])
    wants_comfy = any(x in sit for x in ["집콕", "학교", "꾸안꾸", "근처", "수업"])
    wants_sporty = "운동" in sit or "러닝" in sit
    wants_date = "데이트" in sit or "소개팅" in sit or "첫만남" in sit

    for item in closet:
        s = 0
        r = []

        name = item.get("name", "")
        tp = item.get("type")

        # Weather warmth logic
        if effective_temp is not None:
            if effective_temp < 10 and tp == "outer":
                s += 4; r.append("기온 낮음 → 아우터 추천(개인보정 포함)")
            if effective_temp >= 22 and tp == "outer":
                s -= 3; r.append("기온 높음 → 아우터 감점(개인보정 포함)")

        # Situation baseline scoring
        if wants_sporty:
            # sporty: sneakers/training keywords bonus
            if tp == "shoes":
                s += 2; r.append("운동/러닝 → 신발 중요")
            if any(k in name for k in ["운동", "트레이닝", "러닝", "조거", "스니커", "레깅스"]):
                s += 3; r.append("운동 관련 키워드 매칭")
        if wants_formal:
            if any(k in name for k in ["셔츠", "슬랙", "코트", "자켓", "블레이저", "로퍼"]):
                s += 3; r.append("격식/단정 키워드 매칭")
            if any(k in name for k in ["후드", "트랙", "조거", "볼캡"]):
                s -= 2; r.append("격식 상황엔 캐주얼 요소 감점")
        if wants_date:
            if any(k in name for k in ["셔츠", "니트", "코트", "자켓", "로퍼", "가디건"]):
                s += 2; r.append("데이트/첫만남 → 깔끔한 아이템 가산")
        if wants_comfy:
            if any(k in name for k in ["후드", "맨투맨", "티", "청바지", "가디건", "스니커"]):
                s += 2; r.append("편한 상황 → 캐주얼 아이템 가산")

        # Optional user style (not required)
        if user_style_primary:
            if item.get("primary_style") == user_style_primary or item.get("secondary_style") == user_style_primary:
                s += 1; r.append("선택한 스타일과 일부 일치(선택사항)")

        # OpenAI guidance keywords
        for kw in prefer_keywords:
            if kw and kw in name:
                s += 2; r.append(f"AI 가이드 선호 키워드: {kw}")
        for kw in avoid_keywords:
            if kw and kw in name:
                s -= 2; r.append(f"AI 가이드 회피 키워드: {kw}")

        scores[item["id"]] = s
        reasons[item["id"]] = r if r else ["기본 점수 계산"]

    # pick best per category
    outfit = {}
    for cat in ["top", "bottom", "outer", "shoes"]:
        candidates = [i for i in closet if i.get("type") == cat]
        if candidates:
            outfit[cat] = max(candidates, key=lambda x: scores.get(x["id"], 0))

    meta = {"temp_bias": temp_bias, "effective_temp": effective_temp}
    return outfit, reasons, meta

# =========================
# UI Header: weather/location
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
st.markdown("## 1) 📸 옷장 등록 (사진 선택 / 최소 입력)")
colA, colB = st.columns([1, 1])

with colA:
    img = st.file_uploader("사진 업로드(선택)", type=["jpg", "png"])
    item_type = st.selectbox("카테고리", CATEGORIES)
    name = st.text_input("아이템 이름(권장)", placeholder="예: 검정 셔츠, 슬랙스, 조거 팬츠")

with colB:
    st.markdown("### 🎯 스타일 태그(선택 사항)")
    st.caption("모르면 안 해도 돼요. 상황 기반 추천이 메인입니다.")
    style_use = st.toggle("스타일 태그 입력(선택)", value=False)
    primary_style = None
    secondary_style = None

    if style_use:
        primary_style = st.selectbox("주 스타일(선택)", ["선택안함"] + STYLES, index=0)
        secondary_style_pick = st.selectbox("보조 스타일(선택)", ["없음"] + STYLES, index=0)
        if primary_style == "선택안함":
            primary_style = None
        secondary_style = None if secondary_style_pick == "없음" else secondary_style_pick
        if primary_style and secondary_style == primary_style:
            secondary_style = None
            st.info("보조 스타일이 주 스타일과 같아서 '없음' 처리했어.")

if st.button("옷장에 저장"):
    closet = load_closet()
    iid = f"item_{datetime.now().timestamp()}"
    img_path = None

    if img:
        image = Image.open(img)
        img_path = IMG_DIR / f"{iid}.png"
        image.save(img_path)

    closet.append({
        "id": iid,
        "type": item_type,
        "name": name if name else item_type,
        "primary_style": primary_style,      # can be None
        "secondary_style": secondary_style,  # can be None
        "image": str(img_path) if img_path else None,
        "created_at": datetime.now().isoformat()
    })
    save_closet(closet)
    st.success("저장 완료! (스타일/사진은 선택 사항)")

st.markdown("---")

# =========================
# 2) Closet view
# =========================
st.markdown("## 2) 👕 내 옷장")
closet = load_closet()
if not closet:
    st.info("아직 옷이 없어. 위에서 등록해줘!")
else:
    cols = st.columns(4)
    for i, item in enumerate(closet):
        with cols[i % 4]:
            if item.get("image"):
                st.image(item["image"], use_container_width=True)
            else:
                st.markdown("<div class='smallcard'>📦 이미지 없음</div>", unsafe_allow_html=True)
            ps = item.get("primary_style") or "-"
            ss = item.get("secondary_style") or "-"
            st.caption(f"{item['type']} | 주:{ps} / 보조:{ss}")
            st.caption(item["name"])

st.markdown("---")

# =========================
# 3) Situation-based recommendation (핵심 변경)
# =========================
st.markdown("## 3) 🗓️ 오늘 상황 기반 코디 추천")
st.caption(f"개인 온도 보정값(temp_bias): {temp_bias:+.1f}°C  (피드백으로 자동 학습)")

situation = st.selectbox("오늘 상황을 선택해줘", SITUATIONS)
st.caption("상황 힌트: " + situation_hint(situation))

# Optional style input for users who know styles
optional_style = st.selectbox("스타일도 고려할래? (선택)", ["선택안함"] + STYLES, index=0)
user_style_primary = None if optional_style == "선택안함" else optional_style

# Build OpenAI guidance (optional)
guidance = None
if use_openai and client:
    with st.expander("🤖 OpenAI 상황 가이드(자동 생성) 보기", expanded=False):
        closet_summary = [{"type": i.get("type"), "name": i.get("name")} for i in closet][:50]
        if st.button("상황 가이드 생성(추천 정확도↑)"):
            guidance = build_guidance_with_openai(weather, situation, closet_summary)
            st.session_state["guidance"] = guidance

        guidance = st.session_state.get("guidance")
        if guidance:
            st.write(guidance.get("notes", ""))
            st.caption(f"tone: {guidance.get('tone')}")
            st.write("선호 키워드:", guidance.get("prefer_keywords", []))
            st.write("회피 키워드:", guidance.get("avoid_keywords", []))
        else:
            st.info("버튼을 누르면 상황 기반 추천 기준을 AI가 만들어줘요(무료 API 아님: OpenAI 필요).")

if st.button("OOTD 추천"):
    if not closet:
        st.error("옷장이 비어있어. 먼저 옷을 등록해줘!")
        st.stop()

    # use guidance if exists in session
    guidance = st.session_state.get("guidance", None) if (use_openai and client) else None

    outfit, reasons, meta = recommend(
        closet=closet,
        weather=weather,
        situation=situation,
        temp_bias=temp_bias,
        guidance=guidance,
        user_style_primary=user_style_primary
    )

    st.session_state["last_outfit"] = outfit
    st.session_state["last_reasons"] = reasons
    st.session_state["last_meta"] = meta
    st.session_state["last_ctx"] = {
        "user_id": user_id,
        "lat": lat, "lon": lon,
        "weather": weather,
        "situation": situation,
        "user_style_primary": user_style_primary,
        "guidance": guidance
    }

    st.markdown("### ✨ 추천 결과")
    for k, v in outfit.items():
        st.markdown("<div class='card'>", unsafe_allow_html=True)
        if v.get("image"):
            st.image(v["image"], width=180)
        else:
            st.write("📦 이미지 없음")
        st.markdown(f"**{k.upper()} | {v['name']}**")
        ps = v.get("primary_style") or "-"
        ss = v.get("secondary_style") or "-"
        st.caption(f"태그(선택): 주:{ps} / 보조:{ss}")
        for r in reasons.get(v["id"], []):
            st.caption("• " + r)
        st.markdown("</div>", unsafe_allow_html=True)

    if use_openai and client:
        ai_msg = explain_outfit_ai(weather, situation, outfit, reasons, meta, guidance)
        if ai_msg:
            st.markdown("### 🧠 AI 요약")
            st.write(ai_msg)

# =========================
# 4) Feedback loop (추움/딱좋음/더움)
# =========================
last_outfit = st.session_state.get("last_outfit")
if last_outfit:
    st.markdown("### 🧊🔥 오늘 추천, 어땠어?")
    fb = st.radio("체감 온도 피드백", ["추움", "딱 좋음", "더움"], horizontal=True)
    note = st.text_input("한 줄 코멘트(선택)", placeholder="예: 아우터가 너무 두꺼웠어 / 상의가 더 단정했으면")

    if st.button("피드백 저장"):
        logs = load_feedback()
        ctx = st.session_state.get("last_ctx", {})
        meta = st.session_state.get("last_meta", {})

        logs.append({
            "time": datetime.now().isoformat(),
            "feedback": fb,
            "note": note,
            "context": ctx,
            "meta": meta,
            "outfit": {k: v.get("id") for k, v in last_outfit.items()}
        })
        save_feedback(logs)

        # update personal temp_bias
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
    st.caption("추움이 많으면 더 따뜻하게, 더움이 많으면 더 가볍게 추천하도록 자동 보정돼요.")
