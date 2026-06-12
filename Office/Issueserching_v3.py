import os
import ssl
import sys
import json
import time
import re
import argparse
import urllib3
from datetime import datetime, timedelta
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ==========================================================
# 1. 환경 설정
# ==========================================================
ssl._create_default_https_context = ssl._create_unverified_context
os.environ['WDM_SSL_VERIFY'] = '0'

CREDENTIAL_PATH = r"C:\Users\GSR\Desktop\Code\ilpus@gsretail.com.txt"
REPORT_DIR = r"C:\Users\GSR\Desktop\Code\git_folder\Office\daily_reports"
# [신규] 처리 이력(마지막 ID 등)을 저장할 상태 파일
STATE_PATH = os.path.join(REPORT_DIR, "issue_crawler_state.json")

# ----------------------------------------------------------
# [신규] 구글시트 백업 설정
# ----------------------------------------------------------
ENABLE_GSHEET = True  # 구글시트 백업 사용 여부
GSHEET_CRED_PATH = r"C:\Users\GSR\Desktop\Code\service_account.json"  # 서비스계정 키
# 현재(2026년) 운영이슈 시트의 ID. 연도 전환 시 자동으로 새 파일을 찾거나 생성.
GSHEET_2026_ID = "1Gd2Pi8WSrhR6_94KhoxdfexwuLB1VdM89-DVBVgLKOY"
# 새 연도 파일 생성 시 공유할 계정(편집 권한)
GSHEET_SHARE_EMAIL = "ilpus0270@gmail.com"
# 운영이슈 파일명 규칙: {연도}_운영이슈
GSHEET_NAME_FMT = "{year}_운영이슈"

BASE_URL = "https://coni.gsretail.com/program/dashboard/shoplive/{}"

# [중요] Teams 전송 기능 스위치.
ENABLE_TEAMS = True

# Teams 채팅방 검색어 (검색창에 입력 후 결과 최상단 방 선택)
TEAMS_TARGET_NAME = "팀장님+스디"

# ----------------------------------------------------------
# [신규] 공휴일 처리 설정
#   - 공휴일/주말에는 Teams 전송을 보류(미전송분은 상태파일에 누적).
#   - 다음 근무일에 누적분 + 당일분을 함께 전송.
#   - 공휴일 목록은 로컬 JSON(holidays.json)에서 읽는다(네트워크 의존 X).
#     형식: {"2026": ["2026-01-01", "2026-03-01", ...], "2027": [...]}
#   - 토/일은 코드에서 자동으로 휴일 처리(주말 근무 시 SKIP_WEEKEND=False).
# ----------------------------------------------------------
HOLIDAYS_PATH = os.path.join(REPORT_DIR, "holidays.json")
SKIP_WEEKEND = True  # 주말(토,일)도 휴일로 간주하여 전송 보류


# ==========================================================
# 2. 상태 파일(JSON) 관리
#   - last_id : 마지막으로 '처리 완료'한 ID. 다음 실행은 last_id+1부터 스캔.
# ==========================================================
def load_state():
    if os.path.exists(STATE_PATH):
        try:
            with open(STATE_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"⚠️ 상태 파일 읽기 실패({e}). 새로 시작합니다.")
    return {}


def save_state(state):
    os.makedirs(REPORT_DIR, exist_ok=True)
    with open(STATE_PATH, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)
    print(f"💾 상태 저장 완료: {STATE_PATH}")


