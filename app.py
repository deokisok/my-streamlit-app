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
# Data
# =========================
DATA = Path("data")
IMG = DATA / "images"
CLOSET = DATA / "closet.json"
FEEDBACK = DATA / "feedback.json"
PROFILE = DATA / "profile.json"

DATA.mkdir(exist_ok=True)
IMG.mkdir(exist_ok=True)
if not CLOSET.exists():
    CLOSET.write_text("[]", encoding="utf-8")
if not FEEDBACK.exists():
    FEEDBACK.write_text("[]", encoding="utf-8")
if not PROFILE.exists():
    PROFILE.write_text(json.dumps({"temp_bias": 0.0}, ensure_ascii=False, indent=2), encoding="utf-8")

def load_json(path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except:
        return default

def save_json(path, obj):
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")

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
# Sidebar: API Key & Settings
# =========================
with st.sidebar:
    st.header("🔑 API 설정")
    openai_key = st.text_input("OpenAI API Key", type="password", value=os.environ.get("OPENAI_API_KEY", ""))
    use_openai = st.toggle("OpenAI 기능 사용(스타일/설명/텍스트추출)", value=bool(openai_key))
    if openai_key:
        os.environ["OPENAI_API_KEY"] = openai_key

    st.markdown("---")
    st.header("📍 위치/날씨")
    # 기본값: 서울
    lat = st.number_input("위도(lat)", value=37.5665, format="%.6f")
    lon = st.number_input("경도(lon)", value=126.9780, format="%.6f")
    st.caption("팁: 휴대폰 GPS 값을 입력하면 더 정확해요.")

# OpenAI client (옵션)
client = None
if use_openai and openai_key:
    try:
        from openai import OpenAI
        client = OpenAI()
    except:
        client = None

# =========================
# Free APIs
# 1) Open-Meteo weather (free)
# 2) Nominatim reverse geocoding (free, keyless)
# =========================
def reverse_geocode(lat, lon):
    """
    Nominatim (OpenStreetMap) - free keyless reverse geocoding
    """
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
    """
    Open-Meteo current weather (free)
    """
    url = "https://api.open-meteo.com/v1/forecast"
    params = {
        "latitude": lat,
        "longitude": lon,
        "current_weather": "true",
        "timezone": "auto"
    }
    w = requests.get(url, params=params, timeout=10).json().get("current_weather", {})
    # 예: temperature, windspeed, weathercode
    return {
        "temperature": w.get("temperature"),
        "windspeed": w.get("windspeed"),
        "weathercode": w.get("weathercode"),
        "time": w.get("time")
    }

# =========================
# Style (Rule + OpenAI)
# 주 스타일 1개 + 보조 스타일 0~1개
# =========================
STYLES = ["casual", "dandy", "hiphop", "sporty"]

STYLE_KEYWORDS = {
    "dandy": ["셔츠", "슬랙", "코트", "로퍼", "자켓", "블레이저"],
    "casual": ["후드", "맨투맨", "티", "청바지", "가디건"],
    "hiphop": ["오버", "조거", "트랙", "볼캡", "와이드"],
    "sporty": ["운동", "트레이닝", "러닝", "스니커", "져지"]
}

def suggest_styles_rule(name):
    found = []
    for style, words in STYLE_KEYWORDS.items():
        for w in words:
            if w.lower() in name.lower():
                found.append(style)
                break
    found = list(dict.fromkeys(found))  # preserve order, unique
    if not found:
        return ("casual", None)
    primary = found[0]
    secondary = found[1] if len(found) > 1 else None
    return (primary, secondary)

def suggest_styles_openai(name):
    """
    Return: (primary, secondary)
    JSON format expected: {"primary":"dandy","secondary":"casual"}  (secondary can be null)
    """
    if not client or not name.strip():
        return ("casual", None)

    prompt = f"""
너는 패션 스타일 태깅 도우미야.
아래 의류 이름을 보고 스타일을 추천해줘.
스타일은 반드시 다음 4개 중에서만 선택: {STYLES}

규칙:
- primary(주 스타일) 1개는 필수
- secondary(보조 스타일) 0~1개 (없으면 null)
- 결과는 JSON만 반환

의류 이름: {name}
""".strip()

    try:
        resp = client.responses.create(
            model="gpt-4.1-mini",
            input=prompt,
        )
        text = resp.output_text
        m = re.search(r"\{.*\}", text, re.DOTALL)
        if not m:
            return ("casual", None)
        data = json.loads(m.group(0))
        primary = data.get("primary", "casual")
        secondary = data.get("secondary", None)
        if primary not in STYLES:
            primary = "casual"
        if secondary not in STYLES:
            secondary = None
        if secondary == primary:
            secondary = None
        return (primary, secondary)
    except:
        return ("casual", None)

# =========================
# Bulk import options (no vendor API)
# - CSV upload (type,name,primary_style,secondary_style)
# - Paste order history text -> extract items via OpenAI (optional)
# =========================
def parse_csv_bytes(file_bytes):
    text = file_bytes.decode("utf-8", errors="ignore").splitlines()
    reader = csv.DictReader(text)
    items = []
    for row in reader:
        items.append({
            "type": (row.get("type") or "").strip(),
            "name": (row.get("name") or "").strip(),
            "primary_style": (row.get("primary_style") or "").strip(),
            "secondary_style": (row.get("secondary_style") or "").strip(),
        })
    return items

def extract_items_from_text_with_openai(order_text):
    """
    User pastes order/purchase text -> OpenAI extracts clothing items.
    Return list of dict: {name, type(optional)}
    """
    if not client or not order_text.strip():
        return []

    prompt = f"""
너는 구매내역 텍스트에서 '의류/신발' 상품명만 추출하는 도우미야.
아래 텍스트에서 옷/신발로 보이는 항목을 최대 20개까지 뽑아줘.
가능하면 type도 추정해줘: top/bottom/outer/shoes 중 하나. 모르면 null.
반환은 JSON만: {{"items":[{{"name":"...","type":"top"}}, ...]}}.

텍스트:
{order_text}
""".strip()

    try:
        resp = client.responses.create(model="gpt-4.1-mini", input=prompt)
        text = resp.output_text
        m = re.search(r"\{.*\}", text, re.DOTALL)
        if not m:
            return []
        data = json.loads(m.group(0))
        items = data.get("items", [])
        clean = []
        for it in items:
            nm = (it.get("name") or "").strip()
            tp = it.get("type")
            if tp not in ["top","bottom","outer","shoes"]:
                tp = None
            if nm:
                clean.append({"name": nm, "type": tp})
        return clean[:20]
    except:
        return []

# =========================
# Recommendation Engine + Personal temperature bias from feedback
# =========================
def temperature_bucket(temp):
    if temp is None:
        return "unknown"
    if temp < 5:
        return "very_cold"
    if temp < 12:
        return "cold"
    if temp < 20:
        return "mild"
    if temp < 26:
        return "warm"
    return "hot"

def recommend(closet, temp, today_primary, today_secondary, temp_bias=0.0):
    """
    temp_bias: user warmth preference adjustment (- colder, + warmer)
    We'll adjust effective temp: temp + temp_bias
    """
    effective_temp = None if temp is None else (temp + temp_bias)

    scores, reasons = {}, {}

    for item in closet:
        s, r = 0, []

        # weather: outer preference
        if effective_temp is not None and effective_temp < 10 and item["type"] == "outer":
            s += 3; r.append("기온 낮음 → 아우터 가산(개인보정 반영)")
        if effective_temp is not None and effective_temp >= 22 and item["type"] == "outer":
            s -= 2; r.append("기온 높음 → 아우터 감점(개인보정 반영)")

        # style scoring: primary strong, secondary mild
        item_primary = item.get("primary_style")
        item_secondary = item.get("secondary_style")

        if item_primary == today_primary:
            s += 4; r.append(f"주 스타일({today_primary}) 일치")
        elif today_secondary and item_primary == today_secondary:
            s += 2; r.append(f"보조 스타일({today_secondary}) 일치")
        else:
            s -= 1; r.append("스타일 일치도 낮음")

        # if secondary matches too, small bonus
        if today_secondary and (item_secondary == today_secondary or item_secondary == today_primary):
            s += 1; r.append("보조 스타일 매칭 보너스")

        scores[item["id"]] = s
        reasons[item["id"]] = r

    outfit = {}
    for t in ["top","bottom","outer","shoes"]:
        items = [i for i in closet if i["type"] == t]
        if items:
            outfit[t] = max(items, key=lambda x: scores[x["id"]])

    meta = {
        "effective_temp": effective_temp,
        "temp_bias": temp_bias,
        "bucket": temperature_bucket(effective_temp),
    }
    return outfit, reasons, meta

# =========================
# AI Explanation (optional)
# =========================
def explain_outfit_ai(weather, today_primary, today_secondary, outfit, reasons, meta):
    if not client:
        return None
    prompt = f"""
OOTD 앱 추천 결과를 사용자가 납득하기 쉽게 3줄로 설명해줘.
톤: 짧고 친근한 인스타 느낌.
주 스타일/보조 스타일을 반영했다고 말해줘.

- 날씨: {weather}
- 주 스타일: {today_primary}
- 보조 스타일: {today_secondary}
- 추천 코디: { {k:v['name'] for k,v in outfit.items()} }
- 규칙 기반 근거: {reasons}
- 개인 보정(추움/더움 피드백 기반): {meta}

3줄 텍스트만 반환.
""".strip()

    try:
        resp = client.responses.create(model="gpt-4.1-mini", input=prompt)
        return resp.output_text.strip()
    except:
        return None

# =========================
# UI
# =========================
st.title("🧥 ootd")

# Header: location + weather
loc_name = reverse_geocode(lat, lon)
weather = get_weather(lat, lon)
with st.container():
    st.markdown("<div class='smallcard'>", unsafe_allow_html=True)
    st.write("📍 위치:", loc_name if loc_name else f"{lat:.4f}, {lon:.4f}")
    st.write("🌦️ 현재 날씨:", f"{weather.get('temperature')}°C", f"💨 바람 {weather.get('windspeed')}km/h")
    st.caption(f"시간: {weather.get('time')}")
    st.markdown("</div>", unsafe_allow_html=True)

profile = load_profile()

# -------- 1) Closet register --------
st.markdown("## 1) 📸 옷장 등록 (사진/간단 입력)")
img = st.file_uploader("사진 업로드(선택)", type=["jpg","png"])
item_type = st.selectbox("카테고리", ["top","bottom","outer","shoes"])
name = st.text_input("이름(권장)", placeholder="예: 검정 셔츠, 슬랙스, 조거 팬츠")

# AI suggested style (primary + secondary)
primary, secondary = ("casual", None)
if name:
    if use_openai and client:
        primary, secondary = suggest_styles_openai(name)
        st.caption(f"🤖 AI 추천: 주 스타일={primary} / 보조 스타일={secondary if secondary else '없음'}")
    else:
        primary, secondary = suggest_styles_rule(name)
        st.caption(f"🧠 규칙 추천: 주 스타일={primary} / 보조 스타일={secondary if secondary else '없음'}")

col1, col2 = st.columns(2)
with col1:
    primary_style = st.selectbox("주 스타일(1개)", STYLES, index=STYLES.index(primary) if primary in STYLES else 0)
with col2:
    secondary_options = ["없음"] + STYLES
    default_sec = "없음" if not secondary else secondary
    secondary_style_pick = st.selectbox("보조 스타일(0~1개)", secondary_options, index=secondary_options.index(default_sec))

secondary_style = None if secondary_style_pick == "없음" else secondary_style_pick
if secondary_style == primary_style:
    secondary_style = None
    st.info("보조 스타일이 주 스타일과 같아서 '없음'으로 처리했어.")

if st.button("옷장에 저장"):
    closet = load_closet()

    iid = f"item_{datetime.now().timestamp()}"
    img_path = None

    if img:
        image = Image.open(img)
        img_path = IMG / f"{iid}.png"
        image.save(img_path)

    closet.append({
        "id": iid,
        "type": item_type,
        "name": name if name else item_type,
        "primary_style": primary_style,
        "secondary_style": secondary_style,
        "image": str(img_path) if img_path else None,
        "created_at": datetime.now().isoformat()
    })
    save_closet(closet)
    st.success("옷 저장 완료! (사진은 선택 사항)")

st.markdown("---")

# -------- 1-2) Bulk import --------
st.markdown("## 1-2) 🧾 대량 등록 (CSV / 구매내역 텍스트)")
st.caption("패션 앱(무신사 등) 직접 연동은 보통 공식 API/권한이 없어 MVP에서 어렵고, 대신 CSV/텍스트 방식으로 현실적으로 확장합니다.")

tab1, tab2 = st.tabs(["CSV 업로드", "구매내역 텍스트 붙여넣기(OpenAI)"])

with tab1:
    st.write("CSV 컬럼 예시: `type,name,primary_style,secondary_style`")
    csv_file = st.file_uploader("CSV 업로드", type=["csv"])
    if csv_file and st.button("CSV로 옷장 추가"):
        rows = parse_csv_bytes(csv_file.getvalue())
        closet = load_closet()
        added = 0
        for r in rows:
            tp = r["type"]
            nm = r["name"]
            ps = r["primary_style"] if r["primary_style"] in STYLES else "casual"
            ss = r["secondary_style"] if r["secondary_style"] in STYLES else None
            if tp in ["top","bottom","outer","shoes"] and nm:
                iid = f"item_{datetime.now().timestamp()}_{added}"
                closet.append({
                    "id": iid,
                    "type": tp,
                    "name": nm,
                    "primary_style": ps,
                    "secondary_style": ss if ss != ps else None,
                    "image": None,
                    "created_at": datetime.now().isoformat()
                })
                added += 1
        save_closet(closet)
        st.success(f"CSV로 {added}개 아이템을 추가했어!")

with tab2:
    st.write("예: 주문내역 텍스트(상품명/옵션 포함)를 통째로 붙여넣기")
    order_text = st.text_area("구매내역 텍스트", height=160, placeholder="주문내역을 복사해서 붙여넣어줘.")
    if st.button("텍스트에서 아이템 추출"):
        if not (use_openai and client):
            st.error("이 기능은 OpenAI API Key가 필요해. 사이드바에서 입력하고 토글 켜줘.")
        else:
            items = extract_items_from_text_with_openai(order_text)
            if not items:
                st.warning("추출 결과가 없었어. 텍스트에 상품명이 포함되어 있는지 확인해줘.")
            else:
                st.session_state["extracted_items"] = items
                st.success(f"{len(items)}개 아이템을 추출했어. 아래에서 타입/스타일을 확인하고 추가해줘!")

    items = st.session_state.get("extracted_items", [])
    if items:
        st.write("추출된 아이템(수정 가능):")
        closet = load_closet()
        for idx, it in enumerate(items):
            with st.expander(f"{idx+1}. {it['name']}"):
                tp = st.selectbox("카테고리", ["top","bottom","outer","shoes"], index=0, key=f"ex_tp_{idx}")
                nm = st.text_input("이름", value=it["name"], key=f"ex_nm_{idx}")

                # style suggestion from name
                p, s = suggest_styles_openai(nm) if (use_openai and client) else suggest_styles_rule(nm)
                ps = st.selectbox("주 스타일", STYLES, index=STYLES.index(p), key=f"ex_ps_{idx}")
                ss_opt = ["없음"] + STYLES
                ss_default = "없음" if not s else s
                ss_pick = st.selectbox("보조 스타일", ss_opt, index=ss_opt.index(ss_default), key=f"ex_ss_{idx}")
                ss = None if ss_pick == "없음" else ss_pick
                if ss == ps:
                    ss = None

                if st.button("이 아이템 추가", key=f"ex_add_{idx}"):
                    iid = f"item_{datetime.now().timestamp()}_ex{idx}"
                    closet.append({
                        "id": iid,
                        "type": tp,
                        "name": nm,
                        "primary_style": ps,
                        "secondary_style": ss,
                        "image": None,
                        "created_at": datetime.now().isoformat()
                    })
                    save_closet(closet)
                    st.success("추가 완료!")

st.markdown("---")

# -------- 2) Closet view --------
st.markdown("## 2) 👕 내 옷장")
closet = load_closet()
if not closet:
    st.info("아직 옷이 없어. 위에서 먼저 등록해줘!")
else:
    cols = st.columns(4)
    for i, item in enumerate(closet):
        with cols[i % 4]:
            if item.get("image"):
                st.image(item["image"], use_container_width=True)
            else:
                st.markdown("<div class='smallcard'>📦 이미지 없음</div>", unsafe_allow_html=True)
            st.caption(f"{item['type']} | 주:{item['primary_style']} / 보조:{item['secondary_style'] if item.get('secondary_style') else '-'}")
            st.caption(item["name"])

st.markdown("---")

# -------- 3) Recommend + Feedback loop --------
st.markdown("## 3) 🌦️ 오늘의 코디 추천 + 피드백")
temp = weather.get("temperature")
temp_bias = float(profile.get("temp_bias", 0.0))

st.caption(f"개인 보정값(temp_bias): {temp_bias:+.1f}°C  (피드백으로 자동 조정)")

today_primary = st.selectbox("오늘 주 스타일", STYLES, index=0)
today_secondary_pick = st.selectbox("오늘 보조 스타일(선택)", ["없음"] + STYLES, index=0)
today_secondary = None if today_secondary_pick == "없음" else today_secondary_pick
if today_secondary == today_primary:
    today_secondary = None
    st.info("보조 스타일이 주 스타일과 같아서 '없음'으로 처리했어.")

if st.button("OOTD 추천"):
    if not closet:
        st.error("옷장이 비어있어. 먼저 옷을 등록해줘!")
        st.stop()

    outfit, reasons, meta = recommend(closet, temp, today_primary, today_secondary, temp_bias=temp_bias)

    st.session_state["last_outfit"] = outfit
    st.session_state["last_reasons"] = reasons
    st.session_state["last_meta"] = meta
    st.session_state["last_ctx"] = {
        "lat": lat, "lon": lon,
        "weather": weather,
        "today_primary": today_primary,
        "today_secondary": today_secondary
    }

    st.markdown("### ✨ 추천 결과")
    for k, v in outfit.items():
        st.markdown("<div class='card'>", unsafe_allow_html=True)
        if v.get("image"):
            st.image(v["image"], width=180)
        else:
            st.write("📦 이미지 없음")
        st.markdown(f"**{k.upper()} | {v['name']}**")
        st.caption(f"주:{v.get('primary_style')} / 보조:{v.get('secondary_style') if v.get('secondary_style') else '-'}")
        for r in reasons[v["id"]]:
            st.caption("• " + r)
        st.markdown("</div>", unsafe_allow_html=True)

    # AI summary
    if use_openai and client:
        ai_msg = explain_outfit_ai(weather, today_primary, today_secondary, outfit, reasons, meta)
        if ai_msg:
            st.markdown("### 🧠 AI 요약")
            st.write(ai_msg)

# Feedback UI (appears after recommendation)
last_outfit = st.session_state.get("last_outfit")
if last_outfit:
    st.markdown("### 🧊🔥 오늘 추천, 어땠어?")
    fb = st.radio("체감 온도 피드백", ["추움", "딱 좋음", "더움"], horizontal=True)
    note = st.text_input("한 줄 코멘트(선택)", placeholder="예: 아우터가 너무 두꺼웠어 / 바지가 더 캐주얼했으면")

    if st.button("피드백 저장"):
        # Save feedback log
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

        # Update temp_bias simple learning
        prof = load_profile()
        bias = float(prof.get("temp_bias", 0.0))
        if fb == "추움":
            bias += 1.0  # next time, treat as colder -> recommend warmer
        elif fb == "더움":
            bias -= 1.0  # recommend lighter
        else:
            bias += 0.0
        # clamp
        bias = max(-5.0, min(5.0, bias))
        prof["temp_bias"] = bias
        save_profile(prof)

        st.success(f"피드백 저장 완료! 다음 추천부터 보정값이 {bias:+.1f}°C로 반영돼.")
        # optional: clear last outfit so user doesn't double-submit
        st.session_state.pop("last_outfit", None)

# -------- Feedback stats (optional) --------
st.markdown("---")
st.markdown("## 4) 📊 피드백 통계(간단)")
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
