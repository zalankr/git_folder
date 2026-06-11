import os
import ssl
import time
import re
from datetime import datetime, timedelta
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager

# ==========================================================
# 1. 환경 설정 및 기본 변수
# ==========================================================
ssl._create_default_https_context = ssl._create_unverified_context
os.environ['WDM_SSL_VERIFY'] = '0'

# 파일 저장 및 로드 기준 경로 설정
CREDENTIAL_PATH = r"C:\Users\GSR\Desktop\Code\ilpus@gsretail.com.txt"
REPORT_DIR = r"C:\Users\GSR\Desktop\Code\git_folder\Office\daily_reports"

def read_credentials():
    """텍스트 파일에서 계정 정보를 읽어옵니다."""
    if not os.path.exists(CREDENTIAL_PATH):
        raise FileNotFoundError(f"⚠️ 계정 파일 누락: {CREDENTIAL_PATH}")
    with open(CREDENTIAL_PATH, "r", encoding="utf-8") as f:
        lines = f.read().splitlines()
        return lines[0].strip(), lines[1].strip()
    
def get_target_date_info():
    """기준일(어제)의 문자열과 파일명 포맷을 반환합니다."""
    yesterday = datetime.now() - timedelta(days=1)
    search_date_str = f"{yesterday.strftime('%y')}. {yesterday.month}. {yesterday.day}."
    file_date_str = f"{yesterday.strftime('%y')}_{yesterday.month}_{yesterday.day}"
    return search_date_str, file_date_str

def get_yesterday_info():
    """어제 날짜를 계산하여 검색용 문자열과 파일명 매칭용 문자열을 반환합니다."""
    yesterday = datetime.now() - timedelta(days=1)
    
    # 1. 크롤링 대상 문자열 포맷 (예: 26. 6. 9.)
    search_date_str = f"{yesterday.strftime('%y')}. {yesterday.month}. {yesterday.day}."
    
    # 2. 파일명용 포맷 (예: 26_6_9)
    file_date_str = f"{yesterday.strftime('%y')}_{yesterday.month}_{yesterday.day}"
    
    return search_date_str, file_date_str

def find_target_report_file(file_date_str):
    """지정된 디렉토리에서 어제 날짜로 생성된 HTML 리포트 파일을 찾습니다."""
    target_filename = f"운영이슈_리포트_{file_date_str}.html"
    file_path = os.path.join(REPORT_DIR, target_filename)
    
    if os.path.exists(file_path):
        return file_path
    else:
        return None

# ==========================================================
# 2. 크롤링 로직 (기존 함수 요약 - 이전에 완성한 함수를 그대로 쓰시면 됩니다)
# ==========================================================
def get_time_boundaries():
    """
    [업데이트] 수집 유효 시간을 '어제 05:00' ~ '오늘 03:00'으로 설정합니다.
    이 범위를 벗어나는 데이터는 무시하거나 탐색을 조기 종료합니다.
    """
    now = datetime.now()
    yesterday = now - timedelta(days=1)
    
    start_boundary = yesterday.replace(hour=5, minute=0, second=0, microsecond=0)
    end_boundary = now.replace(hour=3, minute=0, second=0, microsecond=0)
    
    return start_boundary, end_boundary

def parse_program_date(date_str):
    """'26. 6. 9.(화) 7:15~8:15' 형태의 텍스트에서 시작 시간을 datetime으로 추출합니다."""
    match = re.search(r'(\d+)\.\s*(\d+)\.\s*(\d+)\.[^\d]*(\d+):(\d+)', date_str)
    if match:
        y = int(match.group(1)) + 2000
        m = int(match.group(2))
        d = int(match.group(3))
        h = int(match.group(4))
        minute = int(match.group(5))
        return datetime(y, m, d, h, minute)
    return None

