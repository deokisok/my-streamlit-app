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

# =========================
# Sidebar: User + API + Location
# =========================
with st.sidebar:
    st.header("👤 사용자")
    user_id = st.text_input("사용자 ID(닉네임/이메일)", value="guest")
    user_id = re.sub(r"[^a-zA-Z0-9._-]", "_", user_id).strip() or "guest"
    st.caption("ID가 다르면 옷장/피드백이 완전히 분리 저장돼요.")

    st.markdown("---")
    st.header("🔑 API 설정")
    openai_key = st.text_input("OpenAI API Key", type="password", value=os.environ.get("OPENAI_API_KEY", ""))
    use_openai = st.toggle("OpenAI 기능 사용(영수증분석/상황가이드/설명)", value=bool(openai_key))
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
# Categories / styles (styles optional)
# =========================
CATEGORIES = ["top", "bottom", "outer", "shoes"]
STYLES = ["casual", "dandy", "hiphop", "sporty"]

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
# Placeholder image generator (무료, 안정적)
# =========================
def make_placeholder_image(text: str, out_path: Path, size=(512, 512)):
    img = Image.new("RGB", size, (30, 30, 30))
    draw = ImageDraw.Draw(img)

    try:
        font = ImageFont.truetype("DejaVuSans.ttf", 28)
        font_small = ImageFont.truetype("DejaVuSans.ttf", 18)
    except:
        font = ImageFont.load_default()
        font_small = ImageFont.load_default()

    draw.text((24, 20), "ootd item", fill=(200, 200, 200), font=font_small)

    t = (text or "item").strip()
    words = t.split()
    lines, line = [], ""
    for w in words:
        if len((line + " " + w).strip()) <= 18:
            line = (line + " " + w).strip()
        else:
            if line:
                lines.append(line)
            line = w
    if line:
        lines.append(line)
    lines = lines[:6]

    y = 120
    for ln in lines:
        draw.text((24, y), ln, fill=(240, 240, 240), font=font)
        y += 52

    draw.rectangle([24, size[1]-70, size[0]-24, size[1]-24], fill=(79, 127, 255))
    draw.text((36, size[1]-58), "auto-generated placeholder", fill=(255,255,255), font=font_small)

    img.save(out_path)

# =========================
# OpenAI: receipt image -> extract names (Vision)
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
                "role": "user",
                "content": [
                    {"type": "input_text", "text": prompt},
                    {"type": "input_image", "image_url": f"data:image/png;base64,{b64}"}
                ]
            }]
        )
        text = resp.output_text
        m = re.search(r"\{.*\}", text, re.DOTALL)
        if not m:
            return []
        data = json.loads(m.group(0))
        names = data.get("items", [])
        clean = []
        for n in names:
            n = str(n).strip()
            if n:
                clean.append(n[:80])
        return clean[:20]
    except:
        return []

# =========================
# OpenAI: classify names -> top/bottom/outer/shoes/unknown
# =========================
def classify_items_with_openai(item_names):
    if not client or not item_names:
        return [{"name": n, "type": "unknown", "confidence": 0.0} for n in item_names]

    prompt = f"""
너는 패션 상품명을 카테고리로 분류하는 분류기야.
가능한 카테고리(type)는 딱 5개만:
top, bottom, outer, shoes, unknown

규칙:
- 확실하지 않으면 unknown
- 결과는 JSON만 반환
- confidence는 0~1 숫자

입력 상품명 리스트:
{item_names}

반환 형식:
{{
  "items":[
    {{"name":"...", "type":"top", "confidence":0.82}},
    ...
  ]
}}
""".strip()

    try:
        resp = client.responses.create(model="gpt-4.1-mini", input=prompt)
        text = resp.output_text
        m = re.search(r"\{.*\}", text, re.DOTALL)
        if not m:
            return [{"name": n, "type": "unknown", "confidence": 0.0} for n in item_names]

        data = json.loads(m.group(0))
        out = []
        for it in data.get("items", []):
            nm = (it.get("name") or "").strip()
            tp = it.get("type")
            conf = it.get("confidence", 0.0)

            if tp not in ["top","bottom","outer","shoes","unknown"]:
                tp = "unknown"
            try:
                conf = float(conf)
            except:
                conf = 0.0
            conf = max(0.0, min(1.0, conf))

            if nm:
                out.append({"name": nm[:80], "type": tp, "confidence": conf})

        if not out:
            return [{"name": n, "type": "unknown", "confidence": 0.0} for n in item_names]
        return out[:20]
    except:
        return [{"name": n, "type": "unknown", "confidence": 0.0} for n in item_names]

