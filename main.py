import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

# =============================================================
# 기본 설정
# =============================================================
st.set_page_config(
    page_title="영화 데이터 그래프 도감 1 - 시간",
    page_icon="🎬",
    layout="wide",
)

DATA_URL = "https://raw.githubusercontent.com/greatsong/modudata/main/data/kobis_daily.csv"


# =============================================================
# 데이터 불러오기
# =============================================================
@st.cache_data
def load_data(url: str) -> pd.DataFrame:
    """KOBIS 일별 박스오피스 데이터를 불러오고 날짜 열을 날짜형으로 변환한다."""
    df = pd.read_csv(url)

    # 날짜 열 이름 찾기 (파일에 따라 '날짜' 또는 'date' 등일 수 있어 안전하게 처리)
    date_col = None
    for c in df.columns:
        if str(c).strip() in ("날짜", "date", "일자", "Date"):
            date_col = c
            break
    if date_col is None:
        date_col = df.columns[0]  # 첫 번째 열을 날짜로 가정

    # 20240101 같은 8자리 숫자를 진짜 날짜(datetime)로 변환
    df[date_col] = pd.to_datetime(
        df[date_col].astype(str).str.replace("-", "", regex=False).str.strip(),
        format="%Y%m%d",
        errors="coerce",
    )
    df = df.rename(columns={date_col: "날짜"})
    df = df.dropna(subset=["날짜"])

    # 숫자 열은 숫자형으로 정리
    for col in ["순위", "일관객", "누적관객", "스크린수", "상영횟수"]:
        if col in df.columns:
            df[col] = pd.to_numeric(
                df[col].astype(str).str.replace(",", "", regex=False),
                errors="coerce",
            )

    return df.sort_values("날짜").reset_index(drop=True)


df = load_data(DATA_URL)


# =============================================================
# 공통 도구 : 그래프 아래 설명 문구 자리
# =============================================================
def insight_box(text: str = ""):
    """그래프마다 '이 그래프로 알 수 있는 것' 한 문장을 넣는 자리."""
    st.markdown("**💡 이 그래프로 알 수 있는 것**")
    st.info(text if text else "여기에 한 문장으로 정리해 보세요.")


# =============================================================
# 사이드바 : 데이터 요약
# =============================================================
with st.sidebar:
    st.header("📦 데이터 정보")
    st.write(f"- 행 개수 : **{len(df):,}행**")
    st.write(f"- 기간 : **{df['날짜'].min().date()} ~ {df['날짜'].max().date()}**")
    st.write(f"- 영화 수 : **{df['영화명'].nunique():,}편**")
    with st.expander("원본 데이터 미리 보기"):
        st.dataframe(df.head(20), use_container_width=True)


# =============================================================
# 제목
# =============================================================
st.title("🎬 영화 데이터 그래프 도감 1 - 시간")
st.caption("1년치(365일) 일별 박스오피스 10위권 기록으로 '시간에 따른 변화'를 살펴봅니다.")
st.divider()


# =============================================================
# 구역 1 : 영화 한 편의 일별 관객수 변화 (선 그래프)
# =============================================================
def section_1_daily_audience(df: pd.DataFrame):
    st.header("1️⃣ 한 영화의 일별 관객수 변화")
    st.write("영화를 하나 고르면, 그 영화가 박스오피스 10위권에 있었던 날들의 일관객 수를 선 그래프로 보여 줍니다.")

    # 관객이 많은 영화가 위로 오도록 정렬해서 고르기 쉽게 만들기
    movie_order = (
        df.groupby("영화명")["일관객"].sum().sort_values(ascending=False).index.tolist()
    )
    movie = st.selectbox("영화를 선택하세요", movie_order, index=0, key="sec1_movie")

    one = df[df["영화명"] == movie].sort_values("날짜")

    fig = px.line(
        one,
        x="날짜",
        y="일관객",
        markers=True,
        title=f"「{movie}」 날짜별 일관객 수",
        labels={"날짜": "날짜", "일관객": "일별 관객수(명)"},
    )
    fig.update_traces(
        hovertemplate="날짜: %{x|%Y-%m-%d}<br>관객수: %{y:,.0f}명<extra></extra>"
    )
    fig.update_layout(hovermode="x unified", yaxis_tickformat=",")

    st.plotly_chart(fig, use_container_width=True)

    # 간단한 요약 지표
    c1, c2, c3 = st.columns(3)
    c1.metric("10위권 진입 일수", f"{len(one):,}일")
    c2.metric("최고 일관객", f"{one['일관객'].max():,.0f}명")
    c3.metric("최고 기록일", f"{one.loc[one['일관객'].idxmax(), '날짜'].date()}")

    insight_box("예) 개봉 직후 관객수가 가장 높고, 이후 점점 줄어드는 모습을 볼 수 있다.")


