import streamlit as st
import json, os, re
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
.stButton>button {
    background-color: #4F7FFF;
    color: white;
    border-radius: 20px;
}
</style>
""", unsafe_allow_html=True)

# =========================
# Data
# =========================
DATA = Path("data")
IMG = DATA / "images"
CLOSET = DATA / "closet.json"

DATA.mkdir(exist_ok=True)
IMG.mkdir(exist_ok=True)
if not CLOSET.exists():
    CLOSET.write_text("[]", encoding="utf-8")

def load_closet():
    return json.loads(CLOSET.read_text(encoding="utf-8"))

def save_closet(c):
    CLOSET.write_text(json.dumps(c, ensure_ascii=False, indent=2), encoding="utf-8")

# =========================
# Sidebar: API Key
# =========================
with st.sidebar:
    st.header("🔑 API 설정")
    openai_key = st.text_input("OpenAI API Key", type="password", value=os.environ.get("OPENAI_API_KEY", ""))
    use_openai = st.toggle("OpenAI 기능 사용", value=bool(openai_key))
    if openai_key:
        os.environ["OPENAI_API_KEY"] = openai_key

# OpenAI client (옵션)
client = None
if use_openai and openai_key:
    try:
        from openai import OpenAI
        client = OpenAI()
    except:
        client = None

# =========================
# Weather
# =========================
def get_weather():
    url = "https://api.open-meteo.com/v1/forecast?latitude=37.5665&longitude=126.9780&current_weather=true"
    w = requests.get(url, timeout=10).json()["current_weather"]
    return w["temperature"]

# =========================
# Style Suggestion (Rule)
# =========================
STYLE_KEYWORDS = {
    "dandy": ["셔츠", "슬랙", "코트", "로퍼", "자켓"],
    "casual": ["후드", "맨투맨", "티", "청바지"],
    "hiphop": ["오버", "조거", "트랙", "볼캡"],
    "sporty": ["운동", "트레이닝", "러닝", "스니커"]
}

def suggest_styles_rule(name):
    found = set()
    for style, words in STYLE_KEYWORDS.items():
        for w in words:
            if w.lower() in name.lower():
                found.add(style)
    return list(found) if found else ["casual"]

# =========================
# Style Suggestion (OpenAI)
# =========================
def suggest_styles_openai(name):
    if not client or not name.strip():
        return ["casual"]
    prompt = f"""
의류 이름을 보고 스타일 태그를 1~2개 추천해줘.
가능한 태그는 ["casual","dandy","hiphop","sporty"] 중에서만 선택.
JSON 형식으로만 반환해.

의류 이름: {name}
"""
    try:
        resp = client.responses.create(
            model="gpt-4.1-mini",
            input=prompt,
        )
        text = resp.output_text
        m = re.search(r"\{.*\}", text, re.DOTALL)
        if not m:
            return ["casual"]
        data = json.loads(m.group(0))
        styles = [s for s in data.get("styles", []) if s in ["casual","dandy","hiphop","sporty"]]
        return styles[:2] if styles else ["casual"]
    except:
        return ["casual"]

# =========================
# Recommendation Engine
# =========================
def recommend(closet, temp, today_style):
    scores, reasons = {}, {}
    for item in closet:
        s, r = 0, []
        if temp < 10 and item["type"] == "outer":
            s += 2; r.append("기온이 낮아 아우터 적합")
        if today_style in item["style"]:
            s += 3; r.append(f"{today_style} 스타일과 일치")
        else:
            s -= 1; r.append("오늘 스타일과 다소 다름")
        scores[item["id"]] = s
        reasons[item["id"]] = r

    outfit = {}
    for t in ["top","bottom","outer","shoes"]:
        items = [i for i in closet if i["type"] == t]
        if items:
            outfit[t] = max(items, key=lambda x: scores[x["id"]])
    return outfit, reasons

# =========================
# AI Explanation
# =========================
def explain_outfit_ai(temp, today_style, outfit, reasons):
    if not client:
        return None
    prompt = f"""
OOTD 앱의 추천 이유를 3줄로 설명해줘.
톤은 짧고 친근하게.

- 기온: {temp}°C
- 오늘 스타일: {today_style}
- 추천 코디: { {k:v['name'] for k,v in outfit.items()} }
- 규칙 기반 이유: {reasons}
"""
    try:
        resp = client.responses.create(
            model="gpt-4.1-mini",
            input=prompt,
        )
        return resp.output_text.strip()
    except:
        return None

# =========================
# UI
# =========================
st.title("🧥 ootd")

# -------- Register --------
st.markdown("## 📸 옷 등록")
img = st.file_uploader("사진 업로드", type=["jpg","png"])
item_type = st.selectbox("카테고리", ["top","bottom","outer","shoes"])
name = st.text_input("이름", placeholder="예: 검정 셔츠, 슬랙스")

auto_styles = []
if name:
    auto_styles = suggest_styles_openai(name) if (use_openai and client) else suggest_styles_rule(name)
    st.caption(f"🤖 AI 추천 스타일: {', '.join(auto_styles)}")

style = st.multiselect(
    "스타일 (AI 추천됨, 수정 가능)",
    ["casual","dandy","hiphop","sporty"],
    default=auto_styles
)

if img and st.button("옷장에 저장"):
    image = Image.open(img)
    iid = f"item_{datetime.now().timestamp()}"
    path = IMG / f"{iid}.png"
    image.save(path)

    closet = load_closet()
    closet.append({
        "id": iid,
        "type": item_type,
        "name": name if name else item_type,
        "style": style,
        "image": str(path)
    })
    save_closet(closet)
    st.success("옷 저장 완료!")

# -------- Closet --------
st.markdown("## 👕 내 옷장")
closet = load_closet()
cols = st.columns(4)
for i, item in enumerate(closet):
    with cols[i % 4]:
        st.image(item["image"], use_container_width=True)
        st.caption(f"{item['type']} | {', '.join(item['style'])}")

# -------- Recommend --------
st.markdown("## 🌦️ 오늘의 코디")
temp = get_weather()
st.caption(f"현재 기온: {temp}°C")
today_style = st.selectbox("오늘 스타일", ["casual","dandy","hiphop","sporty"])

if st.button("OOTD 추천"):
    outfit, reasons = recommend(closet, temp, today_style)
    st.markdown("### ✨ 추천 결과")

    for k, v in outfit.items():
        st.markdown("<div class='card'>", unsafe_allow_html=True)
        st.image(v["image"], width=180)
        st.markdown(f"**{k.upper()} | {v['name']}**")
        for r in reasons[v["id"]]:
            st.caption("• " + r)
        st.markdown("</div>", unsafe_allow_html=True)

    if use_openai and client:
        ai_msg = explain_outfit_ai(temp, today_style, outfit, reasons)
        if ai_msg:
            st.markdown("### 🧠 AI 요약")
            st.write(ai_msg)
