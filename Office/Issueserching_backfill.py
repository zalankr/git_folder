"""
Issueserching_backfill.py
─────────────────────────────────────────────────────────────
[1회성 백필 전용] 지난 기간(예: 6/1~6/10) 운영이슈를 일괄 크롤링하여
  ① 일자별 HTML 리포트 생성
  ② 구글시트 월 시트에 누적 백업
하는 버전. (Teams 전송 기능 없음)

사용법:
  python Issueserching_backfill.py --start 641600 --end 641829
  (구간 미지정 시 아래 DEFAULT_START/END 사용)
  python Issueserching_backfill.py --probe 1.0 빠르게

주의:
  - 게시물 날짜 텍스트(YY.M.D)를 기준으로 '일자별'로 묶어 HTML을 만든다.
  - 같은 (일자+시간대+프로그램명)은 구글시트에서 중복 저장되지 않는다.
"""

import os
import ssl
import time
import re
import json
import argparse
import urllib3
from datetime import datetime, timedelta
from collections import OrderedDict
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

# 백필 기본 구간. 6/1(635188) ~ 6/10(641829). 중간에 큰 점프 존재
# (6/7 635315 → 6/8 641773). 적응형 크롤러가 점프를 자동으로 건너뜀.
DEFAULT_START = 635188
DEFAULT_END = 641829

BASE_URL = "https://coni.gsretail.com/program/dashboard/shoplive/{}"

# ----------------------------------------------------------
# 구글시트 백업 설정 (메인 코드와 동일)
# ----------------------------------------------------------
ENABLE_GSHEET = True
GSHEET_CRED_PATH = r"C:\Users\GSR\Desktop\Code\service_account.json"
GSHEET_2026_ID = "1Gd2Pi8WSrhR6_94KhoxdfexwuLB1VdM89-DVBVgLKOY"
GSHEET_SHARE_EMAIL = "ilpus0270@gmail.com"
GSHEET_NAME_FMT = "{year}_운영이슈"


# ==========================================================
# 2. 기본 유틸
# ==========================================================
def read_credentials():
    if not os.path.exists(CREDENTIAL_PATH):
        raise FileNotFoundError(f"⚠️ 계정 파일 누락: {CREDENTIAL_PATH}")
    with open(CREDENTIAL_PATH, "r", encoding="utf-8") as f:
        lines = f.read().splitlines()
        return lines[0].strip(), lines[1].strip()


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


def date_to_file_tag(date_part):
    """'26. 6. 1.' → '26_6_1' (파일명용)"""
    m = re.search(r'(\d+)\.\s*(\d+)\.\s*(\d+)\.', date_part)
    if m:
        return f"{m.group(1)}_{m.group(2)}_{m.group(3)}"
    return date_part.replace(". ", "_").replace(".", "").strip()


# ==========================================================
# 3. 로그인 & 크롤링 (ID 구간)
# ==========================================================
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


def fetch_one_page(driver, wait, cid):
    """단일 게시물 페이지를 읽어 dict 반환. 빈/없는 페이지면 None.
    (수집용 - 정상 wait 사용)"""
    driver.get(BASE_URL.format(cid))
    try:
        date_xpath = "//span[contains(@class, 'text-3lg') and not(contains(@class, 'border-l'))]"
        program_date = wait.until(
            EC.presence_of_element_located((By.XPATH, date_xpath))).text.strip()
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
        "id": cid, "date": program_date,
        "datetime": prog_dt.isoformat() if prog_dt else None,
        "name": program_name, "issue": issue_text,
    }


def probe_exists(driver, cid, probe_timeout=2.0):
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