# =========================
# OpenAI: situation guidance + explanation (optional)
# =========================
def build_guidance_with_openai(weather, situation, closet_summary):
    if not client:
        return None
    prompt = f"""
너는 '오늘 상황' 기반 코디 추천 룰을 만드는 도우미야.
아래 정보로 오늘 추천에 반영할 가이드(선호/회피 키워드)를 만들어줘.
반환은 JSON만.

- 날씨: {weather}
- 오늘 상황: {situation}
- 옷장 요약(카테고리/이름만): {closet_summary}

JSON:
{{
  "prefer_keywords": ["...","..."],
  "avoid_keywords": ["...","..."],
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
        pk = data.get("prefer_keywords", [])
        ak = data.get("avoid_keywords", [])
        pk = [str(x)[:30] for x in pk][:8] if isinstance(pk, list) else []
        ak = [str(x)[:30] for x in ak][:8] if isinstance(ak, list) else []
        notes = str(data.get("notes",""))[:120]
        return {"prefer_keywords": pk, "avoid_keywords": ak, "notes": notes}
    except:
        return None

def explain_outfit_ai(weather, situation, outfit, reasons, meta, guidance):
    if not client:
        return None
    prompt = f"""
OOTD 추천 결과를 3줄로 설명해줘. 인스타 느낌으로 짧고 친근하게.
상황 중심으로 왜 이 조합인지 말해줘.

- 날씨: {weather}
- 상황: {situation}
- 추천 코디: { {k:v['name'] for k,v in outfit.items()} }
- 근거: {reasons}
- 개인 보정: {meta}
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
# =========================
def recommend(closet, weather, situation, temp_bias=0.0, guidance=None, user_style_primary=None):
    temp = weather.get("temperature")
    effective_temp = None if temp is None else (temp + temp_bias)

    prefer_keywords = (guidance or {}).get("prefer_keywords", [])
    avoid_keywords = (guidance or {}).get("avoid_keywords", [])

    scores, reasons = {}, {}

    wants_formal = any(x in situation for x in ["면접", "발표", "중요", "출근", "미팅", "결혼식", "장례식"])
    wants_comfy  = any(x in situation for x in ["집콕", "학교", "꾸안꾸", "근처", "수업"])
    wants_sporty = any(x in situation for x in ["운동", "러닝"])
    wants_date   = any(x in situation for x in ["데이트", "소개팅", "첫만남"])

    for item in closet:
        s = 0
        r = []
        name = item.get("name", "")
        tp = item.get("type")

        # Weather
        if effective_temp is not None:
            if effective_temp < 10 and tp == "outer":
                s += 4; r.append("기온 낮음 → 아우터 추천(개인보정 포함)")
            if effective_temp >= 22 and tp == "outer":
                s -= 3; r.append("기온 높음 → 아우터 감점(개인보정 포함)")

        # Situation heuristics
        if wants_sporty:
            if tp == "shoes":
                s += 2; r.append("운동/러닝 → 신발 중요")
            if any(k in name for k in ["운동", "트레이닝", "러닝", "조거", "스니커", "레깅스"]):
                s += 3; r.append("운동 키워드 매칭")

        if wants_formal:
            if any(k in name for k in ["셔츠", "슬랙", "코트", "자켓", "블레이저", "로퍼"]):
                s += 3; r.append("격식/단정 키워드 매칭")
            if any(k in name for k in ["후드", "트랙", "조거", "볼캡"]):
                s -= 2; r.append("격식 상황엔 캐주얼 요소 감점")

        if wants_date:
            if any(k in name for k in ["셔츠", "니트", "코트", "자켓", "로퍼", "가디건"]):
                s += 2; r.append("데이트/첫만남 → 깔끔 아이템 가산")

        if wants_comfy:
            if any(k in name for k in ["후드", "맨투맨", "티", "청바지", "가디건", "스니커"]):
                s += 2; r.append("편한 상황 → 캐주얼 가산")

        # Optional style
        if user_style_primary:
            if item.get("primary_style") == user_style_primary or item.get("secondary_style") == user_style_primary:
                s += 1; r.append("선택한 스타일과 일부 일치(선택사항)")

        # AI guidance keywords
        for kw in prefer_keywords:
            if kw and kw in name:
                s += 2; r.append(f"AI 선호: {kw}")
        for kw in avoid_keywords:
            if kw and kw in name:
                s -= 2; r.append(f"AI 회피: {kw}")

        scores[item["id"]] = s
        reasons[item["id"]] = r if r else ["기본 점수"]

    outfit = {}
    for cat in ["top", "bottom", "outer", "shoes"]:
        candidates = [i for i in closet if i.get("type") == cat]
        if candidates:
            outfit[cat] = max(candidates, key=lambda x: scores.get(x["id"], 0))

    meta = {"temp_bias": temp_bias, "effective_temp": effective_temp}
    return outfit, reasons, meta

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
st.markdown("## 1) 📸 옷장 등록 (옷사진 / 영수증 AI / 텍스트·CSV)")
tabA, tabB, tabC = st.tabs(["옷 사진 등록", "영수증 사진으로 자동 등록(OpenAI)", "대량 등록(텍스트/CSV)"])

