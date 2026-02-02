import streamlit as st
import requests
import matplotlib.pyplot as plt
import numpy as np

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
    r = requests.get(url, params=params, timeout=10)
    r.raise_for_status()
    return r.json().get("results", [])[:n]

# =========================
# 질문 & 점수 매핑
# =========================
QUESTIONS = [
    ("주말에 에너지는 어디서 얻나?", 
     ["사람 만남", "혼자 충전", "새로운 자극", "집에서 안정"],
     [{"Energy":2},{"Energy":-2},{"Action":1},{"Action":-1}]
    ),
    ("스트레스 해소 방식은?", 
     ["수다", "혼자 생각", "운동", "잠"],
     [{"Energy":1,"Humor":1},{"Emotion":1},{"Action":2},{"Action":-1}]
    ),
    ("영화 볼 때 더 끌리는 쪽은?", 
     ["감정선", "메시지", "비주얼", "웃음"],
     [{"Emotion":2},{"Fantasy":1},{"Fantasy":2},{"Humor":2}]
    ),
    ("여행 스타일은?", 
     ["계획형", "즉흥", "액티비티", "힐링"],
     [{"Emotion":1},{"Fantasy":1},{"Action":2},{"Action":-1}]
    ),
    ("친구들 사이에서 나는?", 
     ["리더", "분위기메이커", "경청자", "자유인"],
     [{"Energy":1},{"Humor":2},{"Emotion":2},{"Fantasy":1}]
    ),
    ("선호하는 대화 주제는?", 
     ["현실", "감정", "상상", "유머"],
     [{"Emotion":-1},{"Emotion":2},{"Fantasy":2},{"Humor":2}]
    ),
    ("결정할 때 나는?", 
     ["빠르게", "신중히", "감정 따라", "상황 따라"],
     [{"Action":1},{"Action":-1},{"Emotion":2},{"Fantasy":1}]
    ),
    ("좋아하는 영화 분위기", 
     ["현실적", "잔잔", "화려", "엉뚱"],
     [{"Fantasy":-1},{"Emotion":1},{"Fantasy":2},{"Humor":2}]
    ),
    ("혼자 있는 시간은?", 
     ["필수", "가끔", "별로", "싫음"],
     [{"Energy":-2},{"Energy":-1},{"Energy":1},{"Energy":2}]
    ),
    ("웃음 코드", 
     ["블랙", "잔잔", "과장", "드립"],
     [{"Humor":1},{"Humor":-1},{"Humor":2},{"Humor":1}]
    ),
]

# =========================
# 장르 매칭
# =========================
def decide_genre(traits):
    if traits["Fantasy"] > 3:
        return "SF"
    if traits["Humor"] > 3:
        return "코미디"
    if traits["Action"] > 3:
        return "액션"
    if traits["Emotion"] > 3:
        return "로맨스"
    return "드라마"

# =========================
# 레이더 차트
# =========================
def draw_radar(traits):
    labels = list(traits.keys())
    values = list(traits.values())
    values += values[:1]

    angles = np.linspace(0, 2*np.pi, len(labels)+1)

    fig, ax = plt.subplots(subplot_kw=dict(polar=True))
    ax.plot(angles, values, linewidth=2)
    ax.fill(angles, values, alpha=0.25)
    ax.set_thetagrids(angles[:-1]*180/np.pi, labels)
    ax.set_title("🧠 나의 성향 레이더 차트")
    return fig

# =========================
# UI
# =========================
with st.sidebar:
    tmdb_key = st.text_input("TMDB API Key", type="password")

st.title("🎬 나와 어울리는 영화는?")
st.write("질문이 많아질수록, 당신의 취향은 더 정확해져요.")
st.divider()

traits = init_traits()
answers = []

for i, (q, options, effects) in enumerate(QUESTIONS):
    choice = st.radio(f"{i+1}. {q}", options)
    idx = options.index(choice)
    for k, v in effects[idx].items():
        traits[k] += v

st.divider()

if st.button("🎞️ 결과 보기"):
    if not tmdb_key:
        st.error("TMDB API Key를 입력해 주세요!")
        st.stop()

    genre = decide_genre(traits)
    genre_id = GENRES[genre]

    st.subheader(f"✨ 당신의 영화 성향 장르: **{genre}**")
    st.pyplot(draw_radar(traits))

    st.divider()
    st.subheader("🍿 추천 영화")

    movies = fetch_movies(tmdb_key, genre_id)
    for m in movies:
        cols = st.columns([1,2])
        with cols[0]:
            if m.get("poster_path"):
                st.image(POSTER_BASE + m["poster_path"], use_container_width=True)
        with cols[1]:
            st.markdown(f"### {m.get('title')}")
            st.write(f"⭐ 평점: {m.get('vote_average')}")
            st.write(m.get("overview", "줄거리 없음"))
            st.caption("💡 추천 이유: 당신의 성향 레이더와 이 장르가 가장 잘 맞아요.")
        st.divider()
