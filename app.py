import streamlit as st
import requests

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

def fetch_movies(api_key: str, genre_id: int, n: int = 5):
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
    data = r.json()
    return (data.get("results") or [])[:n]

def analyze_genre(ans):
    """
    ans: dict with q1~q5 answers.
    간단한 규칙 기반으로 장르 스코어링.
    """
    score = {k: 0 for k in GENRES.keys()}

    # Q1 주말
    if ans["q1"] == "새로운 곳 탐험":
        score["액션"] += 2
        score["판타지"] += 1
    elif ans["q1"] == "친구와 놀기":
        score["코미디"] += 2
        score["로맨스"] += 1
    elif ans["q1"] == "집에서 휴식":
        score["드라마"] += 2
        score["로맨스"] += 1
    elif ans["q1"] == "혼자 취미생활":
        score["SF"] += 2
        score["드라마"] += 1

    # Q2 스트레스
    if ans["q2"] == "운동하기":
        score["액션"] += 2
    elif ans["q2"] == "수다 떨기":
        score["코미디"] += 2
        score["로맨스"] += 1
    elif ans["q2"] == "맛있는 거 먹기":
        score["코미디"] += 1
        score["드라마"] += 1
    elif ans["q2"] == "혼자 있기":
        score["드라마"] += 2
        score["SF"] += 1

    # Q3 영화에서 중요한 것
    if ans["q3"] == "감동 스토리":
        score["드라마"] += 3
        score["로맨스"] += 1
    elif ans["q3"] == "시각적 영상미":
        score["SF"] += 2
        score["판타지"] += 2
    elif ans["q3"] == "깊은 메시지":
        score["드라마"] += 2
        score["SF"] += 1
    elif ans["q3"] == "웃는 재미":
        score["코미디"] += 3

    # Q4 여행 스타일
    if ans["q4"] == "즉흥적":
        score["코미디"] += 1
        score["액션"] += 1
    elif ans["q4"] == "액티비티":
        score["액션"] += 2
    elif ans["q4"] == "힐링":
        score["로맨스"] += 1
        score["드라마"] += 1
    elif ans["q4"] == "계획적":
        score["SF"] += 1
        score["드라마"] += 1

    # Q5 친구 사이에서
    if ans["q5"] == "주도하기":
        score["액션"] += 1
        score["판타지"] += 1
    elif ans["q5"] == "분위기 메이커":
        score["코미디"] += 2
    elif ans["q5"] == "듣는 역할":
        score["드라마"] += 1
        score["로맨스"] += 1
    elif ans["q5"] == "필요할 때 나타남":
        score["SF"] += 1
        score["판타지"] += 1

    best_genre = max(score.items(), key=lambda x: x[1])[0]
    return best_genre, score

def short_reason(best_genre: str, ans: dict, score: dict):
    """
    장르 추천 이유(간단) 생성
    """
    hints = []
    if best_genre == "드라마":
        if ans["q3"] == "감동 스토리":
            hints.append("감동 스토리를 중요하게 여겨서")
        if ans["q2"] in ["혼자 있기", "맛있는 거 먹기"]:
            hints.append("스트레스 상황에서 감정 회복을 선호해서")
    elif best_genre == "코미디":
        if ans["q3"] == "웃는 재미":
            hints.append("웃는 재미를 가장 중요하게 생각해서")
        if ans["q1"] == "친구와 놀기":
            hints.append("함께 즐기는 시간을 좋아해서")
    elif best_genre == "액션":
        if ans["q4"] == "액티비티":
            hints.append("활동적인 성향이 강해서")
        if ans["q1"] == "새로운 곳 탐험":
            hints.append("새로운 자극을 즐겨서")
    elif best_genre == "SF":
        if ans["q3"] in ["시각적 영상미", "깊은 메시지"]:
            hints.append("상상력과 세계관/메시지를 좋아해서")
        if ans["q1"] == "혼자 취미생활":
            hints.append("혼자 몰입하는 취향이 있어서")
    elif best_genre == "로맨스":
        if ans["q1"] == "집에서 휴식":
            hints.append("따뜻한 분위기의 힐링을 선호해서")
        if ans["q5"] == "듣는 역할":
            hints.append("관계에서 공감하는 편이라서")
    elif best_genre == "판타지":
        if ans["q3"] == "시각적 영상미":
            hints.append("비현실적인 볼거리와 세계관을 좋아해서")
        if ans["q1"] == "새로운 곳 탐험":
            hints.append("모험/탐험 감성을 즐겨서")

    if not hints:
        hints.append("답변 패턴이 해당 장르와 가장 잘 맞아서")
    return " / ".join(hints[:2])

