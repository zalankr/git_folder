import USLA_model
from datetime import datetime

# USLA모델 instance 생성
key_file_path = "/var/autobot/TR_USLA/kis63721147nkr.txt"
token_file_path = "/var/autobot/TR_USLA/kis63721147_token.json"
cano = "63721147"  # 종합계좌번호 (8자리)
acnt_prdt_cd = "01"  # 계좌상품코드 (2자리)
USLA_ticker = ["UPRO", "TQQQ", "EDC", "TMF", "TMV"]
USLA = USLA_model.USLA_Model(key_file_path, token_file_path, cano, acnt_prdt_cd)

# 지난 USLA data 불러오기
USLA_data = USLA.load_USLA_data()

# date 업데이트
current = datetime.now()
current_date = current.date()
USLA_data['date'] = current_date

