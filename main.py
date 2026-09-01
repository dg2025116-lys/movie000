# ============================================================
# KOBIS 일별 박스오피스 조회 앱 (Streamlit)
# - 달력에서 날짜를 고르면 그날의 박스오피스를 표/카드/그래프로 보여 줍니다.
# - 고를 수 있는 가장 늦은 날짜는 '어제'(한국 시간 기준)입니다.
# ============================================================

# ── 1) 필요한 도구(라이브러리) 불러오기 ──────────────────────
import datetime as dt              # 날짜/시간 계산용
from zoneinfo import ZoneInfo      # '한국 시간대'를 정확히 다루기 위한 도구 (파이썬 3.9+)

import requests                    # 인터넷으로 API를 호출할 때 사용
import pandas as pd                # 표(데이터프레임)를 다루는 도구
import streamlit as st             # 웹 화면을 만들어 주는 도구


# ── 2) 페이지 기본 설정 ──────────────────────────────────────
st.set_page_config(page_title="박스오피스 조회", page_icon="🎬", layout="wide")

st.title("🎬 일별 박스오피스 조회")
st.caption("자료 출처: 영화진흥위원회(KOBIS) 오픈API")


# ── 3) 상수(값이 변하지 않는 이름표) 정의 ────────────────────
API_URL = (
    "https://www.kobis.or.kr/kobisopenapi/webservice/rest/"
    "boxoffice/searchDailyBoxOfficeList.json"
)

# 한국 표준시(KST). 배포 서버는 보통 UTC라서 반드시 변환이 필요합니다.
KST = ZoneInfo("Asia/Seoul")

# KOBIS 오픈API가 제공하는 가장 이른 날짜(2004-01-01)
MIN_DATE = dt.date(2004, 1, 1)

# 누적관객 '100만 명' 기준선 (트로피를 붙일 기준)
MILLION = 1_000_000


# ── 4) '어제' 날짜를 한국 시간 기준으로 계산하는 함수 ────────
def get_yesterday_kst() -> dt.date:
    """
    한국 시간 기준 '어제' 날짜를 date 객체로 돌려줍니다.

    왜 이렇게 하나요?
    - 서버 시계가 UTC이면 한국보다 9시간 느립니다.
      예) 한국 6월 2일 오전 5시  →  서버(UTC)는 6월 1일 오후 8시
      그래서 서버 시각으로 '어제'를 구하면 하루가 어긋날 수 있습니다.
    - KOBIS는 '오늘' 자료를 아직 집계하지 않으므로 어제까지만 고를 수 있게 합니다.
    """
    now_kst = dt.datetime.now(KST)                 # 지금 이 순간을 '한국 시간'으로
    return now_kst.date() - dt.timedelta(days=1)   # 하루 빼기


# ── 5) 문자열 숫자를 진짜 숫자로 바꾸는 함수 ─────────────────
def to_int(value) -> int:
    """
    KOBIS는 관객수·순위증감 같은 값을 '문자열'로 보내 줍니다. (예: "123456", "-2")
    가끔 "1,234" 처럼 쉼표가 섞이거나 빈 값이 올 수 있으므로 안전하게 정수로 바꿉니다.
    실패하면 0을 돌려줍니다.
    """
    try:
        return int(str(value).replace(",", "").strip())
    except (ValueError, AttributeError, TypeError):
        return 0


# ── 6) 순위 증감(rankInten)을 화살표 글자로 바꾸는 함수 ──────
def format_rank_inten(inten: int) -> str:
    """
    전날 대비 순위 증감을 보기 좋은 글자로 바꿉니다.

    rankInten 값의 뜻
      양수(+2) : 순위가 2계단 '올랐다'  → 빨간 위 화살표 🔺
      음수(-3) : 순위가 3계단 '내렸다'  → 파란 아래 화살표 🔻
      0        : 변동 없음              → 가로줄 ➖

    ※ abs()는 절댓값(부호를 뗀 크기)을 구하는 함수입니다.
       -3의 절댓값은 3이므로 "🔻 3"처럼 깔끔하게 표시됩니다.
    """
    if inten > 0:
        return f"🔺 {inten}"      # 🔺 = 빨간 위쪽 삼각형(상승)
    elif inten < 0:
        return f"🔻 {abs(inten)}"  # 🔻 = 파란 아래쪽 삼각형(하락)
    else:
        return "➖ 0"              # 변동 없음