section_1_daily_audience(df)
st.divider()


# =============================================================
# 구역 2 : 일관객 합계 TOP 5 영화 비교 (여러 선 그래프)
# =============================================================
def section_2_top5_compare(df: pd.DataFrame):
    st.header("2️⃣ 관객수 TOP 5 영화의 일관객 비교")
    st.write(
        "이 기간 동안 **일관객 합계가 가장 큰 5편**을 골라, 날짜별 일관객 변화를 한 그래프에 겹쳐 그렸습니다. "
        "오른쪽 범례에서 영화 이름을 **클릭하면 켜고 끌 수 있고**, **더블클릭하면 그 영화만** 볼 수 있어요."
    )

    # ① 영화별 일관객 합계를 구해서 상위 5편 뽑기
    total_by_movie = df.groupby("영화명")["일관객"].sum().sort_values(ascending=False)
    top5 = total_by_movie.head(5)
    top5_names = top5.index.tolist()

    # ② 상위 5편에 해당하는 행만 남기기
    top5_df = df[df["영화명"].isin(top5_names)].sort_values(["영화명", "날짜"])

    # ③ 범례 순서를 관객수 많은 순으로 고정
    fig = px.line(
        top5_df,
        x="날짜",
        y="일관객",
        color="영화명",
        markers=True,
        title="일관객 합계 TOP 5 영화의 날짜별 일관객 수",
        labels={"날짜": "날짜", "일관객": "일별 관객수(명)", "영화명": "영화"},
        category_orders={"영화명": top5_names},
    )
    fig.update_traces(
        hovertemplate="%{fullData.name}<br>날짜: %{x|%Y-%m-%d}<br>관객수: %{y:,.0f}명<extra></extra>"
    )
    fig.update_layout(
        hovermode="closest",
        yaxis_tickformat=",",
        legend=dict(
            title="영화 (클릭: 켜기/끄기, 더블클릭: 혼자 보기)",
            orientation="h",
            yanchor="bottom",
            y=-0.35,
            xanchor="left",
            x=0,
        ),
    )

    st.plotly_chart(fig, use_container_width=True)

    # ④ TOP 5 요약 표
    with st.expander("📋 TOP 5 영화 요약 표 보기"):
        summary = (
            top5_df.groupby("영화명")
            .agg(
                일관객_합계=("일관객", "sum"),
                최고_일관객=("일관객", "max"),
                최고_기록일=("날짜", lambda s: s.loc[top5_df.loc[s.index, "일관객"].idxmax()].date()),
                첫_등장일=("날짜", "min"),
                마지막_등장일=("날짜", "max"),
                진입_일수=("날짜", "count"),
            )
            .loc[top5_names]
            .reset_index()
        )
        st.dataframe(summary, use_container_width=True, hide_index=True)

    insight_box(
        "예) 다섯 영화 모두 개봉 직후 정점을 찍고 감소하지만, 정점의 높이와 인기가 유지되는 기간은 영화마다 다르다."
    )


section_2_top5_compare(df)
st.divider()