with tabA:
    col1, col2 = st.columns([1,1])
    with col1:
        img = st.file_uploader("옷 사진 업로드(선택)", type=["jpg","png"], key="cloth_img")
        item_type = st.selectbox("카테고리", CATEGORIES, key="cloth_type")
        name = st.text_input("아이템 이름(권장)", placeholder="예: 검정 셔츠, 슬랙스, 조거 팬츠", key="cloth_name")

    with col2:
        st.markdown("### 🎯 스타일 태그(선택 사항)")
        st.caption("모르면 안 해도 돼요. 상황 기반 추천이 메인입니다.")
        style_use = st.toggle("스타일 태그 입력(선택)", value=False, key="cloth_style_use")
        primary_style = None
        secondary_style = None
        if style_use:
            ps = st.selectbox("주 스타일(선택)", ["선택안함"] + STYLES, index=0, key="cloth_ps")
            ss = st.selectbox("보조 스타일(선택)", ["없음"] + STYLES, index=0, key="cloth_ss")
            primary_style = None if ps == "선택안함" else ps
            secondary_style = None if ss == "없음" else ss
            if primary_style and secondary_style == primary_style:
                secondary_style = None
                st.info("보조 스타일이 주 스타일과 같아서 '없음' 처리했어.")

    if st.button("옷장에 저장", key="cloth_save"):
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
            "primary_style": primary_style,
            "secondary_style": secondary_style,
            "image": str(img_path) if img_path else None,
            "created_at": datetime.now().isoformat(),
            "source": "manual"
        })
        save_closet(closet)
        st.success("저장 완료!")

with tabB:
    st.write("영수증 사진을 올리면 **의류/신발 품목명만 추출 + 카테고리 분류**해서 옷장에 추가할 수 있어요.")
    st.caption("AI가 틀릴 수 있으니, 추가 전 확인/수정 후 '예'를 눌러 저장합니다. (이미지는 플레이스홀더 자동 생성)")
    receipt_img = st.file_uploader("영수증 사진 업로드", type=["jpg","png"], key="receipt_img")

    if st.button("영수증 분석하기(AI)", key="receipt_analyze"):
        if not (use_openai and client):
            st.error("이 기능은 OpenAI API Key가 필요해요. 사이드바에서 입력하고 토글 켜줘.")
        elif not receipt_img:
            st.error("영수증 이미지를 올려줘.")
        else:
            names = extract_names_from_receipt_image(receipt_img.getvalue())
            if not names:
                st.warning("품목명 추출 실패. 사진이 흐리거나 의류 품목이 없을 수 있어요.")
            else:
                classified = classify_items_with_openai(names)
                # confidence 낮으면 unknown으로 보수적으로
                for it in classified:
                    if it.get("type") in ["top","bottom","outer","shoes"] and it.get("confidence", 0) < 0.55:
                        it["type"] = "unknown"
                st.session_state["receipt_preview"] = classified
                st.success("분석 완료! 아래에서 확인/수정 후 추가 여부를 선택해줘.")

    preview = st.session_state.get("receipt_preview", [])
    if preview:
        st.markdown("### ✅ AI 분석 결과(추가 전 확인/수정)")
        edited = []
        for idx, it in enumerate(preview):
            with st.expander(f"{idx+1}. {it['name']}"):
                col1, col2, col3 = st.columns([3,2,2])

                with col1:
                    nm = st.text_input("상품명", value=it["name"], key=f"pv_nm_{idx}")
                with col2:
                    tp_list = ["unknown"] + CATEGORIES
                    cur = it.get("type", "unknown")
                    if cur not in tp_list:
                        cur = "unknown"
                    tp = st.selectbox("카테고리(수정 가능)", tp_list, index=tp_list.index(cur), key=f"pv_tp_{idx}")
                with col3:
                    conf = float(it.get("confidence", 0.0))
                    st.metric("AI 신뢰도", f"{conf:.2f}")

                add_flag = st.checkbox("이 항목을 추가", value=(tp != "unknown"), key=f"pv_add_{idx}")

                edited.append({
                    "name": nm.strip() if nm else it["name"],
                    "type": tp if tp in CATEGORIES else "unknown",
                    "confidence": conf,
                    "add": add_flag
                })

        st.markdown("---")
        st.markdown("### ❓ 옷장에 추가하시겠습니까?")
        col_yes, col_no = st.columns(2)

        with col_yes:
            if st.button("✅ 예, 추가할게요", key="receipt_confirm_yes"):
                closet = load_closet()
                added = 0

                for idx, it in enumerate(edited):
                    if not it["add"]:
                        continue
                    if it["type"] == "unknown":
                        continue

                    iid = f"item_{datetime.now().timestamp()}_rc{idx}"
                    img_path = IMG_DIR / f"{iid}.png"
                    make_placeholder_image(it["name"], img_path)

                    closet.append({
                        "id": iid,
                        "type": it["type"],
                        "name": it["name"],
                        "primary_style": None,
                        "secondary_style": None,
                        "image": str(img_path),
                        "created_at": datetime.now().isoformat(),
                        "source": "receipt_ai"
                    })
                    added += 1

                save_closet(closet)
                st.success(f"총 {added}개 항목을 옷장에 추가했어! ✅")
                st.session_state.pop("receipt_preview", None)

        with col_no:
            if st.button("❌ 아니오, 취소", key="receipt_confirm_no"):
                st.info("취소했어. 필요하면 다시 분석해줘.")
                st.session_state.pop("receipt_preview", None)

