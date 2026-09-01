# ============================================================
# KOBIS 일별 박스오피스 조회 앱 (Streamlit)
# - 어제(한국 시간 기준) 박스오피스를 표/카드/그래프로 보여 줍니다.
# ============================================================

# ── 1) 필요한 도구(라이브러리) 불러오기 ──────────────────────
import datetime as dt              # 날짜/시간 계산용
from zoneinfo import ZoneInfo      # '한국 시간대'를 정확히 다루기 위한 도구 (파이썬 3.9+)

import requests                    # 인터넷으로 API를 호출할 때 사용
import pandas as pd                # 표(데이터프레임)를 다루는 도구
import streamlit as st             # 웹 화면을 만들어 주는 도구


# ── 2) 페이지 기본 설정 ──────────────────────────────────────
# layout="wide" : 화면을 넓게 사용 (표가 시원하게 보임)
st.set_page_config(page_title="어제의 박스오피스", page_icon="🎬", layout="wide")

st.title("🎬 어제의 박스오피스")
st.caption("자료 출처: 영화진흥위원회(KOBIS) 오픈API")


# ── 3) 상수(값이 변하지 않는 이름표) 정의 ────────────────────
# API 주소는 코드 여기저기에 흩어 두지 않고 한 곳에 모아 두면 관리가 쉽습니다.
API_URL = (
    "https://www.kobis.or.kr/kobisopenapi/webservice/rest/"
    "boxoffice/searchDailyBoxOfficeList.json"
)

# 한국 표준시(KST) 시간대 객체.
# 배포 서버(스트림릿 클라우드)는 보통 UTC라서, 반드시 한국 시간으로 변환해야 합니다.
KST = ZoneInfo("Asia/Seoul")


# ── 4) '어제' 날짜를 한국 시간 기준으로 계산하는 함수 ────────
def get_yesterday_kst() -> str:
    """
    한국 시간 기준 '어제' 날짜를 'yyyymmdd' 형태의 문자열로 돌려줍니다.

    왜 이렇게 하나요?
    - 서버 시계가 UTC이면 한국보다 9시간 느립니다.
      예) 한국 6월 2일 오전 5시  →  서버(UTC)는 6월 1일 오후 8시
      그래서 서버 시각으로 '어제'를 구하면 하루가 어긋날 수 있습니다.
    - KOBIS는 '오늘' 자료를 아직 집계하지 않으므로 '어제'를 조회합니다.
    """
    now_kst = dt.datetime.now(KST)          # 지금 이 순간을 '한국 시간'으로 구하기
    yesterday = now_kst.date() - dt.timedelta(days=1)   # 하루 빼기
    return yesterday.strftime("%Y%m%d")     # 20250601 처럼 여덟 자리로 변환


# ── 5) 문자열 숫자를 진짜 숫자로 바꾸는 함수 ─────────────────
def to_int(value) -> int:
    """
    KOBIS는 관객수·스크린수 같은 값을 '문자열'로 보내 줍니다. (예: "123456")
    가끔 "1,234" 처럼 쉼표가 섞여 오거나 빈 값이 올 수도 있으므로
    안전하게 정수(int)로 바꿔 줍니다. 실패하면 0을 돌려줍니다.
    """
    try:
        # str()로 감싸 문자열로 만든 뒤, 쉼표와 공백을 제거하고 정수로 변환
        return int(str(value).replace(",", "").strip())
    except (ValueError, AttributeError, TypeError):
        return 0