# ==========================================================
# 2-B. 공휴일 판정
#   is_holiday(date) → 주말 또는 holidays.json에 등록된 날이면 True
# ==========================================================
def _load_holiday_set():
    """holidays.json에서 'YYYY-MM-DD' 문자열 집합을 로드. 없으면 빈 집합."""
    if os.path.exists(HOLIDAYS_PATH):
        try:
            with open(HOLIDAYS_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
            s = set()
            # {"2026":[...]} 또는 ["YYYY-MM-DD", ...] 양식 모두 허용
            if isinstance(data, dict):
                for _y, lst in data.items():
                    for d in lst:
                        s.add(str(d).strip())
            elif isinstance(data, list):
                for d in data:
                    s.add(str(d).strip())
            return s
        except Exception as e:
            print(f"⚠️ 공휴일 파일 읽기 실패({e}). 공휴일 목록 없이 진행.")
    else:
        print(f"ℹ️ 공휴일 파일이 없습니다: {HOLIDAYS_PATH} (주말만 휴일로 간주)")
    return set()


def is_holiday(d):
    """d(datetime/date)가 휴일인지 판정. 주말(옵션) 또는 등록 공휴일이면 True."""
    if SKIP_WEEKEND and d.weekday() >= 5:  # 5=토, 6=일
        return True
    key = d.strftime("%Y-%m-%d")
    return key in _load_holiday_set()


def holiday_name(d):
    """간단한 휴일 사유 문자열(로그/기록용)."""
    if SKIP_WEEKEND and d.weekday() >= 5:
        return "주말"
    return "공휴일"


# ==========================================================
# 3. 기본 유틸
# ==========================================================
def read_credentials():
    if not os.path.exists(CREDENTIAL_PATH):
        raise FileNotFoundError(f"⚠️ 계정 파일 누락: {CREDENTIAL_PATH}")
    with open(CREDENTIAL_PATH, "r", encoding="utf-8") as f:
        lines = f.read().splitlines()
        return lines[0].strip(), lines[1].strip()


def get_report_date_str(base_now=None):
    """리포트 파일명/표기에 쓸 '전일' 날짜 문자열."""
    if base_now is None:
        base_now = datetime.now()
    yesterday = base_now - timedelta(days=1)
    display = f"{yesterday.strftime('%y')}. {yesterday.month}. {yesterday.day}."
    file_tag = f"{yesterday.strftime('%y')}_{yesterday.month}_{yesterday.day}"
    return display, file_tag


def parse_program_date(date_str):
    match = re.search(r'(\d+)\.\s*(\d+)\.\s*(\d+)\.[^\d]*(\d+):(\d+)', date_str)
    if match:
        y = int(match.group(1)) + 2000
        return datetime(y, int(match.group(2)), int(match.group(3)),
                        int(match.group(4)), int(match.group(5)))
    return None


def split_date_time(raw_date, iso_dt=None):
    """'26. 6. 11.(목) 6:15~7:15' → ('26. 6. 11.', '6:15~7:15')"""
    date_part, time_part = "", ""
    if raw_date:
        m = re.search(r'(\d{1,2}:\d{2}\s*~\s*\d{1,2}:\d{2})', raw_date)
        if m:
            time_part = m.group(1).replace(" ", "")
        dm = re.search(r'(\d+\.\s*\d+\.\s*\d+\.)', raw_date)
        if dm:
            date_part = dm.group(1).strip()
    if not date_part and iso_dt:
        try:
            dt = datetime.fromisoformat(iso_dt)
            date_part = f"{dt.strftime('%y')}. {dt.month}. {dt.day}."
        except Exception:
            pass
    return date_part, time_part


# ==========================================================
# 4. HTML 리포트 생성
# ==========================================================
def generate_html_report(data_list, file_tag, display_date_str):
    os.makedirs(REPORT_DIR, exist_ok=True)
    html_file_path = os.path.join(REPORT_DIR, f"운영이슈_리포트_{file_tag}.html")

    html_content = f"""<!DOCTYPE html>
<html lang="ko">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{display_date_str} 운영이슈 리포트</title>
    <link rel="stylesheet" as="style" crossorigin href="https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.8/dist/web/static/pretendard.css" />
    <style>
        :root {{ --primary-color: #007AFF; --bg-color: #F4F6F9; --card-bg: #FFFFFF; --text-main: #333333; --text-sub: #666666; --border-color: #E5E5EA; }}
        body {{ font-family: 'Pretendard', sans-serif; background-color: var(--bg-color); color: var(--text-main); margin: 0; padding: 40px 20px; line-height: 1.6; }}
        .container {{ max-width: 900px; margin: 0 auto; background: var(--card-bg); border-radius: 16px; padding: 40px; box-shadow: 0 10px 30px rgba(0,0,0,0.05); }}
        .header {{ text-align: center; border-bottom: 2px solid var(--primary-color); padding-bottom: 20px; margin-bottom: 40px; }}
        .header h1 {{ font-size: 28px; font-weight: 700; margin: 0 0 10px 0; }}
        .header p {{ color: var(--text-sub); margin: 0; font-size: 16px; }}
        .card {{ border: 1px solid var(--border-color); border-radius: 12px; padding: 24px; margin-bottom: 24px; background-color: #FAFAFC; }}
        .card-top {{ display: flex; justify-content: space-between; align-items: center; border-bottom: 1px dashed var(--border-color); padding-bottom: 16px; margin-bottom: 16px; }}
        .program-title {{ font-size: 20px; font-weight: 700; color: var(--primary-color); margin: 0; }}
        .program-meta {{ display:flex; gap:8px; align-items:center; }}
        .program-id {{ font-size: 12px; color:#999; }}
        .program-date {{ font-size: 14px; color: var(--text-sub); background: #EBF5FF; padding: 6px 12px; border-radius: 20px; }}
        .issue-content {{ font-size: 15px; color: var(--text-main); white-space: pre-wrap; }}
        .issue-empty {{ color:#aaa; font-style: italic; }}
        .no-data {{ text-align: center; padding: 50px 0; color: #999; font-size: 18px; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>일일 운영이슈 집계 리포트</h1>
            <p>기준일자 : <strong>{display_date_str}</strong></p>
        </div>
"""
    if not data_list:
        html_content += '<div class="no-data"><p>해당 구간에 등록된 프로그램 및 운영이슈가 없습니다.</p></div>'
    else:
        for item in data_list:
            issue = item['issue']
            issue_cls = "issue-content"
            if not issue or issue.strip() in ("", "등록된 운영 이슈를 찾지 못했습니다."):
                issue = "운영이슈 없음"
                issue_cls = "issue-content issue-empty"
            html_content += f"""
        <div class="card">
            <div class="card-top">
                <h2 class="program-title">{item['name']}</h2>
                <div class="program-meta">
                    <span class="program-id">ID {item['id']}</span>
                    <span class="program-date">{item['date']}</span>
                </div>
            </div>
            <div class="{issue_cls}">{issue}</div>
        </div>"""

    html_content += "</div></body></html>"

    with open(html_file_path, "w", encoding="utf-8") as f:
        f.write(html_content)

    print(f"\n📄 HTML 리포트 생성 완료: {html_file_path} (수집 {len(data_list)}건)")
    return html_file_path


# ==========================================================
# 5. 크롤링 (ID 구간 기반)
#   - 날짜 텍스트는 '믿지 않고' 기록용으로만 추출.
#   - 실제 수집 범위는 start_id ~ end_id 사이의 모든 ID.
# ==========================================================
def fetch_one_page(driver, wait, cid, quiet=False):
    """단일 게시물 페이지를 읽어 dict 반환. 빈/없는 페이지면 None."""
    driver.get(BASE_URL.format(cid))
    try:
        date_xpath = "//span[contains(@class, 'text-3lg') and not(contains(@class, 'border-l'))]"
        program_date = wait.until(
            EC.presence_of_element_located((By.XPATH, date_xpath))
        ).text.strip()
    except Exception:
        return None

    try:
        name_xpath = "//span[contains(@class, 'text-3lg') and contains(@class, 'border-l')]"
        program_name = driver.find_element(By.XPATH, name_xpath).text.strip()
    except Exception:
        program_name = "(프로그램명 미확인)"

    try:
        issue_xpath = "//div[contains(@class, 'text-md/7') and .//span[contains(@class, 'text-brand-secondary')]]"
        issue_text = driver.find_element(By.XPATH, issue_xpath).text.strip()
    except Exception:
        issue_text = ""

    prog_dt = parse_program_date(program_date)
    return {
        "id": cid,
        "date": program_date,
        "datetime": prog_dt.isoformat() if prog_dt else None,
        "name": program_name,
        "issue": issue_text,
    }


def probe_exists(driver, cid, probe_timeout=1.5):
    """[빠른 탐색 전용] 해당 ID에 게시물이 존재하는지만 빠르게 확인.
    긴 WebDriverWait(15초) 대신 짧은 타임아웃으로 날짜요소 유무만 본다.
    빈 ID에서 15초씩 낭비하던 문제를 해결하는 핵심 함수."""
    driver.get(BASE_URL.format(cid))
    short = WebDriverWait(driver, probe_timeout)
    try:
        date_xpath = "//span[contains(@class, 'text-3lg') and not(contains(@class, 'border-l'))]"
        short.until(EC.presence_of_element_located((By.XPATH, date_xpath)))
        return True
    except Exception:
        return False


def crawl_id_range(driver, wait, start_id, end_id, probe_timeout=1.5):
    """start_id ~ end_id (양끝 포함) 사이의 모든 페이지를 방문하여 수집.
    빈 페이지는 probe로 빠르게 건너뛴다."""
    results = []
    lo, hi = min(start_id, end_id), max(start_id, end_id)
    print(f"\n================= ID 구간 스캔: {lo} ~ {hi} ({hi - lo + 1}건) =================")

    for cid in range(lo, hi + 1):
        if probe_exists(driver, cid, probe_timeout):
            page = fetch_one_page(driver, wait, cid)
        else:
            page = None
        if page is None:
            print(f"  [ID {cid}] 빈/없는 페이지 → 스킵")
            continue
        results.append(page)
        flag = "📝이슈" if page["issue"] else "·"
        print(f"  [ID {cid}] {page['date']} | {page['name']} {flag}")

    return results


# ==========================================================
# 5-B. 적응형 갭 점프 탐색
#   ID가 불연속(큰 점프)일 때 효율적으로 '다음 유효 게시물'을 찾는다.
#   전략:
#     1) from_id 부터 1씩 소량(fine_limit) probe → 인접 게시물 즉시 포착
#     2) 못 찾으면 고정 보폭(14)으로 빠른 도약 (probe로 빈 페이지 대기 최소화)
#     3) 유효 ID를 찍으면 역방향으로 '블록(같은 날) 시작'을 정밀 추적
# ==========================================================
def find_next_valid_id(driver, wait, from_id, fine_limit=30,
                       coarse_step=14, coarse_max_span=30000,
                       probe_timeout=1.5, back_limit=None):
    """from_id 이상에서 '가장 가까운 유효 게시물'의 페이지(dict)를 찾아 반환. 없으면 None.

    속도 개선 핵심:
      - 빈 ID 확인을 probe_exists(짧은 타임아웃)로 처리 → 빈 페이지당 15초→1.5초.
      - 정밀(1씩)은 소량(기본 30)만, 그 뒤는 고정 보폭(14)으로 빠르게 도약.
      - 보폭 14는 하루 방송 블록 최소폭(약 15)보다 작아 블록을 통째로 건너뛰지 않음.
      - 유효 ID를 한 번 찍으면 '블록의 시작'을 역방향으로 정밀 탐색.

    back_limit: 역추적이 이 ID 미만으로는 내려가지 않도록 하는 하한.
      (일일 운영처럼 from_id가 '직전 날과 연속'일 때, 이미 처리한 영역을
       다시 블록 시작으로 오인하지 않도록 from_id를 넘겨준다.)
    """
    print(f"\n🔎 다음 유효 게시물 탐색 (from {from_id}, probe={probe_timeout}s)")

    # 1) 정밀(1씩) 소량 탐색 - 인접 게시물 즉시 포착
    cid = from_id
    checked = 0
    hit_id = None
    while checked < fine_limit:
        if probe_exists(driver, cid, probe_timeout):
            hit_id = cid
            break
        cid += 1
        checked += 1

    # 2) 못 찾았으면 고정 보폭(14)으로 빠른 도약
    if hit_id is None:
        print(f"   …정밀 {fine_limit}개 없음 → 보폭 {coarse_step} 빠른 도약")
        span = 0
        pos = cid
        while span < coarse_max_span:
            if probe_exists(driver, pos, probe_timeout):
                hit_id = pos
                break
            pos += coarse_step
            span += coarse_step
            if span % (coarse_step * 30) == 0:
                print(f"   …도약 중 (현재 {pos}, 누적 {span})")
        if hit_id is None:
            print(f"   ❌ {coarse_max_span} 범위 내 유효 게시물 없음")
            return None

    print(f"   ✔ 유효 ID 포착: {hit_id} → 블록 시작 역추적")

    # 3) 역방향으로 '블록(같은 날) 시작' 찾기
    #    hit_id에서 1씩 내려가며 빈 ID를 만나기 직전까지가 블록 시작.
    #    back_limit이 지정되면 그 미만으로는 내려가지 않는다(이미 처리한 영역 보호).
    back_margin = 30
    floor_candidate = min(from_id, hit_id) - back_margin
    if back_limit is not None:
        floor_candidate = max(floor_candidate, back_limit)
    back_floor = max(1, floor_candidate)
    block_start = hit_id
    back = hit_id - 1
    while back >= back_floor:
        if probe_exists(driver, back, probe_timeout):
            block_start = back
            back -= 1
        else:
            break

    page = fetch_one_page(driver, wait, block_start)
    if page is not None:
        print(f"   ✔ 블록 시작 확정: ID {block_start} ({page['date']})")
        return page
    return fetch_one_page(driver, wait, hit_id)


def collect_target_date(driver, wait, first_page, target_date_key,
                        probe_timeout=1.5):
    """first_page(유효 게시물)부터 시작해 '목표 날짜(target_date_key)'에
    해당하는 게시물만 1씩 전진하며 수집. 목표 날짜를 지나면 종료.
    target_date_key: 'YY. M. D.' 형태 문자열 (예: '26. 6. 8.')

    속도 개선: 각 ID를 probe_exists로 먼저 빠르게 확인하고,
    존재할 때만 full fetch → 빈 페이지 대기 최소화."""
    results = []
    cid = first_page["id"]
    started = False
    miss_after_start = 0

    while True:
        if cid == first_page["id"]:
            page = first_page
        elif probe_exists(driver, cid, probe_timeout):
            page = fetch_one_page(driver, wait, cid)
        else:
            page = None

        if page is None:
            # 수집 시작 후 빈 페이지가 연속되면 종료(다음 점프 구간일 수 있음)
            if started:
                miss_after_start += 1
                if miss_after_start >= 10:
                    print(f"  🛑 목표일 수집 후 빈 페이지 연속 → 종료 (ID {cid})")
                    break
            cid += 1
            continue
        miss_after_start = 0

        dpart, _ = split_date_time(page["date"], page.get("datetime"))
        if dpart == target_date_key:
            started = True
            results.append(page)
            flag = "📝이슈" if page["issue"] else "·"
            print(f"  [ID {cid}] {page['date']} | {page['name']} {flag}")
        elif started:
            # 목표 날짜 수집 중 다른 날짜(=다음 날)로 넘어가면 종료
            print(f"  🛑 목표일({target_date_key}) 종료. 다음 날짜 {dpart} 도달 (ID {cid})")
            break
        else:
            # 아직 목표 날짜 전(과거)일 수 있음 → 계속 전진
            print(f"  [ID {cid}] {page['date']} (목표일 {target_date_key} 아직 아님 → 전진)")
        cid += 1

    return results


def discover_latest_id(driver):
    """대시보드 목록에서 현재 가장 큰 게시물 ID를 추정."""
    page_source = driver.page_source
    numbers = re.findall(r'/program/dashboard/shoplive/(\d{6})', page_source)
    if numbers:
        return max(int(n) for n in numbers)
    return None


def login_dashboard(user_id, user_pw):
    options = webdriver.ChromeOptions()
    options.add_argument("--headless=new")  # 👈 이 줄을 추가합니다.
    options.add_argument("--start-maximized")
    options.add_argument("--disable-gpu")
    options.add_argument('--ignore-certificate-errors')

    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=options)
    wait = WebDriverWait(driver, 15)

    print("🌐 대시보드 로그인 진행 중...")
    driver.get("https://coni.gsretail.com/program/dashboard/shoplive")

    try:
        id_field = WebDriverWait(driver, 5).until(
            EC.presence_of_element_located((By.XPATH, "//input[@type='email' or @id='userNameInput']")))
        id_field.send_keys(user_id + Keys.ENTER)
        time.sleep(2)
    except Exception:
        pass

    pw_field = wait.until(EC.presence_of_element_located((By.XPATH, "//input[@type='password']")))
    pw_field.send_keys(user_pw + Keys.ENTER)

    print("⏳ 대시보드 로딩 대기 중...")
    time.sleep(7)
    return driver, wait


