import streamlit as st
import requests
import numpy as np
import plotly.graph_objects as go

# =========================
# 페이지 설정
# =========================
st.set_page_config(page_title="나와 어울리는 영화는?", layout="centered")

# =========================
# TMDB 설정
# =========================
GENRES = {
    "액션": 28,
    "코미디": 35,
    "드라마": 18,
    "SF": 878,
    "로맨스": 10749,
    "판타지": 14,
}
POSTER_BASE = "https://image.tmdb.org/t/p/w500"

# =========================
# 성향 축
# =========================
TRAITS = ["Energy", "Emotion", "Action", "Fantasy", "Humor"]

def init_traits():
    return {t: 0 for t in TRAITS}

def fetch_movies(api_key, genre_id, n=5):
    url = "https://api.themoviedb.org/3/discover/movie"
    params = {
        "api_key": api_key,
        "with_genres": genre_id,
        "language": "ko-KR",
        "sort_by": "popularity.desc",
        "page": 1,
    }
    r = requests.get(url, params=params, timeout=15)
    r.raise_for_status()
    return r.json().get("results", [])[:n]

# =========================
# 질문 & 점수 매핑 (10문항)
# =========================
QUESTIONS = [
    ("주말에 에너지는 어디서 얻나?",
     ["사람 만남", "혼자 충전", "새로운 자극", "집에서 안정"],
     [{"Energy": 2}, {"Energy": -2}, {"Action": 1}, {"Action": -1}]
     ),
    ("스트레스 해소 방식은?",
     ["수다", "혼자 생각", "운동", "잠"],
     [{"Energy": 1, "Humor": 1}, {"Emotion": 1}, {"Action": 2}, {"Action": -1}]
     ),
    ("영화 볼 때 더 끌리는 쪽은?",
     ["감정선", "메시지", "비주얼", "웃음"],
     [{"Emotion": 2}, {"Fantasy": 1}, {"Fantasy": 2}, {"Humor": 2}]
     ),
    ("여행 스타일은?",
     ["계획형", "즉흥", "액티비티", "힐링"],
     [{"Emotion": 1}, {"Fantasy": 1}, {"Action": 2}, {"Action": -1}]
     ),
    ("친구들 사이에서 나는?",
     ["리더", "분위기메이커", "경청자", "자유인"],
     [{"Energy": 1}, {"Humor": 2}, {"Emotion": 2}, {"Fantasy": 1}]
     ),
    ("선호하는 대화 주제는?",
     ["현실", "감정", "상상", "유머"],
     [{"Emotion": -1}, {"Emotion": 2}, {"Fantasy": 2}, {"Humor": 2}]
     ),
    ("결정할 때 나는?",
     ["빠르게", "신중히", "감정 따라", "상황 따라"],
     [{"Action": 1}, {"Action": -1}, {"Emotion": 2}, {"Fantasy": 1}]
     ),
    ("좋아하는 영화 분위기",
     ["현실적", "잔잔", "화려", "엉뚱"],
     [{"Fantasy": -1}, {"Emotion": 1}, {"Fantasy": 2}, {"Humor": 2}]
     ),
    ("혼자 있는 시간은?",
     ["필수", "가끔", "별로", "싫음"],
     [{"Energy": -2}, {"Energy": -1}, {"Energy": 1}, {"Energy": 2}]
     ),
    ("웃음 코드",
     ["블랙", "잔잔", "과장", "드립"],
     [{"Humor": 1}, {"Humor": -1}, {"Humor": 2}, {"Humor": 1}]
     ),
]

# =========================
# 장르 결정 (성향 기반)
# =========================
def decide_genre(traits):
    # 우선순위: Fantasy→SF/판타지, Humor→코미디, Action→액션, Emotion→로맨스, 나머지 드라마
    if traits["Fantasy"] >= 4:
        # 상상력이 매우 강하면 SF 쪽으로
        return "SF"
    if traits["Humor"] >= 4:
        return "코미디"
    if traits["Action"] >= 4:
        return "액션"
    if traits["Emotion"] >= 4:
        return "로맨스"
    # Fantasy가 높지만 SF까지는 아니면 판타지로
    if traits["Fantasy"] >= 2:
        return "판타지"
    return "드라마"

