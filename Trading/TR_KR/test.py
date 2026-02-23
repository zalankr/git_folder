import telegram_alert as TA
import sys

# 단일 문자열
TA.send_telegram("🚨 AAPL 목표가 도달 — 현재가: $195.4")

# 문자열 리스트 (줄바꿈 결합 → 한 메시지로 전송)
TA.send_telegram([
    "📊 <b>[포트폴리오 리포트]</b>",
    "",
    "  AAPL  $195.4  +1.2%",
    "  NVDA  $875.2  +3.5%",
    "  TSLA  $210.8  -0.8%",
    "",
    "▶ 총 평가금액: $128,450",
    "▶ 일간 손익: +$1,230 (+0.97%)",
])

sys.exit(0)