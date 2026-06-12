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


def crawl_id_range(driver, wait, start_id, end_id):
    """start_id ~ end_id (양끝 포함) 사이의 모든 페이지를 방문하여 수집."""
    results = []
    lo, hi = min(start_id, end_id), max(start_id, end_id)
    print(f"\n================= ID 구간 스캔: {lo} ~ {hi} ({hi - lo + 1}건) =================")

    for cid in range(lo, hi + 1):
        page = fetch_one_page(driver, wait, cid)
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
#     1) from_id 부터 1씩 최대 FINE_LIMIT(=100)개 스캔 → 유효 게시물 즉시 반환
#     2) 못 찾으면 큰 점프(coarse): step씩(10→커지며) 멀리 도약하여
#        유효 게시물이 나오는 대략 위치를 먼저 찾는다
#     3) 대략 위치를 찾으면 그 '직전 도약폭'을 1씩 되짚어 정확한 시작 ID 확정
# ==========================================================
def find_next_valid_id(driver, wait, from_id, fine_limit=100,
                       coarse_step=10, coarse_max_span=20000):
    """from_id 이상에서 '가장 가까운 유효 게시물'의 페이지(dict)를 찾아 반환.
    못 찾으면 None."""
    print(f"\n🔎 다음 유효 게시물 탐색 시작 (from {from_id})")

    # 1) 정밀(1씩) 탐색
    cid = from_id
    fine_checked = 0
    while fine_checked < fine_limit:
        page = fetch_one_page(driver, wait, cid)
        if page is not None:
            print(f"   ✔ 정밀탐색에서 발견: ID {cid} ({page['date']})")
            return page
        cid += 1
        fine_checked += 1
    print(f"   …정밀 {fine_limit}개 내 없음 → 큰 점프(coarse) 탐색 전환")

    # 2) coarse 점프: step을 점점 키우며 유효 페이지가 나오는 지점을 찾는다
    coarse_pos = cid  # 정밀 탐색이 끝난 지점부터
    step = coarse_step
    span = 0
    last_empty = coarse_pos - 1  # 직전까지 비어있던 마지막 위치
    found_page = None
    while span < coarse_max_span:
        page = fetch_one_page(driver, wait, coarse_pos)
        if page is not None:
            found_page = page
            print(f"   ✔ coarse 도약에서 발견: ID {coarse_pos} ({page['date']})")
            break
        last_empty = coarse_pos
        coarse_pos += step
        span += step
        # 보폭 확대하되 상한 15: 하루 방송 구간 폭(약 19)보다 작아야
        # 도약 중 유효 구간을 건너뛰지 않는다.
        if step < 15:
            step = min(step * 2, 15)
        print(f"   …coarse 빈 구간 통과: 다음 {coarse_pos} (step={step}, 누적 {span})")

    if found_page is None:
        print(f"   ❌ coarse {coarse_max_span} 범위 내 유효 게시물 없음")
        return None

    # 3) 되짚기: last_empty+1 ~ found_page['id'] 사이의 '진짜 시작 ID'를 1씩 확인
    #    (coarse가 건너뛴 사이에 더 앞선 유효 게시물이 있을 수 있음)
    refine_start = last_empty + 1
    refine_end = found_page["id"]
    if refine_start < refine_end:
        print(f"   🔁 되짚기 정밀탐색: {refine_start} ~ {refine_end - 1}")
        for rid in range(refine_start, refine_end):
            page = fetch_one_page(driver, wait, rid)
            if page is not None:
                print(f"   ✔ 되짚기에서 더 앞선 게시물 발견: ID {rid} ({page['date']})")
                return page
    return found_page