# =============================================================
# 구역 3 : 날짜별 10위권 일관객 합계 (영역 그래프 + 최고 3일 표시)
# =============================================================
def section_3_daily_total(df: pd.DataFrame):
    st.header("3️⃣ 극장가 전체 흐름 — 날짜별 10위권 관객 합계")
    st.write(
        "하루하루 **10위권 영화 관객수를 모두 더한 값**을 영역 그래프로 그렸습니다. "
        "1년 동안 극장가가 언제 붐볐고 언제 한산했는지 한눈에 볼 수 있어요. "
        "가장 관객이 많았던 **상위 3일**은 그래프 위에 ★ 표시와 날짜를 적어 두었습니다."
    )

    # ① 날짜별로 묶어서 일관객 합계 구하기
    daily = (
        df.groupby("날짜", as_index=False)["일관객"]
        .sum()
        .rename(columns={"일관객": "합계관객"})
        .sort_values("날짜")
        .reset_index(drop=True)
    )

    # ② 합계가 가장 컸던 3일 뽑기
    top3 = daily.nlargest(3, "합계관객").sort_values("합계관객", ascending=False)

    # ③ 영역 그래프 그리기
    fig = px.area(
        daily,
        x="날짜",
        y="합계관객",
        title="날짜별 박스오피스 10위권 관객수 합계",
        labels={"날짜": "날짜", "합계관객": "그날 10위권 관객수 합계(명)"},
    )
    fig.update_traces(
        line=dict(width=1.5, color="#1f77b4"),
        fillcolor="rgba(31, 119, 180, 0.25)",
        hovertemplate="날짜: %{x|%Y-%m-%d}<br>합계: %{y:,.0f}명<extra></extra>",
    )

    # ④ 상위 3일에 ★ 마커와 날짜 라벨 얹기
    fig.add_trace(
        go.Scatter(
            x=top3["날짜"],
            y=top3["합계관객"],
            mode="markers+text",
            marker=dict(size=14, color="crimson", symbol="star",
                        line=dict(width=1, color="white")),
            text=[d.strftime("%Y-%m-%d") for d in top3["날짜"]],
            textposition="top center",
            textfont=dict(size=12, color="crimson"),
            name="관객 최다 3일",
            hovertemplate="🏆 %{x|%Y-%m-%d}<br>합계: %{y:,.0f}명<extra></extra>",
            cliponaxis=False,
        )
    )

    # ⑤ 라벨이 잘리지 않도록 y축 위쪽에 여유 주기
    y_max = daily["합계관객"].max()
    fig.update_layout(
        hovermode="x unified",
        yaxis_tickformat=",",
        yaxis_range=[0, y_max * 1.18],
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
    )

    st.plotly_chart(fig, use_container_width=True)

    # ⑥ 최다 3일 정보 카드
    st.markdown("**🏆 관객이 가장 많았던 3일**")
    cols = st.columns(3)
    medals = ["🥇", "🥈", "🥉"]
    weekday_kr = ["월", "화", "수", "목", "금", "토", "일"]
    for i, (col, (_, row)) in enumerate(zip(cols, top3.iterrows())):
        d = row["날짜"]
        col.metric(
            label=f"{medals[i]} {d.strftime('%Y-%m-%d')} ({weekday_kr[d.weekday()]})",
            value=f"{row['합계관객']:,.0f}명",
        )

    # ⑦ 그날 1위 영화가 무엇이었는지 확인해 보기
    with st.expander("🔎 그 3일에 어떤 영화가 상위권이었을까?"):
        detail = (
            df[df["날짜"].isin(top3["날짜"])]
            .sort_values(["날짜", "순위"])[["날짜", "순위", "영화명", "일관객", "스크린수"]]
        )
        detail["날짜"] = detail["날짜"].dt.strftime("%Y-%m-%d")
        st.dataframe(detail, use_container_width=True, hide_index=True)

    insight_box(
        "예) 관객수는 1년 내내 고르지 않고, 방학·연휴·대작 개봉 시기에 뾰족하게 솟아오른다."
    )


section_3_daily_total(df)
st.divider()