def movie_reason(best_genre: str, movie: dict):
    """
    영화 추천 이유(짧게)
    """
    title = movie.get("title") or "이 영화"
    if best_genre == "코미디":
        return f"가볍게 즐기기 좋은 인기 코미디라서 {title}를 추천해요."
    if best_genre == "드라마":
        return f"감정선이 풍부한 드라마 장르에서 평점/인기가 좋아 {title}가 잘 맞아요."
    if best_genre == "액션":
        return f"긴장감과 몰입도가 높은 인기 액션이라서 {title}를 추천해요."
    if best_genre == "SF":
        return f"독특한 세계관과 상상력이 매력적인 SF라서 {title}를 추천해요."
    if best_genre == "로맨스":
        return f"따뜻한 분위기의 로맨스 장르에서 반응이 좋아 {title}가 잘 맞아요."
    if best_genre == "판타지":
        return f"세계관과 비주얼이 강한 판타지로 즐기기 좋아 {title}를 추천해요."
    return f"당신의 취향과 잘 맞는 장르라서 {title}를 추천해요."

# =========================
# 사이드바 - TMDB API Key
# =========================
with st.sidebar:
    st.header("🔑 TMDB 설정")
    tmdb_key = st.text_input("TMDB API Key", type="password", placeholder="TMDB API Key를 입력하세요")
    st.caption("키가 없으면 TMDB에서 발급 후 입력해주세요.")

# =========================
# 제목 & 소개
# =========================
st.title("🎬 나와 어울리는 영화는?")
st.write("간단한 질문에 답하면, 당신과 어울리는 영화 장르와 인기 영화 5편을 추천해드려요 🎥🍿")
st.divider()

# =========================
# 질문 5개 (각 4개 선택지)
# =========================
q1 = st.radio("1️⃣ 주말에 가장 하고 싶은 것은?", ["집에서 휴식", "친구와 놀기", "새로운 곳 탐험", "혼자 취미생활"])
q2 = st.radio("2️⃣ 스트레스 받으면?", ["혼자 있기", "수다 떨기", "운동하기", "맛있는 거 먹기"])
q3 = st.radio("3️⃣ 영화에서 중요한 것은?", ["감동 스토리", "시각적 영상미", "깊은 메시지", "웃는 재미"])
q4 = st.radio("4️⃣ 여행 스타일?", ["계획적", "즉흥적", "액티비티", "힐링"])
q5 = st.radio("5️⃣ 친구 사이에서 나는?", ["듣는 역할", "주도하기", "분위기 메이커", "필요할 때 나타남"])

st.divider()

# =========================
# 결과 보기
# =========================
if st.button("🎞️ 결과 보기"):
    if not tmdb_key:
        st.error("TMDB API Key를 사이드바에 입력해줘!")
        st.stop()

    ans = {"q1": q1, "q2": q2, "q3": q3, "q4": q4, "q5": q5}
    best_genre, score = analyze_genre(ans)
    genre_id = GENRES[best_genre]

    st.subheader("🔍 분석 중...")
    st.write("당신의 선택을 분석하고, 어울리는 영화를 찾고 있어요...")

    try:
        movies = fetch_movies(tmdb_key, genre_id, n=5)
    except Exception as e:
        st.error(f"TMDB 요청 실패: {e}")
        st.stop()

    st.success(f"당신에게 어울리는 장르는 **{best_genre}** 이에요!")
    st.caption("장르 선택 이유: " + short_reason(best_genre, ans, score))

    st.divider()
    st.subheader("🍿 추천 영화 TOP 5")

    for m in movies:
        title = m.get("title") or "제목 없음"
        rating = m.get("vote_average")
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
            st.write(f"⭐ 평점: {rating if rating is not None else 'N/A'}")
            st.write(overview)
            st.caption("💡 추천 이유: " + movie_reason(best_genre, m))

        st.divider()
