import kakao_alert
from tendo import singleton
me = singleton.SingleInstance()

kakao_alert.SendMessage("성공한 메세지 메시지")