# ── 6) API를 호출하는 함수 (1시간 캐시) ──────────────────────
# @st.cache_data : 같은 인자(target_dt)로 다시 부르면 인터넷에 다시 나가지 않고
#                  저장해 둔 결과를 그대로 돌려줍니다.
# ttl=3600       : 3600초 = 1시간 동안만 기억합니다. (Time To Live)
# show_spinner   : 불러오는 동안 보여 줄 안내 문구
@st.cache_data(ttl=3600, show_spinner="박스오피스 자료를 불러오는 중입니다...")
def fetch_boxoffice(target_dt: str, api_key: str) -> dict:
    """
    KOBIS 일별 박스오피스 API를 호출해 결과를 사전(dict)으로 돌려줍니다.

    반환 형태(항상 아래 두 가지 열쇠를 가집니다):
      {"ok": True,  "data": [영화 목록]}          # 성공
      {"ok": False, "error": "사람이 읽을 안내문"}  # 실패
    """
    # 요청에 함께 보낼 값들. key와 targetDt 두 가지가 필수입니다.
    params = {"key": api_key, "targetDt": target_dt}

    # (1) 네트워크 단계에서 생길 수 있는 문제를 try/except로 감쌉니다.
    try:
        response = requests.get(API_URL, params=params, timeout=10)  # 10초 안에 응답 없으면 포기
        response.raise_for_status()   # 상태코드가 400/500이면 예외를 일으킴
        result = response.json()      # 받은 JSON 글자를 파이썬 사전으로 변환
    except requests.exceptions.Timeout:
        return {"ok": False, "error": "요청 시간이 초과되었습니다. 잠시 후 다시 시도해 주세요."}
    except requests.exceptions.RequestException as e:
        return {"ok": False, "error": f"네트워크 요청에 실패했습니다. (자세한 내용: {e})"}
    except ValueError:
        # json() 변환 실패 = 응답이 JSON이 아님 (점검 페이지 등이 올 때)
        return {"ok": False, "error": "응답을 해석할 수 없습니다. KOBIS 서비스 점검 중일 수 있습니다."}

    # (2) 인증키가 틀려도 상태코드는 200입니다. 대신 faultInfo 상자가 옵니다.
    if "faultInfo" in result:
        fault = result.get("faultInfo", {})
        message = fault.get("message", "알 수 없는 오류")
        code = fault.get("errorCode", "-")
        return {
            "ok": False,
            "error": f"KOBIS가 오류를 돌려주었습니다. (코드 {code}) {message}",
        }

    # (3) 정상 응답이면 boxOfficeResult > dailyBoxOfficeList 순서로 꺼냅니다.
    #     .get()을 쓰면 열쇠가 없어도 오류 대신 기본값을 받습니다.
    box_office_result = result.get("boxOfficeResult", {})
    movie_list = box_office_result.get("dailyBoxOfficeList", [])

    # (4) 목록이 비어 있는 경우 (아직 집계 전이거나 날짜가 너무 이른 경우)
    if not movie_list:
        return {"ok": False, "error": "해당 날짜의 박스오피스 자료가 비어 있습니다."}

    return {"ok": True, "data": movie_list}


# ── 7) 받아온 목록을 표(DataFrame)로 정리하는 함수 ───────────
def build_dataframe(movie_list: list) -> pd.DataFrame:
    """
    영화 목록(사전들의 리스트)을 표로 바꾸고,
    문자열로 온 숫자들을 진짜 숫자 자료형으로 바꿔 줍니다.
    """
    rows = []   # 한 줄씩 담아 둘 빈 상자
    for movie in movie_list:
        rows.append({
            "순위": to_int(movie.get("rank")),
            "영화명": movie.get("movieNm", "-"),
            "개봉일": movie.get("openDt", "-"),
            "관객수": to_int(movie.get("audiCnt")),
            "누적관객": to_int(movie.get("audiAcc")),
            "스크린수": to_int(movie.get("scrnCnt")),
            "상영횟수": to_int(movie.get("showCnt")),
            "전일대비": to_int(movie.get("rankInten")),
        })

    df = pd.DataFrame(rows)             # 리스트 → 표로 변환
    df = df.sort_values("순위").reset_index(drop=True)  # 순위 오름차순 정렬
    return df


# ============================================================
#                      화면 그리기 (실행 부분)
# ============================================================

# ── 8) 비밀 금고(secrets)에서 인증키 꺼내기 ──────────────────
# 인증키를 코드에 직접 적으면 깃허브에 그대로 공개되어 위험합니다.
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
    st.stop()   # 인증키가 없으면 아래 코드를 실행하지 않고 여기서 멈춤


# ── 9) 조회 날짜 정하기 ──────────────────────────────────────
target_dt = get_yesterday_kst()

# 화면에 보기 좋은 형태(2025-06-01)로도 만들어 둡니다.
pretty_date = f"{target_dt[:4]}-{target_dt[4:6]}-{target_dt[6:]}"
st.subheader(f"📅 조회 날짜: {pretty_date} (한국 시간 기준 어제)")