# ==========================================================
# 6. 수집 대상 결정 & 적응형 수집
#   (A) 수동 구간 지정 : --start / --end  → 해당 구간 전체 수집
#   (B) 자동 모드      : 상태파일 last_id 다음부터 적응형 탐색으로
#                        '목표 날짜(전회 저장 다음 날)' 1일치만 수집
# ==========================================================
def determine_target_date(state):
    """수집할 목표 날짜 키('YY. M. D.')를 결정.
    - 상태파일에 last_date가 있으면 그 '다음 날'.
    - 없으면 시스템 기준 '어제'."""
    last_date_iso = state.get("last_date")
    if last_date_iso:
        try:
            d = datetime.fromisoformat(last_date_iso) + timedelta(days=1)
            return f"{d.strftime('%y')}. {d.month}. {d.day}.", d
        except Exception:
            pass
    y = datetime.now() - timedelta(days=1)
    return f"{y.strftime('%y')}. {y.month}. {y.day}.", y


def collect_results(driver, wait, args, state):
    """수집 실행. results 반환."""
    probe_timeout = getattr(args, "probe", 1.5)

    # (A) 수동 구간 지정 → 해당 구간 전체 수집(기존 방식)
    if args.start is not None and args.end is not None:
        print(f"▶ 수동 구간 모드: {args.start} ~ {args.end}")
        return crawl_id_range(driver, wait, args.start, args.end)

    # (B) 자동 모드: 목표 날짜 1일치 수집
    target_key, target_dt = determine_target_date(state)
    print(f"▶ 자동 모드: 목표 날짜 '{target_key}' 1일치를 수집합니다.")

    last_done = state.get("last_id")
    if last_done is None:
        # 첫 실행: 최신 ID 부근에서 시작점 추정
        latest = discover_latest_id(driver)
        if latest is None:
            print("⚠️ 최신 ID를 찾지 못했습니다. --start/--end 로 수동 지정해 주세요.")
            return []
        from_id = max(latest - 60, 1)
        print(f"ℹ️ 상태파일 없음(첫 실행). 최신 {latest} 부근 {from_id}부터 탐색.")
    else:
        from_id = last_done + 1
        print(f"ℹ️ 전회 저장 ID {last_done} → {from_id}부터 탐색 시작.")

    # 적응형 탐색으로 from_id 이상에서 첫 유효 게시물 찾기 (빠른 probe)
    # back_limit=from_id: 이미 처리한 직전 날(연속 ID)을 침범하지 않도록 보호
    first = find_next_valid_id(driver, wait, from_id,
                               probe_timeout=probe_timeout, back_limit=from_id)
    if first is None:
        print("❌ 다음 유효 게시물을 찾지 못했습니다.")
        return []

    # 찾은 게시물이 목표 날짜보다 과거면, 목표 날짜가 나올 때까지 전진하며 수집
    results = collect_target_date(driver, wait, first, target_key,
                                  probe_timeout=probe_timeout)

    if not results:
        fpart, _ = split_date_time(first["date"], first.get("datetime"))
        print(f"ℹ️ 목표 날짜 '{target_key}' 게시물을 찾지 못했습니다. (첫 발견일: {fpart})")
    return results