# ── 7) 누적관객 100만 돌파 시 트로피를 붙이는 함수 ───────────
def decorate_movie_name(name: str, audi_acc: int) -> str:
    """
    누적관객이 100만 명 이상이면 영화명 앞에 트로피 이모지를 붙입니다.
    (100만은 흔히 '흥행 성공'의 기준선으로 이야기됩니다.)
    """
    if audi_acc >= MILLION:
        return f"🏆 {name}"
    return name


# ── 8) API를 호출하는 함수 (1시간 캐시) ──────────────────────
# @st.cache_data : 같은 인자(target_dt)로 다시 부르면 인터넷에 다시 나가지 않고
#                  저장해 둔 결과를 그대로 돌려줍니다.
# ttl=3600       : 3600초 = 1시간 동안만 기억합니다.
@st.cache_data(ttl=3600, show_spinner="박스오피스 자료를 불러오는 중입니다...")
def fetch_boxoffice(target_dt: str, api_key: str) -> dict:
    """
    KOBIS 일별 박스오피스 API를 호출해 결과를 사전(dict)으로 돌려줍니다.

    반환 형태(항상 "status" 열쇠를 가집니다):
      {"status": "OK",    "data": [영화 목록]}      # 성공
      {"status": "EMPTY"}                           # 목록이 비어 있음(집계 전)
      {"status": "ERROR", "error": "안내문"}        # 그 밖의 오류
    """
    params = {"key": api_key, "targetDt": target_dt}

    # (1) 네트워크 단계에서 생길 수 있는 문제를 try/except로 감쌉니다.
    try:
        response = requests.get(API_URL, params=params, timeout=10)  # 10초 안에 응답 없으면 포기
        response.raise_for_status()   # 상태코드가 400/500이면 예외 발생
        result = response.json()      # 받은 JSON 글자를 파이썬 사전으로 변환
    except requests.exceptions.Timeout:
        return {"status": "ERROR", "error": "요청 시간이 초과되었습니다. 잠시 후 다시 시도해 주세요."}
    except requests.exceptions.RequestException as e:
        return {"status": "ERROR", "error": f"네트워크 요청에 실패했습니다. (자세한 내용: {e})"}
    except ValueError:
        # json() 변환 실패 = 응답이 JSON이 아님 (점검 페이지 등이 올 때)
        return {"status": "ERROR", "error": "응답을 해석할 수 없습니다. KOBIS 서비스 점검 중일 수 있습니다."}

    # (2) 인증키가 틀려도 상태코드는 200입니다. 대신 faultInfo 상자가 옵니다.
    if "faultInfo" in result:
        fault = result.get("faultInfo", {})
        message = fault.get("message", "알 수 없는 오류")
        code = fault.get("errorCode", "-")
        return {"status": "ERROR", "error": f"KOBIS가 오류를 돌려주었습니다. (코드 {code}) {message}"}

    # (3) 정상 응답이면 boxOfficeResult > dailyBoxOfficeList 순서로 꺼냅니다.
    box_office_result = result.get("boxOfficeResult", {})
    movie_list = box_office_result.get("dailyBoxOfficeList", [])

    # (4) 목록이 비어 있는 경우 → 아직 집계되지 않은 날짜
    if not movie_list:
        return {"status": "EMPTY"}

    return {"status": "OK", "data": movie_list}


# ── 9) 받아온 목록을 표(DataFrame)로 정리하는 함수 ───────────
def build_dataframe(movie_list: list) -> pd.DataFrame:
    """
    영화 목록(사전들의 리스트)을 표로 바꾸고,
    문자열로 온 숫자들을 진짜 숫자 자료형으로 바꿔 줍니다.
    또한 화살표·트로피 같은 '보여 주기용' 열도 함께 만듭니다.
    """
    rows = []   # 한 줄씩 담아 둘 빈 상자
    for movie in movie_list:
        # 먼저 문자열 → 숫자로 변환
        audi_acc = to_int(movie.get("audiAcc"))     # 누적관객
        inten = to_int(movie.get("rankInten"))      # 순위 증감
        raw_name = movie.get("movieNm", "-")        # 원래 영화명

        rows.append({
            "순위": to_int(movie.get("rank")),
            "증감": format_rank_inten(inten),                    # 표에 보여 줄 화살표 글자
            "영화명": decorate_movie_name(raw_name, audi_acc),   # 트로피가 붙을 수 있는 이름
            "개봉일": movie.get("openDt", "-"),
            "관객수": to_int(movie.get("audiCnt")),
            "누적관객": audi_acc,
            "스크린수": to_int(movie.get("scrnCnt")),
            "상영횟수": to_int(movie.get("showCnt")),
            # 아래 두 열은 계산·정렬용 '숨은 열'입니다. 화면 표에는 넣지 않습니다.
            "_원래영화명": raw_name,
            "_증감숫자": inten,
        })

    df = pd.DataFrame(rows)                              # 리스트 → 표로 변환
    df = df.sort_values("순위").reset_index(drop=True)   # 순위 오름차순 정렬
    return df