# 사이드바에 참고 정보와 새로고침 버튼을 둡니다.
with st.sidebar:
    st.header("ℹ️ 안내")
    st.write(f"현재 한국 시각: **{dt.datetime.now(KST).strftime('%Y-%m-%d %H:%M')}**")
    st.write("같은 날짜는 **1시간 동안** 저장해 두고 다시 사용합니다.")
    if st.button("🔄 캐시 지우고 다시 불러오기"):
        st.cache_data.clear()   # 저장해 둔 결과를 모두 지움
        st.rerun()              # 앱을 처음부터 다시 실행


# ── 10) 자료 불러오기 ────────────────────────────────────────
result = fetch_boxoffice(target_dt, API_KEY)

# 실패한 경우: 빈 화면 대신 원인과 확인 방법을 알려 줍니다.
if not result["ok"]:
    st.error(f"⚠️ 자료를 가져오지 못했습니다.\n\n{result['error']}")
    st.markdown(
        """
        **이런 점을 확인해 보세요.**
        - **인증키**: KOBIS 사이트에서 발급받은 키가 맞는지, 앞뒤에 빈칸이 섞이지 않았는지 확인하세요.
        - **키 상태**: 발급 직후에는 활성화까지 시간이 걸릴 수 있고, 일일 호출 한도를 넘으면 막힙니다.
        - **날짜**: 조회 날짜가 너무 최근이면 아직 집계 전일 수 있습니다. (보통 오전 중에 갱신)
        - **네트워크**: 인터넷 연결 또는 KOBIS 서버 점검 여부를 확인하세요.
        - 위 항목을 고친 뒤 왼쪽 사이드바의 **🔄 다시 불러오기** 버튼을 눌러 주세요.
        """
    )
    st.stop()   # 여기서 실행을 멈춤 (아래 표/그래프를 그리지 않음)


# ── 11) 표 만들기 ────────────────────────────────────────────
df = build_dataframe(result["data"])


# ── 12) 1위 영화를 지표 카드 세 장으로 크게 보여 주기 ────────
st.markdown("### 🥇 1위 영화")

top_movie = df.iloc[0]   # iloc[0] = 표의 첫 번째 줄 = 1위

# st.columns(3) : 화면을 가로로 3등분
col1, col2, col3 = st.columns(3)

with col1:
    st.metric(label="영화명", value=top_movie["영화명"])
with col2:
    # f"{숫자:,}" : 천 단위마다 쉼표를 찍어 읽기 쉽게 만듭니다.
    st.metric(label="어제 관객수", value=f"{top_movie['관객수']:,} 명")
with col3:
    st.metric(label="누적 관객수", value=f"{top_movie['누적관객']:,} 명")

st.caption(f"개봉일: {top_movie['개봉일']} · 스크린수: {top_movie['스크린수']:,}개")


# ── 13) 전체 순위 표 보여 주기 ───────────────────────────────
st.markdown("### 📋 박스오피스 순위 (TOP 10)")

# 요청받은 항목만 골라서 보여 줍니다.
show_cols = ["순위", "영화명", "개봉일", "관객수", "누적관객", "스크린수"]

st.dataframe(
    df[show_cols],
    use_container_width=True,   # 화면 너비에 맞춰 표를 넓게
    hide_index=True,            # 왼쪽 0,1,2... 번호 숨기기
    column_config={
        # NumberColumn: 숫자 열에 천 단위 쉼표를 붙여 표시
        "관객수": st.column_config.NumberColumn("관객수", format="%d"),
        "누적관객": st.column_config.NumberColumn("누적관객", format="%d"),
        "스크린수": st.column_config.NumberColumn("스크린수", format="%d"),
    },
)


# ── 14) 관객수 상위 5편 막대그래프 ───────────────────────────
st.markdown("### 📊 관객수 상위 5편")

# 관객수 기준 내림차순으로 정렬한 뒤 위에서 5개만 자릅니다.
top5 = df.sort_values("관객수", ascending=False).head(5)

# st.bar_chart는 '표의 index'를 가로축 이름으로 사용합니다.
# 그래서 영화명을 index로 바꿔 준 다음 관객수 열만 넘깁니다.
chart_data = top5.set_index("영화명")[["관객수"]]

st.bar_chart(chart_data)

st.caption("가로축: 영화명 / 세로축: 어제 하루 관객수(명)")
