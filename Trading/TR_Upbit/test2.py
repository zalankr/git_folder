import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime

# 사용법:

# credentials.json 파일 경로와 스프레드시트 이름만 수정
# python 파일명.py 실행

# 생성되는 컬럼:
# date_record day, position_position, position_ETH_weight, balance_Total_balance 등으로 자동 생성됩니다.
# 매일 실행하면 해당 월 시트에 데이터가 순차적으로 쌓이게 됩니다!

# Google spread account 연결 및 오픈 ######################## 회사에서 깃으로 json파일
gc = gspread.service_account("C:/Users/ilpus/Desktop/NKL_invest/service_account.json")
url = 'https://docs.google.com/spreadsheets/d/19KCxCqF32emisAEO1zT0XEDgD_Ye4n2-R3-0jzbZ-zs/edit?gid=1963431369#gid=1963431369'

def open_gspread(gc, url, month): # 기 작성 URL기입
    spreadsheet = gc.open_by_url(url) # 스프레드시트 url주소로 연결
    worksheet = spreadsheet.get_worksheet(month) # 해당월 워크시트 가져오기
    return worksheet

# 구글 스프레드시트 연결 설정
def connect_google_sheets(credentials_file, spreadsheet_name):
    scope = ['https://spreadsheets.google.com/feeds',
             'https://www.googleapis.com/auth/drive']
    
    creds = Credentials.from_service_account_file(credentials_file, scopes=scope)
    client = gspread.authorize(creds)
    spreadsheet = client.open(spreadsheet_name)
    
    return spreadsheet

# JSON 데이터를 플랫하게 변환
def flatten_data(data):
    flattened = {}
    for key, value in data.items():
        if isinstance(value, dict):
            for sub_key, sub_value in value.items():
                flattened[f"{key}_{sub_key}"] = sub_value
        else:
            flattened[key] = value
    return flattened

# 데이터를 구글 스프레드시트에 저장
def save_to_sheets(spreadsheet, data, month):
    # 월별 시트명
    month_names = {1: "1월", 2: "2월", 3: "3월", 4: "4월", 5: "5월", 6: "6월",
                   7: "7월", 8: "8월", 9: "9월", 10: "10월", 11: "11월", 12: "12월"}
    
    sheet_name = month_names[month]
    worksheet = spreadsheet.worksheet(sheet_name)
    
    # 데이터 플랫하게 변환
    flattened_data = flatten_data(data)
    
    # 모든 기존 데이터 가져오기
    all_values = worksheet.get_all_values()
    
    # 첫 번째 행이 비어있으면 헤더 생성
    if not all_values or not all_values[0]:
        headers = list(flattened_data.keys())
        worksheet.update('A1', [headers])
        next_row = 2
    else:
        # 기존 헤더 사용
        headers = all_values[0]
        next_row = len(all_values) + 1
    
    # 헤더 순서에 맞춰 데이터 정렬
    new_row = []
    for header in headers:
        value = flattened_data.get(header, "")
        new_row.append(value)
    
    # 데이터 추가
    worksheet.update(f'A{next_row}', [new_row])
    print(f"{sheet_name} 시트 {next_row}행에 데이터 저장 완료")

# 메인 실행 함수
def main():
    # 현재 시간
    now = datetime.now()
    
    # Upbit 데이터 (사용자 제공 데이터)
    upbit_data = {
        "date": {
            "record day": now.strftime('%Y-%m-%d')
        },
        "position": {
            "position": "Long",
            "ETH_weight": 0.7,
            "ETH_target": 0.8,
            "CASH_weight": 0.3,
            "Invest_quantity": 1000000
        },
        "balance": {
            "Total_balance": 1500000,
            "ETH": 1050000,
            "KRW": 450000
        },
        "Historical_data": {
            "last_month_Total_balance": 1400000,
            "last_year_Total_balance": 1200000
        },
        "return": {
            "daily_return": 0.0,
            "montly_return": 0.0,
            "yearly_return": 5.55
        }
    }
    
    # 설정값 (실제 값으로 변경 필요)
    credentials_file = "credentials.json"  # 구글 서비스 계정 JSON 파일 경로
    spreadsheet_name = "Upbit 투자 데이터"  # 스프레드시트 이름
    
    # 구글 스프레드시트 연결
    spreadsheet = connect_google_sheets(credentials_file, spreadsheet_name)
    
    # 현재 월 계산
    current_month = now.month
    
    # 데이터 저장
    save_to_sheets(spreadsheet, upbit_data, current_month)

if __name__ == "__main__":
    main()

# 필요한 라이브러리 설치:
# pip install gspread google-auth