# ============================================================
#                      화면 그리기 (실행 부분)
# ============================================================

# ── 10) 비밀 금고(secrets)에서 인증키 꺼내기 ─────────────────
# 인증키를 코드에 직접 적으면 깃허브에 공개되어 위험합니다.
# 스트림릿 클라우드 > App settings > Secrets 에 아래처럼 저장하세요.
#   KOBIS_KEY = "여기에_발급받은_인증키"
try:
    API_KEY = st.secrets["KOBIS_KEY"]
except (KeyError, FileNotFoundError):
    st.error("🔑 인증키를 찾을 수 없습니다.")
    st.markdown(
        """
        **이렇게 확인해 보세요.**
        1. 스트림릿 클라우드 화면 오른쪽 아래 **⋮ → Settings → Secrets** 로 들어갑니다.
        2. 아래 한 줄을 그대로 넣고 저장합니다. (따옴표 포함)
           ```
           KOBIS_KEY = "발급받은_인증키"
           ```
        3. 내 컴퓨터에서 실행 중이라면 프로젝트 폴더에
           `.streamlit/secrets.toml` 파일을 만들고 같은 내용을 적습니다.
        4. 저장 후 앱을 다시 실행(Reboot)합니다.
        """
    )
    st.stop()   # 인증키가 없으면 여기서 멈춤


# ── 11) 달력에서 날짜 고르기 ─────────────────────────────────
yesterday = get_yesterday_kst()   # 고를 수 있는 가장 늦은 날짜

with st.sidebar:
    st.header("📅 날짜 선택")

    # st.date_input : 달력 위젯
    #   value     : 처음 화면에 보일 기본 날짜 (어제)
    #   min_value : 고를 수 있는 가장 이른 날짜
    #   max_value : 고를 수 있는 가장 늦은 날짜 → '어제'로 막아 둡니다.
    selected_date = st.date_input(
        "조회할 날짜를 고르세요",
        value=yesterday,
        min_value=MIN_DATE,
        max_value=yesterday,
        format="YYYY-MM-DD",
    )

    st.caption("오늘 자료는 아직 집계 전이라 **어제까지만** 고를 수 있습니다.")

    st.divider()
    st.header("ℹ️ 안내")
    st.write(f"현재 한국 시각: **{dt.datetime.now(KST).strftime('%Y-%m-%d %H:%M')}**")
    st.write("같은 날짜는 **1시간 동안** 저장해 두고 다시 사용합니다.")

    st.markdown(
        """
        **표 기호 읽는 법**
        - 🔺 : 전날보다 순위 **상승**
        - 🔻 : 전날보다 순위 **하락**
        - ➖ : 변동 없음
        - 🏆 : 누적관객 **100만 명** 돌파
        """
    )

    if st.button("🔄 캐시 지우고 다시 불러오기"):
        st.cache_data.clear()   # 저장해 둔 결과를 모두 지움
        st.rerun()              # 앱을 처음부터 다시 실행


# ── 12) 고른 날짜를 API가 원하는 형태로 바꾸기 ───────────────
# strftime("%Y%m%d") : date(2025, 6, 1) → "20250601"
target_dt = selected_date.strftime("%Y%m%d")

# 화면에 보기 좋은 형태(2025-06-01)
pretty_date = selected_date.strftime("%Y-%m-%d")
st.subheader(f"📅 {pretty_date} 박스오피스")


# ── 13) 자료 불러오기 ────────────────────────────────────────
result = fetch_boxoffice(target_dt, API_KEY)

# (가) 목록이 비어 있는 경우 → '집계 전' 안내
if result["status"] == "EMPTY":
    st.warning(f"📭 {pretty_date}는 아직 집계 전입니다.")
    st.markdown(
        """
        **이런 점을 확인해 보세요.**
        - KOBIS 일별 자료는 보통 **다음 날 오전**에 갱신됩니다. 조금 뒤에 다시 시도해 보세요.
        - 너무 오래된 날짜는 자료가 없을 수 있습니다.
        - 왼쪽 사이드바에서 **다른 날짜**를 골라 보세요.
        """
    )
    st.stop()

