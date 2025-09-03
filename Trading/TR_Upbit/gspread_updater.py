import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime
import json

# 사용법:
# 필요한 라이브러리 설치:
# pip install gspread google-auth
# credentials.json 파일 경로와 스프레드시트 이름만 수정
# python 파일명.py 실행

# 생성되는 컬럼: 자동 생성됩니다.
# 매일 실행하면 해당 월 시트에 데이터가 순차적으로 쌓이게 됩니다!

# 구글 스프레드시트 연결 설정
def connect_google_sheets(credentials_file, spreadsheet_name):
    scope = ['https://spreadsheets.google.com/feeds',
             'https://www.googleapis.com/auth/drive']
    
    creds = Credentials.from_service_account_file(credentials_file, scopes=scope)
    client = gspread.authorize(creds)
    spreadsheet = client.open(spreadsheet_name)
    
    return spreadsheet

# JSON 데이터를 플랫하게 변환(다단계 딕셔너리 구조일때 )
# def flatten_data(data):
#     flattened = {}
#     for key, value in data.items():
#         if isinstance(value, dict):
#             for sub_key, sub_value in value.items():
#                 flattened[f"{key}_{sub_key}"] = sub_value
#         else:
#             flattened[key] = value
#     return flattened

# 데이터를 구글 스프레드시트에 저장
def save_to_sheets(spreadsheet, data, month):
    # 월별 시트명
    month_names = {1: "1월", 2: "2월", 3: "3월", 4: "4월", 5: "5월", 6: "6월",
                   7: "7월", 8: "8월", 9: "9월", 10: "10월", 11: "11월", 12: "12월"}
    
    sheet_name = month_names[month]
    worksheet = spreadsheet.worksheet(sheet_name)
    
    # 데이터 플랫하게 변환
    # flattened_data = flatten_data(data)
    
    # 모든 기존 데이터 가져오기
    all_values = worksheet.get_all_values()
    
    # 첫 번째 행이 비어있으면 헤더 생성
    if not all_values or not all_values[0]:
        # headers = list(flattened_data.keys())
        headers = list(data.keys())
        worksheet.update(values=[headers], range_name='A1')
        next_row = 2
    else:
        # 기존 헤더 사용
        headers = all_values[0]
        next_row = len(all_values) + 1
    
    # 헤더 순서에 맞춰 데이터 정렬
    new_row = []
    for header in headers:
        # value = flattened_data.get(header, "")
        value = data.get(header, "")
        new_row.append(value)
    
    # 데이터 추가
    worksheet.update(values=[new_row], range_name=f'A{next_row}')
    print(f"{sheet_name} 시트 {next_row}행에 데이터 저장 완료")

# 메인 실행 함수
# def main():
#     # 현재 시간
#     now = datetime.now()
    
#     # Upbit 데이터 (사용자 제공 데이터)
#     # with open('C:/Users/ilpus/Desktop/git_folder/Trading/TR_Upbit/Upbit_data.json', 'r', encoding='utf-8') as f:
#     #     upbit_data = json.load(f)
#     # Upbit_data 만들기
#     Upbit_data = {
#         "Date": now.strftime('%Y-%m-%d'),
#         "Position": 0,
#         "ETH_weight": 0,
#         "ETH_target": 0,
#         "CASH_weight": 0,
#         "Invest_quantity": 0,
#         "Total_balance": "Total_balance",
#         "ETH": "ETH",
#         "KRW": "KRW",
#         "Last_month_Total_balance": 0,
#         "Last_year_Total_balance": 0,
#         "daily_return": 0,
#         "montly_return": 0,
#         "yearly_return": 0
#     }

#     # 설정값 (실제 값으로 변경 필요)
#     credentials_file = "C:/Users/ilpus/Desktop/NKL_invest/service_account.json"  # 구글 서비스 계정 JSON 파일 경로
#     spreadsheet_name = "2025_TR_Upbit"  # 스프레드시트 이름
    
#     # 구글 스프레드시트 연결
#     spreadsheet = connect_google_sheets(credentials_file, spreadsheet_name)
    
#     # 현재 월 계산
#     current_month = now.month
    
#     # 데이터 저장
#     save_to_sheets(spreadsheet, Upbit_data, current_month)

# if __name__ == "__main__":
#     main()