def find_next_valid_id(driver, wait, from_id, fine_limit=30,
                       coarse_step=14, coarse_max_span=30000,
                       probe_timeout=1.5):
    """from_id 이상에서 '가장 가까운 유효 게시물'의 page(dict)를 찾아 반환. 없으면 None.

    속도 개선 핵심:
      - 빈 ID 확인을 probe_exists(짧은 타임아웃)로 처리 → 빈 페이지당 15초→1.5초.
      - 정밀(1씩)은 소량(기본 30)만, 그 뒤는 고정 보폭(14)으로 빠르게 도약.
      - 보폭 14는 하루 방송 블록 최소폭(약 15)보다 작아 블록을 통째로 건너뛰지 않음.
      - 유효 ID를 한 번 찍으면 '블록의 시작'을 역방향으로 정밀 탐색하여
        그 날짜의 진짜 첫 게시물을 반환.
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
    #    하한은 hit_id - back_margin (하루 블록폭 최대 약 19 + 여유).
    #    단, 이미 처리된 구간을 다시 긁지 않도록 from_id - back_margin 밑으로는
    #    내려가되, 음수/0은 방지.
    back_margin = 30
    back_floor = max(1, min(from_id, hit_id) - back_margin)
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
    # 혹시 block_start 재읽기 실패 시 hit_id로 폴백
    return fetch_one_page(driver, wait, hit_id)


def crawl_range_with_jump(driver, wait, start_id, end_id,
                          empty_tolerance=5, probe_timeout=1.5):
    """start_id ~ end_id 를 수집하되, 빈 구간(점프)을 만나면
    find_next_valid_id로 다음 유효 게시물까지 건너뛴다.

    속도 개선: 각 ID를 먼저 probe_exists(짧은 타임아웃)로 확인하고,
    존재할 때만 full fetch_one_page를 호출 → 빈 페이지 대기시간 대폭 감소.
    빈 페이지 empty_tolerance(기본 5)연속이면 즉시 점프 탐색으로 전환."""
    results = []
    lo, hi = min(start_id, end_id), max(start_id, end_id)
    print(f"\n================= 적응형 구간 스캔: {lo} ~ {hi} =================")

    cid = lo
    empty_run = 0
    while cid <= hi:
        # 빠른 존재 확인 먼저
        if probe_exists(driver, cid, probe_timeout):
            page = fetch_one_page(driver, wait, cid)
        else:
            page = None

        if page is not None:
            results.append(page)
            flag = "📝이슈" if page["issue"] else "·"
            print(f"  [ID {cid}] {page['date']} | {page['name']} {flag}")
            empty_run = 0
            cid += 1
            continue

        # 빈 페이지
        empty_run += 1
        if empty_run < empty_tolerance:
            cid += 1
            continue

        # 연속 빈 구간 → 점프 탐색으로 다음 유효 게시물로 건너뜀
        print(f"  …빈 페이지 {empty_run}연속 (ID {cid}) → 점프 탐색")
        nxt = find_next_valid_id(driver, wait, cid + 1, probe_timeout=probe_timeout)
        if nxt is None or nxt["id"] > hi:
            print("  🛑 다음 유효 게시물이 구간 밖이거나 없음 → 종료")
            break
        results.append(nxt)
        flag = "📝이슈" if nxt["issue"] else "·"
        print(f"  [ID {nxt['id']}] {nxt['date']} | {nxt['name']} {flag} (점프 착지)")
        cid = nxt["id"] + 1
        empty_run = 0

    return results


def crawl_id_range(driver, wait, start_id, end_id):
    """하위호환용: 적응형 버전으로 위임."""
    return crawl_range_with_jump(driver, wait, start_id, end_id)


# ==========================================================
# 4. 일자별 HTML 리포트 생성
#   - results 를 '일자(YY.M.D)' 단위로 묶어 각각 별도 HTML 파일 생성.
# ==========================================================
def build_html(data_list, display_date_str):
    html = f"""<!DOCTYPE html>
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
        html += '<div class="no-data"><p>해당 일자에 등록된 프로그램 및 운영이슈가 없습니다.</p></div>'
    else:
        for item in data_list:
            issue = item['issue']
            cls = "issue-content"
            if not issue or issue.strip() in ("", "등록된 운영 이슈를 찾지 못했습니다."):
                issue = "운영이슈 없음"
                cls = "issue-content issue-empty"
            html += f"""
        <div class="card">
            <div class="card-top">
                <h2 class="program-title">{item['name']}</h2>
                <div class="program-meta">
                    <span class="program-id">ID {item['id']}</span>
                    <span class="program-date">{item['date']}</span>
                </div>
            </div>
            <div class="{cls}">{issue}</div>
        </div>"""
    html += "</div></body></html>"
    return html