def collect_target_date(driver, wait, first_page, target_date_key):
    """first_page(유효 게시물)부터 시작해 '목표 날짜(target_date_key)'에
    해당하는 게시물만 1씩 전진하며 수집. 목표 날짜를 지나면 종료.
    target_date_key: 'YY. M. D.' 형태 문자열 (예: '26. 6. 8.')"""
    results = []
    cid = first_page["id"]
    started = False
    miss_after_start = 0

    while True:
        page = fetch_one_page(driver, wait, cid) if cid != first_page["id"] else first_page
        if page is None:
            # 수집 시작 후 빈 페이지가 연속되면 종료(다음 점프 구간일 수 있음)
            if started:
                miss_after_start += 1
                if miss_after_start >= 15:
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
    """수집 실행. (results, used_start_hint) 반환."""
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

    # 적응형 탐색으로 from_id 이상에서 첫 유효 게시물 찾기
    first = find_next_valid_id(driver, wait, from_id)
    if first is None:
        print("❌ 다음 유효 게시물을 찾지 못했습니다.")
        return []

    # 찾은 게시물이 목표 날짜보다 과거면, 목표 날짜가 나올 때까지 전진하며 수집
    # (collect_target_date가 '아직 목표일 아님 → 전진'을 처리)
    results = collect_target_date(driver, wait, first, target_key)

    # 만약 목표 날짜를 못 만나고 끝났다면(예: 목표일 게시물이 아직 없음)
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
def send_teams_message(user_id, user_pw, file_path, file_tag):
    print("\n================= Teams 전송 프로세스 시작 =================")

    if not os.path.exists(file_path):
        print(f"❌ 첨부할 파일이 없습니다: {file_path}")
        return

    options = webdriver.ChromeOptions()
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
            return
        print(f"✅ 대상 채팅방 진입 확인: '{TEAMS_TARGET_NAME}'")

        # --- 파일 첨부 ---
        print("📎 리포트 파일 첨부를 시작합니다...")
        # 방 진입 후 메시지 영역이 완전히 렌더링되도록 추가 대기 (느린 환경 대비 상향)
        time.sleep(15)
        upload_ok = False

        # 1차: 숨은 input[type=file]에 직접 주입 (가장 안정적, 메뉴 없이 가능한 경우)
        try:
            file_input = driver.find_element(By.XPATH, "//input[@type='file']")
            file_input.send_keys(file_path)
            print("⏳ (1차) 숨은 input 직접 업로드 중 (약 15초)...")
            time.sleep(15)
            upload_ok = True
        except Exception:
            print("ℹ️ 숨은 input 미발견 → 아이콘 클릭 방식으로 전환.")

        # 2차: 첨부 아이콘 클릭 → '이 디바이스에서 업로드' → 노출된 input에 주입
        if not upload_ok:
            try:
                # 아이콘: svg/path 까지의 경로는 클릭이 빗나갈 수 있어 상위 button을 클릭
                attach_btn_candidates = [
                    '//*[@id="message-pane-layout-a11y"]/div[4]/div/div/div[4]/div/div[3]/div[2]/button[2]',
                    '//button[contains(@aria-label,"첨부") or contains(@aria-label,"Attach")]',
                    '//button[contains(@aria-label,"파일") or contains(@aria-label,"File")]',
                ]
                attach_btn = None
                # 아이콘이 늦게 뜰 수 있어 넉넉히 재시도 (느린 환경 대비 5회)
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

                # '이 디바이스에서 업로드' 메뉴
                upload_menu_candidates = [
                    "/html/body/div[12]/div/div[2]/div/div[1]/div/ul/li[9]/a/span[2]/span",
                    "//*[contains(text(),'이 디바이스') or contains(text(),'Upload from this device')]",
                    "//ul//a[contains(.,'업로드') or contains(.,'Upload')]",
                ]
                menu_clicked = False
                for xp in upload_menu_candidates:
                    try:
                        menu = WebDriverWait(driver, 6).until(
                            EC.element_to_be_clickable((By.XPATH, xp)))
                        try:
                            menu.click()
                        except Exception:
                            driver.execute_script("arguments[0].click();", menu)
                        menu_clicked = True
                        print("   '이 디바이스에서 업로드' 선택됨.")
                        time.sleep(4)
                        break
                    except Exception:
                        continue
                if not menu_clicked:
                    print("   ℹ️ 업로드 메뉴 항목을 못 찾음(이미 input 노출 가능). 계속 진행.")

                # 메뉴 클릭 후 노출되는 input[type=file]에 경로 주입 (넉넉히 대기)
                file_input = WebDriverWait(driver, 15).until(
                    EC.presence_of_element_located((By.XPATH, "//input[@type='file']")))
                file_input.send_keys(file_path)
                print("⏳ (2차) 아이콘 경유 업로드 중 (약 15초)...")
                time.sleep(15)
                upload_ok = True
            except Exception as e:
                print(f"⚠️ 파일 업로드 실패: {e}")

        if upload_ok:
            # 업로드가 채팅창에 반영(썸네일 표시)될 때까지 추가 안정화 대기
            print("⏳ 업로드 반영 대기 (약 12초)...")
            time.sleep(12)

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

        if chat_box is not None:
            try:
                date_display = file_tag.replace("_", ".")
                msg = f"안녕하세요, {date_display}일 방송준비 운영이슈 리포트 공유드립니다."
                chat_box.click()
                time.sleep(1)
                chat_box.send_keys(msg)
                time.sleep(2)
                chat_box.send_keys(Keys.ENTER)
                print("✅ Teams 메시지 발송 완료!")
                time.sleep(8)
            except Exception as e:
                print(f"⚠️ 메시지 입력 중 오류: {e}")
        else:
            if upload_ok:
                print("ℹ️ 입력창을 못 찾았지만 파일은 첨부됨. 첨부 상태에서 Enter 시도.")
                try:
                    driver.switch_to.active_element.send_keys(Keys.ENTER)
                except Exception:
                    pass
            else:
                print("⚠️ 채팅 입력창을 끝내 찾지 못했습니다.")

    except Exception as e:
        print(f"\n❌ Teams 발송 중 오류가 발생했습니다: {e}")
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

    # Teams 전송
    if ENABLE_TEAMS:
        report_path = os.path.join(REPORT_DIR, f"운영이슈_리포트_{file_tag}.html")
        if os.path.exists(report_path):
            print(f"\n📄 전송 대기 파일: {report_path}")
            send_teams_message(user_id, user_pw, report_path, file_tag)
        else:
            print(f"❌ 전송할 {file_tag} 일자 파일을 찾지 못해 Teams 발송을 취소합니다.")
    else:
        print("\n⏸️ Teams 전송 단계는 건너뜁니다 (ENABLE_TEAMS=False).")


if __name__ == "__main__":
    main()