def generate_html_report(data_list, file_date_str, display_date_str):
    """데이터를 HTML로 변환하고 지정된 daily_reports 경로에 저장합니다."""
    html_file_path = os.path.join(REPORT_DIR, f"운영이슈_리포트_{file_date_str}.html")
    
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
        .program-date {{ font-size: 14px; color: var(--text-sub); background: #EBF5FF; padding: 6px 12px; border-radius: 20px; }}
        .issue-content {{ font-size: 15px; color: var(--text-main); white-space: pre-wrap; }}
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
        html_content += '<div class="no-data"><p>해당 일자에 등록된 프로그램 및 운영이슈가 없습니다.</p></div>'
    else:
        for item in data_list:
            html_content += f"""
        <div class="card">
            <div class="card-top">
                <h2 class="program-title">{item['name']}</h2>
                <span class="program-date">{item['date']}</span>
            </div>
            <div class="issue-content">{item['issue']}</div>
        </div>"""
    
    html_content += "</div></body></html>"

    with open(html_file_path, "w", encoding="utf-8") as f:
        f.write(html_content)
        
    print(f"\n📄 HTML 리포트 생성 완료: {html_file_path}")
    return html_file_path

def fetch_sequential_data(user_id, user_pw, display_date_str, file_date_str):
    start_boundary, end_boundary = get_time_boundaries()
    print(f"🕒 타겟 시간 범위: {start_boundary.strftime('%m-%d %H:%M')} ~ {end_boundary.strftime('%m-%d %H:%M')}")

    options = webdriver.ChromeOptions()
    options.add_argument("--start-maximized")
    options.add_argument("--disable-gpu")
    options.add_argument('--ignore-certificate-errors')

    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=options)
    wait = WebDriverWait(driver, 15)
    
    final_report = []
    
    try:
        print("🌐 대시보드 로그인 진행 중...")
        driver.get("https://coni.gsretail.com/program/dashboard/shoplive")

        try:
            id_field = WebDriverWait(driver, 5).until(EC.presence_of_element_located((By.XPATH, "//input[@type='email' or @id='userNameInput']")))
            id_field.send_keys(user_id + Keys.ENTER)
            time.sleep(2)
        except: pass

        pw_field = wait.until(EC.presence_of_element_located((By.XPATH, "//input[@type='password']")))
        pw_field.send_keys(user_pw + Keys.ENTER)
        time.sleep(5)

        # 동적 시작점 찾기
        page_source = driver.page_source
        numbers = re.findall(r'\b64\d{4}\b', page_source)
        current_id = max([int(n) for n in numbers]) + 2 if numbers else 641810

        print("\n================= 순차 탐색 스캔 가동 =================")
        empty_page_count = 0
        
        while True:
            driver.get(f"https://coni.gsretail.com/program/dashboard/shoplive/{current_id}")
            
            try:
                date_xpath = "//span[contains(@class, 'text-3lg') and not(contains(@class, 'border-l'))]"
                program_date = wait.until(EC.presence_of_element_located((By.XPATH, date_xpath))).text.strip()
                empty_page_count = 0 
            except Exception:
                current_id -= 1
                empty_page_count += 1
                if empty_page_count >= 10: break
                continue

            # [핵심] 텍스트에서 시간을 추출하여 범위 비교
            prog_dt = parse_program_date(program_date)
            
            if prog_dt:
                if prog_dt > end_boundary:
                    print(f"  [ID: {current_id}] {program_date} (오늘 이후 방송 -> 패스)")
                elif start_boundary <= prog_dt <= end_boundary:
                    print(f"🔄 타겟 시간대 확인! 데이터 추출 중... (ID: {current_id})")
                    try:
                        name_xpath = "//span[contains(@class, 'text-3lg') and contains(@class, 'border-l')]"
                        program_name = driver.find_element(By.XPATH, name_xpath).text.strip()
                        
                        issue_xpath = "//div[contains(@class, 'text-md/7') and .//span[contains(@class, 'text-brand-secondary')]]"
                        try:
                            issue_element = driver.find_element(By.XPATH, issue_xpath)
                            issue_text = issue_element.text.strip()
                        except:
                            issue_text = "등록된 운영 이슈를 찾지 못했습니다."

                        final_report.append({"date": program_date, "name": program_name, "issue": issue_text})
                    except: pass
                else:
                    print(f"\n🛑 스캔 완료: 설정된 범위(어제 05시) 이전 데이터에 도달했습니다.")
                    break
                    
            current_id -= 1
            
        final_report.reverse()
        html_path = generate_html_report(final_report, file_date_str, display_date_str)
        return html_path

    finally:
        driver.quit()

# ==========================================================
# 3. 신규 추가: MS Teams 자동 로그인 및 메시지 발송 로직
# ==========================================================
def send_teams_message(user_id, user_pw, file_path, file_date_str):
    print("\n================= Teams 전송 프로세스 시작 =================")
    
    options = webdriver.ChromeOptions()
    options.add_argument("--start-maximized")
    options.add_argument("--disable-gpu")
    options.add_argument('--ignore-certificate-errors')
    
    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=options)
    wait = WebDriverWait(driver, 20)
    
    try:
        # 1. Teams 접속 및 ADFS 로그인 프로세스
        print("🌐 Microsoft Teams 웹버전에 접속합니다...")
        driver.get("https://teams.microsoft.com/v2/")
        
        # 아이디 입력
        print("🔑 로그인 진행 중...")
        try:
            id_field = wait.until(EC.presence_of_element_located((By.XPATH, "//input[@type='email']")))
            id_field.clear()
            id_field.send_keys(user_id)
            id_field.send_keys(Keys.ENTER)
            time.sleep(3)
        except:
            print("ℹ️ 아이디 입력창 생략 (캐시됨)")

        # 비밀번호 입력
        pw_field = wait.until(EC.presence_of_element_located((By.XPATH, "//input[@type='password']")))
        pw_field.clear()
        pw_field.send_keys(user_pw)
        pw_field.send_keys(Keys.ENTER)
        
        # '로그인 상태 유지' 창 처리 (있을 경우 통과)
        try:
            stay_signed_in = WebDriverWait(driver, 5).until(EC.element_to_be_clickable((By.XPATH, "//input[@id='idSIButton9' or @value='예']")))
            stay_signed_in.click()
        except:
            pass
            
        print("🚀 로그인 완료. Teams 인터페이스 로딩 대기 (약 10초)...")
        time.sleep(10) # 무거운 웹앱이므로 충분한 렌더링 대기

        # 2. 수신자 검색 및 채팅방 진입
        target_name = "이민혜/영상아트팀"
        print(f"🔍 수신자 '{target_name}' 님을 검색합니다...")
        
        # 제공해주신 검색창 XPath 적용
        search_box = wait.until(EC.element_to_be_clickable((By.XPATH, '//*[@id="ms-searchux-input"]')))
        search_box.send_keys(target_name)
        time.sleep(3) # 자동완성 리스트가 뜰 때까지 잠시 대기
        search_box.send_keys(Keys.ENTER)
        print("▶ 채팅방으로 이동했습니다.")
        time.sleep(5) # 채팅창 로딩 대기

        # 3. HTML 파일 첨부 (가장 핵심적인 숨김 파일 입력 태그 찾기)
        print("📎 리포트 파일 첨부를 시작합니다...")
        try:
            # Teams 화면 내부의 숨겨진 file input 태그를 찾아 다이렉트로 절대경로 전송
            file_input = driver.find_element(By.XPATH, "//input[@type='file']")
            file_input.send_keys(file_path)
            print("⏳ 파일 업로드 중...")
            time.sleep(5) # 파일이 서버에 업로드될 여유 시간 확보
        except Exception as e:
            print("⚠️ 파일 업로드 태그를 찾지 못했습니다. 첨부 없이 텍스트만 전송할 수 있습니다.")

        # 4. 메시지 텍스트 작성 및 전송 (동적 UUID 우회 XPath 적용)
        print("✉️ 안내 메시지를 작성하고 발송합니다...")
        
        # 'new-message-'로 시작하는 id를 가진 요소를 유연하게 찾습니다.
        chat_box = wait.until(EC.element_to_be_clickable((By.XPATH, "//*[starts-with(@id, 'new-message-')] | //div[@data-tid='ckeditor-reply-message']")))
        
        # 메시지 내용 입력
        date_display = file_date_str.replace("_", ".") # 26.6.9 형식으로 변환
        chat_message = f"안녕하세요 팀장님, {date_display}일자 운영이슈 리포트 공유드립니다."
        
        chat_box.send_keys(chat_message)
        time.sleep(1)
        chat_box.send_keys(Keys.ENTER) # 전송
        
        print("✅ 성공적으로 Teams 메시지와 파일이 발송되었습니다!")
        time.sleep(3) # 발송 완료 후 시각적 확인을 위한 짧은 대기

    except Exception as e:
        print(f"\n❌ Teams 발송 중 오류가 발생했습니다: {e}")

    finally:
        driver.quit()
        print("Teams 프로세스를 종료합니다.")

# ==========================================================
# 4. 전체 자동화 파이프라인 (Main)
# ==========================================================
if __name__ == "__main__":
    print("🤖 일일 업무 자동화 시스템을 가동합니다.")
    
    user_id, user_pw = read_credentials()
    search_date_str, file_date_str = get_yesterday_info()
    
    # 1. 정보 준비
    user_id, user_pw = read_credentials()
    display_date_str, file_date_str = get_target_date_info()
    
    # 2. 크롤링 및 파일 생성 (이전 코드를 이 위치에서 호출합니다)   
    fetch_sequential_data(user_id, user_pw, display_date_str, file_date_str)  
    
    # 2. 전송할 파일 탐색
    report_file_path = find_target_report_file(file_date_str)
    
    if report_file_path:
        print(f"📄 전송 대기 파일 확인 완료: {report_file_path}")
        # 3. Teams 발송
        send_teams_message(user_id, user_pw, report_file_path, file_date_str)
    else:
        print(f"❌ 전송할 {file_date_str} 일자 파일을 찾지 못해 Teams 발송을 취소합니다.")