def generate_daily_html_reports(results):
    """results 를 일자(YY.M.D)별로 묶어 각각 HTML 파일 생성."""
    os.makedirs(REPORT_DIR, exist_ok=True)

    # 일자별 그룹화 (입력 순서 유지)
    groups = OrderedDict()
    for r in results:
        date_part, _ = split_date_time(r.get("date", ""), r.get("datetime"))
        if not date_part:
            date_part = "미상"
        groups.setdefault(date_part, []).append(r)

    created = []
    for date_part, items in groups.items():
        file_tag = date_to_file_tag(date_part)
        path = os.path.join(REPORT_DIR, f"운영이슈_리포트_{file_tag}.html")
        with open(path, "w", encoding="utf-8") as f:
            f.write(build_html(items, date_part))
        print(f"📄 HTML 생성: {path} ({len(items)}건)")
        created.append(path)
    print(f"\n✅ 일자별 HTML {len(created)}개 생성 완료.")
    return created


# ==========================================================
# 5. 구글시트 백업 (메인 코드와 동일 로직)
# ==========================================================
def _gs_open_or_create_spreadsheet(gc, year):
    if year == 2026 and GSHEET_2026_ID:
        try:
            return gc.open_by_key(GSHEET_2026_ID)
        except Exception as e:
            print(f"ℹ️ 2026 ID 열기 실패({e}). 파일명으로 재시도합니다.")
    target_name = GSHEET_NAME_FMT.format(year=year)
    try:
        return gc.open(target_name)
    except Exception:
        pass
    print(f"🆕 '{target_name}' 스프레드시트를 새로 생성합니다...")
    sh = gc.create(target_name)
    try:
        sh.share(GSHEET_SHARE_EMAIL, perm_type='user', role='writer')
    except Exception as e:
        print(f"⚠️ 공유 설정 실패(무시 가능): {e}")
    for m in range(1, 13):
        sh.add_worksheet(title=f'{m}월', rows=600, cols=12)
    try:
        sh.del_worksheet(sh.get_worksheet(0))
    except Exception:
        pass
    print(f"✅ '{target_name}' 생성 완료.")
    return sh


def _gs_get_month_worksheet(sh, month):
    title = f"{month}월"
    try:
        return sh.worksheet(title)
    except Exception:
        return sh.add_worksheet(title=title, rows=600, cols=12)


def _gs_format_issue_column(sh, ws):
    try:
        sheet_id = ws._properties['sheetId']
        requests = [
            {"updateDimensionProperties": {
                "range": {"sheetId": sheet_id, "dimension": "COLUMNS", "startIndex": 3, "endIndex": 4},
                "properties": {"pixelSize": 600}, "fields": "pixelSize"}},
            {"updateDimensionProperties": {
                "range": {"sheetId": sheet_id, "dimension": "COLUMNS", "startIndex": 0, "endIndex": 3},
                "properties": {"pixelSize": 110}, "fields": "pixelSize"}},
            {"repeatCell": {
                "range": {"sheetId": sheet_id, "startColumnIndex": 3, "endColumnIndex": 4},
                "cell": {"userEnteredFormat": {"wrapStrategy": "WRAP", "verticalAlignment": "TOP"}},
                "fields": "userEnteredFormat(wrapStrategy,verticalAlignment)"}},
            {"repeatCell": {
                "range": {"sheetId": sheet_id, "startRowIndex": 0, "endRowIndex": 1},
                "cell": {"userEnteredFormat": {"textFormat": {"bold": True}, "horizontalAlignment": "CENTER"}},
                "fields": "userEnteredFormat(textFormat,horizontalAlignment)"}},
        ]
        sh.batch_update({"requests": requests})
    except Exception as e:
        print(f"⚠️ 서식 적용 실패(데이터 저장은 정상): {e}")


