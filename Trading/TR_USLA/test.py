import kakao_alert as KA
import USLA_model

# USLA모델 instance 생성
key_file_path = "/var/autobot/TR_USLA/kis63721147nkr.txt"
token_file_path = "/var/autobot/TR_USLA/kis63721147_token.json"
cano = "63721147"
acnt_prdt_cd = "01"
USLA = USLA_model.USLA_Model(key_file_path, token_file_path, cano, acnt_prdt_cd)

usd = USLA.get_US_dollar_balance()
print(usd)
print(usd['withdrawable'])
KA.SendMessage(usd['withdrawable'])