# =============================================================
# 구역 4 : 영화별 총관객 TOP 10 (가로 막대그래프)
# =============================================================
def section_4_top10_bar(df: pd.DataFrame):
    st.header("4️⃣ 영화별 총관객 TOP 10")
    st.write(
        "이 기간 동안 각 영화가 10위권에서 모은 **일관객을 모두 더해** 상위 10편을 뽑았습니다. "
        "막대에 마우스를 올리면 **10위권에 머문 날수**도 함께 볼 수 있어요."
    )

    # ① 영화별로 합계관객 + 진입일수를 한 번에 계산
    movie_stats = (
        df.groupby("영화명")
        .agg(
            합계관객=("일관객", "sum"),
            진입일수=("날짜", "nunique"),
            최고일관객=("일관객", "max"),
            최고순위=("순위", "min"),
        )
        .reset_index()
    )

    # ② 합계관객 기준 TOP 10
    top10 = movie_stats.nlargest(10, "합계관객").reset_index(drop=True)

    # ③ 하루 평균 관객도 계산해 두기
    top10["일평균관객"] = top10["합계관객"] / top10["진입일수"]

    # ④ 가로 막대그래프 — 관객 많은 영화가 위로 오게
    #    (y축은 아래에서 위로 그려지므로, 적은 순서로 정렬해야 큰 값이 맨 위에 온다)
    plot_df = top10.sort_values("합계관객", ascending=True)

    fig = px.bar(
        plot_df,
        x="합계관객",
        y="영화명",
        orientation="h",
        title="일관객 합계 TOP 10 영화",
        labels={"합계관객": "총관객수(명)", "영화명": ""},
        color="합계관객",
        color_continuous_scale="Blues",
        text="합계관객",
        custom_data=["진입일수", "일평균관객", "최고일관객", "최고순위"],
    )

    # ⑤ 툴팁에 진입일수 등 추가 정보 넣기
    fig.update_traces(
        texttemplate="%{x:,.0f}",
        textposition="outside",
        cliponaxis=False,
        hovertemplate=(
            "<b>%{y}</b><br>"
            "총관객수: %{x:,.0f}명<br>"
            "10위권에 든 날수: %{customdata[0]:,.0f}일<br>"
            "하루 평균 관객: %{customdata[1]:,.0f}명<br>"
            "최고 일관객: %{customdata[2]:,.0f}명<br>"
            "최고 순위: %{customdata[3]:.0f}위"
            "<extra></extra>"
        ),
    )

    x_max = top10["합계관객"].max()
    fig.update_layout(
        xaxis_tickformat=",",
        xaxis_range=[0, x_max * 1.15],   # 막대 끝 숫자가 잘리지 않도록 여유
        height=520,
        coloraxis_showscale=False,       # 색 막대(범례) 숨기기
        margin=dict(l=10, r=10, t=60, b=10),
        yaxis=dict(tickfont=dict(size=13)),
    )

    st.plotly_chart(fig, use_container_width=True)

    # ⑥ 순위표
    with st.expander("📋 TOP 10 순위표 보기"):
        table = top10.copy()
        table.insert(0, "순위", range(1, len(table) + 1))
        table = table[["순위", "영화명", "합계관객", "진입일수", "일평균관객", "최고일관객", "최고순위"]]
        st.dataframe(
            table,
            use_container_width=True,
            hide_index=True,
            column_config={
                "합계관객": st.column_config.NumberColumn("총관객수", format="%,d명"),
                "진입일수": st.column_config.NumberColumn("10위권 날수", format="%d일"),
                "일평균관객": st.column_config.NumberColumn("하루 평균", format="%,d명"),
                "최고일관객": st.column_config.NumberColumn("최고 일관객", format="%,d명"),
                "최고순위": st.column_config.NumberColumn("최고 순위", format="%d위"),
            },
        )

    insight_box(
        "예) 총관객이 많다고 해서 10위권에 오래 머문 것은 아니며, "
        "짧고 굵게 흥행한 영화와 길게 버틴 영화가 나뉜다."
    )


section_4_top10_bar(df)
st.divider()


# =============================================================
# 구역 5 : (준비 중) — 앞으로 그래프를 추가할 자리
# =============================================================
def section_5_placeholder(df: pd.DataFrame):
    st.header("5️⃣ (다음 그래프 자리)")
    st.write("여기에 새로운 그래프를 추가할 예정입니다.")
    st.empty()
    insight_box("")


section_5_placeholder(df)