with tabC:
    st.markdown("### 🧾 구매내역 텍스트/CSV로 대량 추가")
    st.caption("무신사 같은 앱 직접 연동은 보통 공식 API/제휴가 필요해 MVP에선 어려워요. 대신 이 방식이 현실적입니다.")

    sub1, sub2 = st.tabs(["텍스트 붙여넣기(OpenAI)", "CSV 업로드"])

    with sub1:
        txt = st.text_area("구매내역 텍스트", height=140, placeholder="주문내역/영수증 텍스트를 복사해 붙여넣기")
        if st.button("텍스트에서 옷 추출(OpenAI)"):
            if not (use_openai and client):
                st.error("OpenAI API Key가 필요해.")
            else:
                prompt = f"""
구매내역 텍스트에서 의류/신발 품목명만 최대 20개 추출해줘.
JSON만:
{{"items":["상품명1","상품명2",...]}}
텍스트:
{txt}
""".strip()
                try:
                    resp = client.responses.create(model="gpt-4.1-mini", input=prompt)
                    m = re.search(r"\{.*\}", resp.output_text, re.DOTALL)
                    names = json.loads(m.group(0)).get("items", []) if m else []
                    names = [str(n).strip()[:80] for n in names if str(n).strip()]
                    classified = classify_items_with_openai(names)
                    for it in classified:
                        if it.get("type") in ["top","bottom","outer","shoes"] and it.get("confidence", 0) < 0.55:
                            it["type"] = "unknown"
                    st.session_state["text_preview"] = classified
                    st.success("추출/분류 완료! 아래에서 확인 후 추가해줘.")
                except:
                    st.warning("추출 실패. 텍스트에 상품명이 잘 보이게 다시 시도해줘.")

        preview = st.session_state.get("text_preview", [])
        if preview:
            st.markdown("#### 미리보기(수정 후 추가)")
            edited = []
            for idx, it in enumerate(preview):
                with st.expander(f"{idx+1}. {it['name']}"):
                    nm = st.text_input("상품명", value=it["name"], key=f"tp_nm_{idx}")
                    tp_list = ["unknown"] + CATEGORIES
                    cur = it.get("type","unknown")
                    if cur not in tp_list:
                        cur = "unknown"
                    tp = st.selectbox("카테고리", tp_list, index=tp_list.index(cur), key=f"tp_tp_{idx}")
                    conf = float(it.get("confidence", 0.0))
                    st.caption(f"AI 신뢰도: {conf:.2f}")
                    add_flag = st.checkbox("추가", value=(tp != "unknown"), key=f"tp_add_{idx}")
                    edited.append({"name": nm.strip(), "type": tp, "add": add_flag})

            if st.button("✅ 선택 항목을 옷장에 추가"):
                closet = load_closet()
                added = 0
                for idx, it in enumerate(edited):
                    if not it["add"]:
                        continue
                    if it["type"] == "unknown":
                        continue
                    iid = f"item_{datetime.now().timestamp()}_t{idx}"
                    img_path = IMG_DIR / f"{iid}.png"
                    make_placeholder_image(it["name"], img_path)
                    closet.append({
                        "id": iid, "type": it["type"], "name": it["name"],
                        "primary_style": None, "secondary_style": None,
                        "image": str(img_path),
                        "created_at": datetime.now().isoformat(),
                        "source": "text_ai"
                    })
                    added += 1
                save_closet(closet)
                st.success(f"{added}개 추가 완료!")
                st.session_state.pop("text_preview", None)

    with sub2:
        st.write("CSV 컬럼: type,name,primary_style,secondary_style (style은 선택)")
        csv_file = st.file_uploader("CSV 업로드", type=["csv"], key="csv_up")
        if csv_file and st.button("CSV로 추가"):
            text = csv_file.getvalue().decode("utf-8", errors="ignore").splitlines()
            reader = csv.DictReader(text)
            rows = list(reader)
            closet = load_closet()
            added = 0
            for row in rows:
                tp = (row.get("type") or "").strip()
                nm = (row.get("name") or "").strip()
                if tp not in CATEGORIES or not nm:
                    continue
                ps = (row.get("primary_style") or "").strip()
                ss = (row.get("secondary_style") or "").strip()
                ps_val = ps if ps in STYLES else None
                ss_val = ss if ss in STYLES else None
                if ps_val and ss_val == ps_val:
                    ss_val = None

                iid = f"item_{datetime.now().timestamp()}_c{added}"
                img_path = IMG_DIR / f"{iid}.png"
                make_placeholder_image(nm, img_path)

                closet.append({
                    "id": iid, "type": tp, "name": nm,
                    "primary_style": ps_val, "secondary_style": ss_val,
                    "image": str(img_path),
                    "created_at": datetime.now().isoformat(),
                    "source": "csv"
                })
                added += 1
            save_closet(closet)
            st.success(f"{added}개 추가 완료!")

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
# 3) Situation-based recommendation
# =========================
st.markdown("## 3) 🗓️ 오늘 상황 기반 코디 추천")
st.caption(f"개인 온도 보정값(temp_bias): {temp_bias:+.1f}°C (피드백으로 자동 학습)")