# ==========================================================
# 6-B. 구글시트 백업
#   - A열: 일자(YY.M.D) / B열: 시간대 / C열: 프로그램명 / D열: 운영이슈(멀티라인)
#   - 월별 시트(예: '6월')에 프로그램 1건당 1행으로 누적.
#   - 연도가 바뀌면 '{연도}_운영이슈' 파일을 첨부 양식대로 새로 생성.
#   - 중복 방지: (일자+시간대+프로그램명) 키가 이미 있으면 건너뜀.
# ==========================================================
def _gs_open_or_create_spreadsheet(gc, year):
    """해당 연도의 '{year}_운영이슈' 스프레드시트를 연다. 없으면 생성."""
    # 2026년은 알려진 ID를 우선 사용(빠르고 확실)
    if year == 2026 and GSHEET_2026_ID:
        try:
            return gc.open_by_key(GSHEET_2026_ID)
        except Exception as e:
            print(f"ℹ️ 2026 ID 열기 실패({e}). 파일명으로 재시도합니다.")

    target_name = GSHEET_NAME_FMT.format(year=year)
    # 파일명으로 열기 시도
    try:
        return gc.open(target_name)
    except Exception:
        pass

    # 없으면 첨부 양식대로 신규 생성 (1~12월 시트, 기본시트 삭제, 공유)
    print(f"🆕 '{target_name}' 스프레드시트를 새로 생성합니다...")
    sh = gc.create(target_name)
    try:
        sh.share(GSHEET_SHARE_EMAIL, perm_type='user', role='writer')
    except Exception as e:
        print(f"⚠️ 공유 설정 실패(무시 가능): {e}")
    for m in range(1, 13):
        sh.add_worksheet(title=f'{m}월', rows=600, cols=12)
    # 자동 생성된 기본 시트(Sheet1) 제거
    try:
        sh.del_worksheet(sh.get_worksheet(0))
    except Exception:
        pass
    print(f"✅ '{target_name}' 생성 완료.")
    return sh