# =========================
# 레이더 차트 (Plotly)
# =========================
def draw_radar(traits):
    labels = list(traits.keys())
    values = list(traits.values())

    fig = go.Figure(
        data=[
            go.Scatterpolar(
                r=values + [values[0]],
                theta=labels + [labels[0]],
                fill="toself"
            )
        ]
    )

    # 점수 범위(대략): -5 ~ 8 정도 나올 수 있어 안전하게 넉넉히
    fig.update_layout(
        polar=dict(
            radialaxis=dict(
                visible=True,
                range=[-6, 8]
            )
        ),
        showlegend=False,
        margin=dict(l=20, r=20, t=50, b=20),
        title="🧠 나의 성향 레이더 차트"
    )
    return fig

# =========================
# 영화 추천 이유 (짧게)
# =========================
def movie_reason(genre, traits):
    if genre == "SF":
        return "상상력/세계관 선호 성향이 강해서 SF가 잘 맞아요."
    if genre == "판타지":
        return "비현실적인 설정과 비주얼을 즐기는 성향이라 판타지가 어울려요."
    if genre == "코미디":
        return "웃음 포인트를 중요하게 생각해서 가볍게 즐길 코미디가 좋아요."
    if genre == "액션":
        return "활동적이고 몰입감 있는 전개를 선호해서 액션이 잘 맞아요."
    if genre == "로맨스":
        return "감정 몰입/관계 서사 선호가 높아 로맨스가 어울려요."
    return "현실적인 이야기와 감정선을 선호해 드라마가 잘 맞아요."

# =========================
# 사이드바
# =========================
with st.sidebar:
    st.header("🔑 TMDB API 설정")
    tmdb_key = st.text_input("TMDB API Key", type="password")
    st.caption("TMDB에서 발급받은 키를 입력하세요.")

# =========================
# 메인 UI
# =========================
st.title("🎬 나와 어울리는 영화는?")
st.write("질문이 많아질수록 당신의 취향이 더 정확해져요 🎥🍿")
st.divider()

traits = init_traits()

# 질문 출력
for i, (q, options, effects) in enumerate(QUESTIONS):
    choice = st.radio(f"{i+1}. {q}", options, key=f"q_{i}")
    idx = options.index(choice)
    for k, v in effects[idx].items():
        traits[k] += v

st.divider()

# 결과 버튼
if st.button("🎞️ 결과 보기"):
    if not tmdb_key:
        st.error("TMDB API Key를 사이드바에 입력해 주세요!")
        st.stop()

    genre = decide_genre(traits)
    genre_id = GENRES[genre]

    st.subheader(f"✨ 당신과 어울리는 장르: **{genre}**")
    st.caption(movie_reason(genre, traits))

    st.plotly_chart(draw_radar(traits), use_container_width=True)

    st.divider()
    st.subheader("🍿 추천 영화 TOP 5")

    try:
        movies = fetch_movies(tmdb_key, genre_id, n=5)
    except Exception as e:
        st.error(f"TMDB 요청 실패: {e}")
        st.stop()

    for m in movies:
        title = m.get("title") or "제목 없음"
        rating = m.get("vote_average", "N/A")
        overview = m.get("overview") or "줄거리 정보가 없어요."
        poster_path = m.get("poster_path")

        cols = st.columns([1, 2])
        with cols[0]:
            if poster_path:
                st.image(POSTER_BASE + poster_path, use_container_width=True)
            else:
                st.info("포스터 없음")
        with cols[1]:
            st.markdown(f"### {title}")
            st.write(f"⭐ 평점: {rating}")
            st.write(overview)
            st.caption("💡 추천 이유: " + movie_reason(genre, traits))

        st.divider()
