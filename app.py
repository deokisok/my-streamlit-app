else:
    st.markdown("## 📊 피드백 리포트")

    profile = load_profile()
    logs = load_feedback()
    closet = load_closet()
    taste = profile.get("taste", {})

    st.markdown("<div class='smallcard'>", unsafe_allow_html=True)
    st.write("⭐ 평균 별점:", float(taste.get("avg_rating", 0.0)))
    st.write("🧾 피드백 누적:", int(taste.get("rating_count", 0)), "회")
    st.write("🌡️ 온도 보정값(temp_bias):", f"{float(profile.get('temp_bias', 0.0)):+.1f}°C")
    st.write("👕 옷장 아이템 수:", len(closet))
    st.markdown("</div>", unsafe_allow_html=True)

    if not logs:
        st.info("아직 피드백이 없어요. 메인 페이지에서 추천 후 피드백을 남겨주세요!")
        st.stop()

    # --- 집계 ---
    temp_cnt = {"추움": 0, "딱 좋음": 0, "더움": 0}
    color_cnt = {"좋음": 0, "상관없음": 0, "별로": 0}
    pattern_cnt = {"좋음": 0, "상관없음": 0, "별로": 0}
    vibe_cnt = {"좋음": 0, "상관없음": 0, "별로": 0}

    ratings = []
    for l in logs:
        r = l.get("rating")
        if isinstance(r, int):
            ratings.append(r)
        tf = l.get("temp_feedback")
        if tf in temp_cnt:
            temp_cnt[tf] += 1
        sf = l.get("style_feedback", {}) or {}
        if sf.get("color") in color_cnt: color_cnt[sf.get("color")] += 1
        if sf.get("pattern") in pattern_cnt: pattern_cnt[sf.get("pattern")] += 1
        if sf.get("vibe") in vibe_cnt: vibe_cnt[sf.get("vibe")] += 1

    st.markdown("### 📌 피드백 요약")
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.markdown("<div class='smallcard'>", unsafe_allow_html=True)
        st.write("🌡️ 체감 온도")
        st.write(temp_cnt)
        st.markdown("</div>", unsafe_allow_html=True)
    with c2:
        st.markdown("<div class='smallcard'>", unsafe_allow_html=True)
        st.write("🎨 색 조합")
        st.write(color_cnt)
        st.markdown("</div>", unsafe_allow_html=True)
    with c3:
        st.markdown("<div class='smallcard'>", unsafe_allow_html=True)
        st.write("🧩 패턴 조합")
        st.write(pattern_cnt)
        st.markdown("</div>", unsafe_allow_html=True)
    with c4:
        st.markdown("<div class='smallcard'>", unsafe_allow_html=True)
        st.write("🧠 분위기(vibe)")
        st.write(vibe_cnt)
        st.markdown("</div>", unsafe_allow_html=True)

    if ratings:
        st.markdown("### ⭐ 별점 분포")
        # Streamlit 내장 차트로 간단히
        dist = {i: 0 for i in range(1, 6)}
        for r in ratings:
            dist[r] += 1
        st.bar_chart(dist)

    st.markdown("### 🧠 학습된 취향 Top")
    def top_items(d, n=6):
        return sorted((d or {}).items(), key=lambda x: x[1], reverse=True)[:n]

    colA, colB, colC = st.columns(3)
    with colA:
        st.markdown("<div class='smallcard'>", unsafe_allow_html=True)
        st.write("🎨 색 선호/비선호")
        st.write("선호:", top_items(taste.get("color_pref", {})))
        st.write("비선호:", top_items(taste.get("color_avoid", {})))
        st.markdown("</div>", unsafe_allow_html=True)

    with colB:
        st.markdown("<div class='smallcard'>", unsafe_allow_html=True)
        st.write("🧩 패턴 선호/비선호")
        st.write("선호:", top_items(taste.get("pattern_pref", {})))
        st.write("비선호:", top_items(taste.get("pattern_avoid", {})))
        st.markdown("</div>", unsafe_allow_html=True)

    with colC:
        st.markdown("<div class='smallcard'>", unsafe_allow_html=True)
        st.write("🧠 vibe 선호/비선호")
        st.write("선호:", top_items(taste.get("vibe_pref", {})))
        st.write("비선호:", top_items(taste.get("vibe_avoid", {})))
        st.markdown("</div>", unsafe_allow_html=True)

    st.markdown("### 🧾 최근 피드백 로그")
    # 최근 20개 테이블
    recent = list(reversed(logs[-20:]))
    rows = []
    for l in recent:
        sf = l.get("style_feedback", {}) or {}
        rows.append({
            "time": l.get("time",""),
            "rating": l.get("rating",""),
            "temp": l.get("temp_feedback",""),
            "color": sf.get("color",""),
            "pattern": sf.get("pattern",""),
            "vibe": sf.get("vibe",""),
            "note": l.get("note",""),
        })
    st.dataframe(rows, use_container_width=True)