def _gs_get_month_worksheet(sh, month):
    """'{month}월' 워크시트를 반환. 없으면 생성."""
    title = f"{month}월"
    try:
        return sh.worksheet(title)
    except Exception:
        return sh.add_worksheet(title=title, rows=600, cols=12)


def backup_to_gsheet(results):
    """크롤링 결과를 구글시트에 백업.
    results: [{id,date,datetime,name,issue}, ...] (date 예: '26. 6. 11.(목) 6:15~7:15')"""
    if not results:
        print("ℹ️ 백업할 데이터가 없어 구글시트 저장을 건너뜁니다.")
        return

    try:
        import gspread
    except ImportError:
        print("❌ gspread 미설치: pip install gspread google-auth")
        return

    if not os.path.exists(GSHEET_CRED_PATH):
        print(f"❌ 서비스계정 키 누락: {GSHEET_CRED_PATH}")
        return

    print("\n================= 구글시트 백업 시작 =================")
    try:
        gc = gspread.service_account(GSHEET_CRED_PATH)
    except Exception as e:
        print(f"❌ 구글 인증 실패: {e}")
        return

    # 결과의 첫 항목 datetime으로 연/월 결정 (없으면 date 텍스트 파싱)
    base_dt = None
    for r in results:
        if r.get("datetime"):
            try:
                base_dt = datetime.fromisoformat(r["datetime"])
                break
            except Exception:
                pass
    if base_dt is None:
        base_dt = parse_program_date(results[0].get("date", "")) or datetime.now()

    year, month = base_dt.year, base_dt.month

    try:
        sh = _gs_open_or_create_spreadsheet(gc, year)
        ws = _gs_get_month_worksheet(sh, month)
    except Exception as e:
        print(f"❌ 스프레드시트/시트 열기 실패: {e}")
        return

    # 헤더 보장 (A1:D1)
    headers = ["일자", "시간대", "프로그램명", "운영이슈"]
    all_values = ws.get_all_values()
    if not all_values or not all_values[0] or all_values[0][:4] != headers:
        ws.update(values=[headers], range_name='A1:D1')
        if not all_values:
            all_values = [headers]
        else:
            all_values[0] = headers

    # 기존 키(중복 방지): (일자, 시간대, 프로그램명)
    existing_keys = set()
    for row in all_values[1:]:
        if len(row) >= 3:
            existing_keys.add((row[0].strip(), row[1].strip(), row[2].strip()))

    # 결과를 A~D 행으로 변환
    new_rows = []
    for r in results:
        raw_date = r.get("date", "")
        # 'YY. M. D.(요일) HH:MM~HH:MM' → 일자/시간대 분리
        date_part, time_part = _split_date_time(raw_date, r.get("datetime"))
        name = (r.get("name") or "").strip()
        issue = (r.get("issue") or "").strip()
        if not issue:
            issue = "운영이슈 없음"

        key = (date_part, time_part, name)
        if key in existing_keys:
            continue  # 이미 저장된 프로그램은 건너뜀
        existing_keys.add(key)
        new_rows.append([date_part, time_part, name, issue])

    if not new_rows:
        print("ℹ️ 추가할 신규 행이 없습니다(모두 기존에 저장됨).")
    else:
        start_row = len(all_values) + 1
        end_row = start_row + len(new_rows) - 1
        ws.update(values=new_rows, range_name=f'A{start_row}:D{end_row}')
        print(f"✅ {month}월 시트에 {len(new_rows)}건 추가 (행 {start_row}~{end_row})")

    # D열(운영이슈) 자동 줄바꿈 + 넓은 열폭 서식 적용
    _gs_format_issue_column(sh, ws)
    print(f"📊 백업 완료: {GSHEET_NAME_FMT.format(year=year)} / {month}월")


def _split_date_time(raw_date, iso_dt=None):
    return split_date_time(raw_date, iso_dt)


def _gs_format_issue_column(sh, ws):
    """D열: 자동 줄바꿈(WRAP) + 넓은 열폭, 상단정렬 적용."""
    try:
        sheet_id = ws._properties['sheetId']
        requests = [
            # D열(인덱스 3) 폭 600px
            {
                "updateDimensionProperties": {
                    "range": {"sheetId": sheet_id, "dimension": "COLUMNS",
                              "startIndex": 3, "endIndex": 4},
                    "properties": {"pixelSize": 600},
                    "fields": "pixelSize",
                }
            },
            # A~C열 적당히
            {
                "updateDimensionProperties": {
                    "range": {"sheetId": sheet_id, "dimension": "COLUMNS",
                              "startIndex": 0, "endIndex": 3},
                    "properties": {"pixelSize": 110},
                    "fields": "pixelSize",
                }
            },
            # D열 전체 자동 줄바꿈 + 상단 정렬
            {
                "repeatCell": {
                    "range": {"sheetId": sheet_id, "startColumnIndex": 3, "endColumnIndex": 4},
                    "cell": {"userEnteredFormat": {"wrapStrategy": "WRAP",
                                                   "verticalAlignment": "TOP"}},
                    "fields": "userEnteredFormat(wrapStrategy,verticalAlignment)",
                }
            },
            # 1행 헤더 굵게 + 가운데
            {
                "repeatCell": {
                    "range": {"sheetId": sheet_id, "startRowIndex": 0, "endRowIndex": 1},
                    "cell": {"userEnteredFormat": {"textFormat": {"bold": True},
                                                   "horizontalAlignment": "CENTER"}},
                    "fields": "userEnteredFormat(textFormat,horizontalAlignment)",
                }
            },
        ]
        sh.batch_update({"requests": requests})
    except Exception as e:
        print(f"⚠️ 서식 적용 실패(데이터 저장은 정상): {e}")