# (나) 그 밖의 오류 → 원인과 확인 방법 안내
if result["status"] == "ERROR":
    st.error(f"⚠️ 자료를 가져오지 못했습니다.\n\n{result['error']}")
    st.markdown(
        """
        **이런 점을 확인해 보세요.**
        - **인증키**: KOBIS에서 발급받은 키가 맞는지, 앞뒤에 빈칸이 섞이지 않았는지 확인하세요.
        - **키 상태**: 발급 직후에는 활성화까지 시간이 걸릴 수 있고, 일일 호출 한도를 넘으면 막힙니다.
        - **네트워크**: 인터넷 연결 또는 KOBIS 서버 점검 여부를 확인하세요.
        - 위 항목을 고친 뒤 왼쪽 사이드바의 **🔄 다시 불러오기** 버튼을 눌러 주세요.
        """
    )
    st.stop()


# ── 14) 표 만들기 ────────────────────────────────────────────
df = build_dataframe(result["data"])


# ── 15) 1위 영화를 지표 카드 세 장으로 크게 보여 주기 ────────
st.markdown("### 🥇 1위 영화")

top_movie = df.iloc[0]   # iloc[0] = 표의 첫 번째 줄 = 1위

col1, col2, col3 = st.columns(3)   # 화면을 가로로 3등분

with col1:
    st.metric(label="영화명", value=top_movie["영화명"])   # 트로피가 붙어 있으면 함께 표시
with col2:
    # f"{숫자:,}" : 천 단위마다 쉼표를 찍어 읽기 쉽게 만듭니다.
    st.metric(label="당일 관객수", value=f"{top_movie['관객수']:,} 명")
with col3:
    st.metric(label="누적 관객수", value=f"{top_movie['누적관객']:,} 명")

st.caption(
    f"개봉일: {top_movie['개봉일']} · "
    f"스크린수: {top_movie['스크린수']:,}개 · "
    f"전일 대비 순위: {top_movie['증감']}"
)


# ── 16) 전체 순위 표 보여 주기 ───────────────────────────────
st.markdown("### 📋 박스오피스 순위 (TOP 10)")

# 화면에 보여 줄 열만 골라 냅니다. (밑줄 _ 로 시작하는 숨은 열은 제외)
show_cols = ["순위", "증감", "영화명", "개봉일", "관객수", "누적관객", "스크린수"]

st.dataframe(
    df[show_cols],
    use_container_width=True,   # 화면 너비에 맞춰 표를 넓게
    hide_index=True,            # 왼쪽 0,1,2... 번호 숨기기
    column_config={
        "증감": st.column_config.TextColumn("전일대비", width="small"),
        "관객수": st.column_config.NumberColumn("관객수", format="%d"),
        "누적관객": st.column_config.NumberColumn("누적관객", format="%d"),
        "스크린수": st.column_config.NumberColumn("스크린수", format="%d"),
    },
)

# 100만 돌파 영화가 몇 편인지 세어 알려 줍니다.
# (조건에 맞는 줄만 고르는 방법: df[조건] → 그 결과의 길이를 len()으로 셈)
million_movies = df[df["누적관객"] >= MILLION]
if len(million_movies) > 0:
    names = ", ".join(million_movies["_원래영화명"].tolist())
    st.success(f"🏆 누적관객 100만 명 돌파 작품 {len(million_movies)}편: {names}")


# ── 17) 관객수 상위 5편 막대그래프 ───────────────────────────
st.markdown("### 📊 관객수 상위 5편")

# 관객수 기준 내림차순으로 정렬한 뒤 위에서 5개만 자릅니다.
top5 = df.sort_values("관객수", ascending=False).head(5)

# st.bar_chart는 '표의 index'를 가로축 이름으로 사용합니다.
# 그래프에는 트로피가 없는 원래 이름을 쓰는 편이 깔끔합니다.
chart_data = top5.set_index("_원래영화명")[["관객수"]]
chart_data.index.name = "영화명"   # 가로축 제목을 보기 좋게 바꿈

st.bar_chart(chart_data)

st.caption("가로축: 영화명 / 세로축: 해당 날짜 관객수(명)")