situation = st.selectbox("오늘 상황을 선택해줘", SITUATIONS)
st.caption("상황 힌트: " + situation_hint(situation))

optional_style = st.selectbox("스타일도 고려할래? (선택)", ["선택안함"] + STYLES, index=0)
user_style_primary = None if optional_style == "선택안함" else optional_style

guidance = None
if use_openai and client:
    with st.expander("🤖 OpenAI 상황 가이드(자동 생성) 보기", expanded=False):
        closet_summary = [{"type": i.get("type"), "name": i.get("name")} for i in closet][:60]
        if st.button("상황 가이드 생성"):
            guidance = build_guidance_with_openai(weather, situation, closet_summary)
            st.session_state["guidance"] = guidance
        guidance = st.session_state.get("guidance", None)
        if guidance:
            st.write(guidance.get("notes", ""))
            st.write("선호 키워드:", guidance.get("prefer_keywords", []))
            st.write("회피 키워드:", guidance.get("avoid_keywords", []))

if st.button("OOTD 추천"):
    if not closet:
        st.error("옷장이 비어있어. 먼저 옷을 등록해줘!")
        st.stop()

    guidance = st.session_state.get("guidance", None) if (use_openai and client) else None
    outfit, reasons, meta = recommend(
        closet=closet, weather=weather, situation=situation,
        temp_bias=temp_bias, guidance=guidance, user_style_primary=user_style_primary
    )

    st.session_state["last_outfit"] = outfit
    st.session_state["last_reasons"] = reasons
    st.session_state["last_meta"] = meta
    st.session_state["last_ctx"] = {
        "user_id": user_id, "weather": weather, "situation": situation,
        "user_style_primary": user_style_primary, "guidance": guidance
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
        for rr in reasons.get(v["id"], []):
            st.caption("• " + rr)
        st.markdown("</div>", unsafe_allow_html=True)

    if use_openai and client:
        ai_msg = explain_outfit_ai(weather, situation, outfit, reasons, meta, guidance)
        if ai_msg:
            st.markdown("### 🧠 AI 요약")
            st.write(ai_msg)

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