# ==========================================================
# 7. Teams 전송
#   흐름: 웹 접속 → 로그인 → 검색창에 방이름 입력 → 결과 최상단 방 클릭
#         → 파일첨부 아이콘 클릭 → '이 디바이스에서 업로드' → input[file]에 경로 주입
#         → 채팅창에 안내 메시지 입력 후 전송
# ==========================================================
def send_teams_message(user_id, user_pw, file_paths, message_text):
    """Teams 채팅방에 여러 HTML 파일을 첨부하고 안내 메시지를 전송.
    file_paths: 첨부할 파일 경로 리스트 (1개 이상)
    message_text: 보낼 안내 메시지 문구
    반환: 성공 True / 실패 False"""
    print("\n================= Teams 전송 프로세스 시작 =================")

    # 리스트 정규화 + 존재하는 파일만 추림
    if isinstance(file_paths, str):
        file_paths = [file_paths]
    valid_files = [p for p in file_paths if p and os.path.exists(p)]
    if not valid_files:
        print(f"❌ 첨부할 유효한 파일이 없습니다: {file_paths}")
        return False
    print(f"📎 첨부 대상 {len(valid_files)}개: {[os.path.basename(p) for p in valid_files]}")

    options = webdriver.ChromeOptions()
    options.add_argument("--headless=new")  # 👈 이 줄을 추가합니다.
    options.add_argument("--start-maximized")
    options.add_argument("--disable-gpu")
    options.add_argument('--ignore-certificate-errors')

    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=options)
    wait = WebDriverWait(driver, 20)

    try:
        print("🌐 Microsoft Teams 웹버전에 접속합니다...")
        driver.get("https://teams.microsoft.com/v2/")

        # --- 로그인 ---
        print("🔑 로그인 진행 중...")
        try:
            id_field = wait.until(EC.presence_of_element_located((By.XPATH, "//input[@type='email']")))
            id_field.clear()
            id_field.send_keys(user_id)
            id_field.send_keys(Keys.ENTER)
            time.sleep(3)
        except Exception:
            pass

        try:
            pw_field = wait.until(EC.presence_of_element_located((By.XPATH, "//input[@type='password']")))
            pw_field.clear()
            pw_field.send_keys(user_pw)
            pw_field.send_keys(Keys.ENTER)
        except Exception:
            print("ℹ️ 비밀번호 입력 단계 생략(이미 로그인 상태일 수 있음).")

        # '로그인 상태 유지' 팝업
        try:
            stay = WebDriverWait(driver, 5).until(
                EC.element_to_be_clickable((By.XPATH, "//input[@id='idSIButton9' or @value='예']")))
            stay.click()
        except Exception:
            pass

        print("🚀 로그인 완료. Teams 인터페이스 로딩 대기 (안전하게 약 60초)...")
        # 인터페이스가 충분히 안정화되도록 1차 고정 대기(60초)
        time.sleep(60)

        # 그 후, 검색창이 실제로 '상호작용 가능'해질 때까지 추가 대기
        search_box = None
        for attempt in range(1, 13):  # 최대 약 60초 추가
            try:
                search_box = WebDriverWait(driver, 5).until(
                    EC.element_to_be_clickable((By.XPATH, '//*[@id="ms-searchux-input"]')))
                driver.execute_script("arguments[0].scrollIntoView({block:'center'});", search_box)
                time.sleep(0.5)
                break
            except Exception:
                print(f"   …검색창 활성화 대기 중 ({attempt}/12)")
                time.sleep(5)

        if search_box is None:
            print("❌ 검색창이 끝내 로드되지 않았습니다. 네트워크/로그인 상태를 확인하세요.")
            return

        # --- 채팅방 검색 ---
        print(f"🔍 채팅방 '{TEAMS_TARGET_NAME}' 을(를) 검색합니다...")
        # 일반 click()은 상단 타이틀바(pre-core-title-bar)에 가로채일 수 있어 JS 클릭 사용
        try:
            driver.execute_script("arguments[0].click();", search_box)
        except Exception:
            try:
                search_box.click()
            except Exception:
                pass
        time.sleep(1)

        # 기존 입력값 정리 후 검색어 입력
        try:
            search_box.send_keys(Keys.CONTROL, 'a')
            search_box.send_keys(Keys.DELETE)
        except Exception:
            pass
        search_box.send_keys(TEAMS_TARGET_NAME)
        time.sleep(3)

        # --- 검색 결과 최상단 방 클릭 ---
        # 동적 UI 대응: 여러 후보 XPath를 순차 시도
        clicked = False
        result_candidates = [
            f"//div[@role='option'][.//*[contains(text(),'{TEAMS_TARGET_NAME}')]][1]",
            f"//li[@role='option'][.//*[contains(text(),'{TEAMS_TARGET_NAME}')]][1]",
            "//div[@role='listbox']//div[@role='option'][1]",
            "//ul[@role='listbox']//li[1]",
            f"(//*[contains(text(), '{TEAMS_TARGET_NAME}')])[1]",
            "//div[contains(@class,'fui-')][@role='option'][1]",
        ]
        for xp in result_candidates:
            try:
                item = WebDriverWait(driver, 5).until(EC.element_to_be_clickable((By.XPATH, xp)))
                try:
                    item.click()
                except Exception:
                    driver.execute_script("arguments[0].click();", item)
                clicked = True
                print(f"▶ 검색 결과 최상단 방 클릭: {xp}")
                break
            except Exception:
                continue
        if not clicked:
            print("⚠️ 검색 결과 클릭 실패 → ENTER로 진입 시도")
            search_box.send_keys(Keys.ENTER)

        print("▶ 채팅방 로딩 대기...")
        time.sleep(6)

        # ----------------------------------------------------------
        # [중요] 방 진입 검증
        #   - 검색 결과를 클릭하지 못한 채로 진행하면, 직전에 열려있던
        #     '다른 채팅방'에 파일이 업로드되는 사고가 난다.
        #   - 헤더에 대상 방 이름이 보이는지로 진입 여부를 확인한다.
        # ----------------------------------------------------------
        entered = False
        verify_xpaths = [
            f"//*[@id='chat-pane-list' or @data-tid='chat-pane-list']//*[contains(text(),'{TEAMS_TARGET_NAME}')]",
            f"//div[contains(@class,'ts-title') or @role='heading'][contains(.,'{TEAMS_TARGET_NAME}')]",
            f"//*[contains(text(),'{TEAMS_TARGET_NAME}')]",
        ]
        for xp in verify_xpaths:
            try:
                WebDriverWait(driver, 5).until(EC.presence_of_element_located((By.XPATH, xp)))
                entered = True
                break
            except Exception:
                continue

        if not entered:
            print(f"❌ 대상 채팅방('{TEAMS_TARGET_NAME}') 진입을 확인하지 못했습니다.")
            print("   엉뚱한 방에 업로드되는 사고 방지를 위해 첨부/전송을 중단합니다.")
            return False
        print(f"✅ 대상 채팅방 진입 확인: '{TEAMS_TARGET_NAME}'")

        # --- 파일 첨부 (여러 개) ---
        print("📎 리포트 파일 첨부를 시작합니다...")
        # 방 진입 후 메시지 영역이 완전히 렌더링되도록 추가 대기 (느린 환경 대비)
        time.sleep(15)

        def _find_file_input():
            """현재 DOM에서 input[type=file] 탐색. 없으면 첨부 아이콘→메뉴 경유로 노출."""
            # 1차: 이미 노출된 숨은 input
            try:
                return driver.find_element(By.XPATH, "//input[@type='file']")
            except Exception:
                pass
            # 2차: 첨부 아이콘 클릭 → '이 디바이스에서 업로드'
            attach_btn_candidates = [
                '//*[@id="message-pane-layout-a11y"]/div[4]/div/div/div[4]/div/div[3]/div[2]/button[2]',
                '//button[contains(@aria-label,"첨부") or contains(@aria-label,"Attach")]',
                '//button[contains(@aria-label,"파일") or contains(@aria-label,"File")]',
            ]
            attach_btn = None
            for _try in range(5):
                for xp in attach_btn_candidates:
                    try:
                        attach_btn = WebDriverWait(driver, 6).until(
                            EC.element_to_be_clickable((By.XPATH, xp)))
                        break
                    except Exception:
                        continue
                if attach_btn is not None:
                    break
                print(f"   …첨부 아이콘 대기 재시도 ({_try+1}/5)")
                time.sleep(5)
            if attach_btn is None:
                raise RuntimeError("첨부 아이콘을 찾지 못함")

            driver.execute_script("arguments[0].scrollIntoView({block:'center'});", attach_btn)
            time.sleep(1)
            try:
                attach_btn.click()
            except Exception:
                driver.execute_script("arguments[0].click();", attach_btn)
            print("   첨부 메뉴 여는 중...")
            time.sleep(6)

            upload_menu_candidates = [
                "/html/body/div[12]/div/div[2]/div/div[1]/div/ul/li[9]/a/span[2]/span",
                "//*[contains(text(),'이 디바이스') or contains(text(),'Upload from this device')]",
                "//ul//a[contains(.,'업로드') or contains(.,'Upload')]",
            ]
            for xp in upload_menu_candidates:
                try:
                    menu = WebDriverWait(driver, 6).until(
                        EC.element_to_be_clickable((By.XPATH, xp)))
                    try:
                        menu.click()
                    except Exception:
                        driver.execute_script("arguments[0].click();", menu)
                    print("   '이 디바이스에서 업로드' 선택됨.")
                    time.sleep(4)
                    break
                except Exception:
                    continue

            return WebDriverWait(driver, 15).until(
                EC.presence_of_element_located((By.XPATH, "//input[@type='file']")))

        uploaded_count = 0
        for idx, fpath in enumerate(valid_files, 1):
            try:
                print(f"  [{idx}/{len(valid_files)}] 첨부: {os.path.basename(fpath)}")
                file_input = _find_file_input()
                file_input.send_keys(fpath)
                print(f"  ⏳ 업로드 중 (약 12초)...")
                time.sleep(12)
                uploaded_count += 1
            except Exception as e:
                print(f"  ⚠️ '{os.path.basename(fpath)}' 첨부 실패: {e}")

        upload_ok = uploaded_count > 0
        if upload_ok:
            print(f"✅ {uploaded_count}/{len(valid_files)}개 첨부 완료. 반영 대기 (약 12초)...")
            time.sleep(12)
        else:
            print("⚠️ 첨부된 파일이 없습니다. 메시지만 전송을 시도합니다.")

        # --- 안내 메시지 입력 ---
        print("✉️ 안내 메시지를 작성하고 발송합니다...")
        chat_box = None
        # new-message-<UUID> 의 UUID는 가변 → 접두사 패턴으로 매칭
        chat_box_candidates = [
            "//*[starts-with(@id,'new-message-')]//p",
            "//*[starts-with(@id,'new-message-')]",
            "//div[@contenteditable='true' and @role='textbox']",
            "//div[@data-testid='message-box-rich-text-editor']",
            "//div[@contenteditable='true']",
        ]
        for xp in chat_box_candidates:
            try:
                chat_box = WebDriverWait(driver, 5).until(EC.element_to_be_clickable((By.XPATH, xp)))
                break
            except Exception:
                continue

        sent_ok = False
        if chat_box is not None:
            try:
                chat_box.click()
                time.sleep(1)
                # 여러 줄 메시지: 줄바꿈은 Shift+Enter, 마지막에 Enter로 전송
                lines = message_text.split("\n")
                for li, line in enumerate(lines):
                    chat_box.send_keys(line)
                    if li < len(lines) - 1:
                        chat_box.send_keys(Keys.SHIFT, Keys.ENTER)
                time.sleep(2)
                chat_box.send_keys(Keys.ENTER)
                print("✅ Teams 메시지 발송 완료!")
                sent_ok = True
                time.sleep(8)
            except Exception as e:
                print(f"⚠️ 메시지 입력 중 오류: {e}")
        else:
            if upload_ok:
                print("ℹ️ 입력창을 못 찾았지만 파일은 첨부됨. 첨부 상태에서 Enter 시도.")
                try:
                    driver.switch_to.active_element.send_keys(Keys.ENTER)
                    sent_ok = True
                except Exception:
                    pass
            else:
                print("⚠️ 채팅 입력창을 끝내 찾지 못했습니다.")

        return sent_ok

    except Exception as e:
        print(f"\n❌ Teams 발송 중 오류가 발생했습니다: {e}")
        return False
    finally:
        time.sleep(2)
        driver.quit()
        print("Teams 프로세스를 종료합니다.")