def backup_to_gsheet(results):
    """크롤링 결과를 (연·월별로 나눠) 구글시트에 백업.
    백필은 여러 날짜가 섞여 있을 수 있으나, 모두 같은 달이라고 가정하되
    안전하게 (연,월) 묶음으로 처리한다."""
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

    # (연,월)별로 그룹화
    ym_groups = OrderedDict()
    for r in results:
        dt = None
        if r.get("datetime"):
            try:
                dt = datetime.fromisoformat(r["datetime"])
            except Exception:
                dt = None
        if dt is None:
            dt = parse_program_date(r.get("date", ""))
        if dt is None:
            continue
        ym_groups.setdefault((dt.year, dt.month), []).append(r)

    headers = ["일자", "시간대", "프로그램명", "운영이슈"]

    for (year, month), items in ym_groups.items():
        try:
            sh = _gs_open_or_create_spreadsheet(gc, year)
            ws = _gs_get_month_worksheet(sh, month)
        except Exception as e:
            print(f"❌ {year}/{month} 시트 열기 실패: {e}")
            continue

        all_values = ws.get_all_values()
        if not all_values or not all_values[0] or all_values[0][:4] != headers:
            ws.update(values=[headers], range_name='A1:D1')
            if not all_values:
                all_values = [headers]
            else:
                all_values[0] = headers

        existing_keys = set()
        for row in all_values[1:]:
            if len(row) >= 3:
                existing_keys.add((row[0].strip(), row[1].strip(), row[2].strip()))

        new_rows = []
        for r in items:
            date_part, time_part = split_date_time(r.get("date", ""), r.get("datetime"))
            name = (r.get("name") or "").strip()
            issue = (r.get("issue") or "").strip() or "운영이슈 없음"
            key = (date_part, time_part, name)
            if key in existing_keys:
                continue
            existing_keys.add(key)
            new_rows.append([date_part, time_part, name, issue])

        if not new_rows:
            print(f"ℹ️ {month}월: 추가할 신규 행 없음(모두 기존 저장).")
        else:
            start_row = len(all_values) + 1
            end_row = start_row + len(new_rows) - 1
            ws.update(values=new_rows, range_name=f'A{start_row}:D{end_row}')
            print(f"✅ {month}월 시트에 {len(new_rows)}건 추가 (행 {start_row}~{end_row})")

        _gs_format_issue_column(sh, ws)

    print("📊 구글시트 백업 완료.")


# ==========================================================
# 6. Main
# ==========================================================
def main():
    parser = argparse.ArgumentParser(description="[백필] 운영이슈 일괄 크롤링 + 일자별 HTML + 구글시트")
    parser.add_argument("--start", type=int, default=DEFAULT_START, help="스캔 시작 ID")
    parser.add_argument("--end", type=int, default=DEFAULT_END, help="스캔 끝 ID")
    parser.add_argument("--no-gsheet", action="store_true", help="구글시트 백업 생략")
    parser.add_argument("--probe", type=float, default=1.5,
                        help="빈 페이지 판정 타임아웃(초). 네트워크가 빠르면 1.0~1.2로 낮추면 더 빠름")
    args = parser.parse_args()

    print("🤖 [백필] 운영이슈 일괄 처리 시스템을 가동합니다.")
    print(f"   대상 구간: {args.start} ~ {args.end} (probe={args.probe}s)")
    user_id, user_pw = read_credentials()

    driver, wait = login_dashboard(user_id, user_pw)
    results = []
    try:
        results = crawl_range_with_jump(driver, wait, args.start, args.end,
                                        probe_timeout=args.probe)
    finally:
        driver.quit()

    if not results:
        print("❌ 수집된 데이터가 없습니다. 구간을 확인하세요.")
        return

    # 일자별 HTML 생성
    generate_daily_html_reports(results)

    # 구글시트 백업
    if ENABLE_GSHEET and not args.no_gsheet:
        try:
            backup_to_gsheet(results)
        except Exception as e:
            print(f"⚠️ 구글시트 백업 중 오류: {e}")
    else:
        print("\n⏸️ 구글시트 백업은 건너뜁니다.")

    print("\n🎉 백필 작업 완료.")


if __name__ == "__main__":
    main()