# ==========================================================
# 8. Main
# ==========================================================
def main():
    parser = argparse.ArgumentParser(description="운영이슈 대시보드 크롤러 (ID 구간 기반)")
    parser.add_argument("--start", type=int, default=None, help="스캔 시작 ID")
    parser.add_argument("--end", type=int, default=None, help="스캔 끝 ID")
    parser.add_argument("--no-save", action="store_true", help="상태파일(last_id) 갱신 안 함")
    parser.add_argument("--probe", type=float, default=1.5,
                        help="빈 페이지 판정 타임아웃(초). 네트워크가 빠르면 1.0~1.2로 낮추면 더 빠름")
    args = parser.parse_args()

    print("🤖 전일 운영이슈 자동화 시스템(크롤링 모드)을 가동합니다.")
    user_id, user_pw = read_credentials()
    display_date_str, file_tag = get_report_date_str()
    state = load_state()

    driver, wait = login_dashboard(user_id, user_pw)
    results = []
    try:
        results = collect_results(driver, wait, args, state)

        # HTML 리포트: 수집된 날짜를 우선 사용(자동 모드에서 정확한 일자 반영)
        if results:
            dpart, _ = split_date_time(results[0]["date"], results[0].get("datetime"))
            if dpart:
                file_tag = dpart.replace(". ", "_").replace(".", "").strip("_")
                # 'YY. M. D.' → 'YY_M_D' 정규화
                m = re.search(r'(\d+)\.\s*(\d+)\.\s*(\d+)\.', dpart)
                if m:
                    file_tag = f"{m.group(1)}_{m.group(2)}_{m.group(3)}"
                    display_date_str = dpart
        generate_html_report(results, file_tag, display_date_str)

        # 상태 저장: 처리한 최대 ID + 수집한 날짜 기록
        if results and not args.no_save:
            max_id = max(r["id"] for r in results)
            state["last_id"] = max_id
            # 수집한 날짜(마지막 게시물 기준)를 저장 → 다음 실행의 '다음 날' 기준
            last_dt = None
            for r in results:
                if r.get("datetime"):
                    try:
                        cand = datetime.fromisoformat(r["datetime"])
                        if last_dt is None or cand > last_dt:
                            last_dt = cand
                    except Exception:
                        pass
            if last_dt is not None:
                # 날짜만(시각 제거) 저장 → 다음날 계산이 명확
                state["last_date"] = last_dt.replace(hour=0, minute=0, second=0,
                                                     microsecond=0).isoformat()
            state["last_run"] = datetime.now().isoformat()
            save_state(state)
    finally:
        driver.quit()

    # 구글시트 백업 (연도 전환 시 새 파일 자동 생성)
    if ENABLE_GSHEET:
        try:
            backup_to_gsheet(results)
        except Exception as e:
            print(f"⚠️ 구글시트 백업 중 오류(전체 흐름은 계속): {e}")
    else:
        print("\n⏸️ 구글시트 백업은 건너뜁니다 (ENABLE_GSHEET=False).")

    # ======================================================
    # Teams 전송 (공휴일 인식)
    #   - 오늘(실행일)이 휴일이면: 당일 HTML을 pending_reports에 누적, 전송 보류.
    #   - 근무일이면: pending_reports(과거 미전송분) + 당일분을 모아 한 번에 전송.
    #     전송 성공 시 pending_reports 비움.
    # ======================================================
    today = datetime.now()
    report_path = os.path.join(REPORT_DIR, f"운영이슈_리포트_{file_tag}.html")
    pending = state.get("pending_reports", [])

    if not ENABLE_TEAMS:
        print("\n⏸️ Teams 전송 단계는 건너뜁니다 (ENABLE_TEAMS=False).")
    elif not os.path.exists(report_path):
        print(f"❌ 전송할 {file_tag} 일자 파일을 찾지 못해 Teams 처리를 건너뜁니다.")
    elif is_holiday(today):
        # 휴일: 전송 보류 + 누적 기록
        reason = holiday_name(today)
        entry = {
            "file_tag": file_tag,
            "display_date": display_date_str,
            "path": report_path,
            "created": today.isoformat(),
        }
        # 중복 누적 방지(같은 file_tag면 갱신)
        pending = [p for p in pending if p.get("file_tag") != file_tag]
        pending.append(entry)
        state["pending_reports"] = pending
        save_state(state)
        print(f"\n🏖️ 오늘은 {reason}({today.strftime('%Y-%m-%d')})이라 Teams 전송을 보류합니다.")
        print(f"   미전송 리포트 누적: 총 {len(pending)}건 (전송은 다음 근무일에 일괄 진행)")
    else:
        # 근무일: 누적분 + 당일분 일괄 전송
        # 첨부 파일 목록(과거 누적 → 당일 순, 존재하는 것만)
        attach = []
        labels = []
        for p in pending:
            if os.path.exists(p.get("path", "")):
                attach.append(p["path"])
                labels.append(p.get("display_date", p.get("file_tag", "")))
        # 당일분(누적에 이미 없으면 추가)
        if report_path not in attach:
            attach.append(report_path)
            labels.append(display_date_str)

        # 안내 메시지 구성
        if len(attach) == 1:
            msg = f"안녕하세요, {labels[0]}일 방송준비 운영이슈 리포트 공유드립니다."
        else:
            joined = ", ".join(labels)
            msg = ("안녕하세요, 휴일 기간 미전송분을 포함하여 운영이슈 리포트 "
                   f"{len(attach)}건을 한 번에 공유드립니다.\n대상 일자: {joined}")

        print(f"\n📄 전송 대상 {len(attach)}건: {labels}")
        ok = send_teams_message(user_id, user_pw, attach, msg)

        if ok:
            # 전송 성공 → 누적 비움
            state["pending_reports"] = []
            state["last_sent"] = today.isoformat()
            save_state(state)
            print(f"✅ 일괄 전송 완료. 미전송 누적을 비웠습니다.")
        else:
            # 실패 → 당일분도 누적에 추가해 다음 근무일 재시도
            if not any(p.get("file_tag") == file_tag for p in pending):
                pending.append({
                    "file_tag": file_tag,
                    "display_date": display_date_str,
                    "path": report_path,
                    "created": today.isoformat(),
                })
            state["pending_reports"] = pending
            save_state(state)
            print(f"⚠️ 전송 실패. 다음 실행에서 재시도합니다. (누적 {len(pending)}건)")


if __name__ == "__main__":
    main()
