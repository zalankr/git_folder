#!/usr/bin/python3
# -*- coding: utf-8 -*-
"""
PEN_preflight.py  ―  연금저축계좌 자동매매 장전 검증 스크립트 (READ-ONLY)
==========================================================================
실제 주문을 단 한 건도 내지 않습니다. 조회 API만 호출합니다.

점검 항목
  1) 토큰 발급/유효성
  2) 네트워크(KIS 서버 9443 포트)
  3) 거래일 여부 (오늘 / 6월 1일)
  4) 계좌 요약(nass_amt 기반 총자산/주식/현금) 정합성
  5) 매수가능금액(nrcvb_buy_amt) vs cash_balance 비교
  6) target 7종목 weight 합계 = 1.0 검증
  7) target 7종목 현재가 조회 가능 여부
  8) 1회차 target_qty / target_invest 시뮬레이션 (저장 안 함)
  9) 현재 보유잔고 조회 + target 외 이상종목 탐지
 10) 매도가능수량(ord_psbl_qty) vs 보유수량 차이 점검
 11) order_time() 회차 매핑 시뮬레이션 (00:00~05:50 UTC)

사용법 (EC2):
  cd /var/autobot/TR_PEN
  /usr/bin/python3 PEN_preflight.py
  # 텔레그램 알림까지 보내려면:
  /usr/bin/python3 PEN_preflight.py --tele
"""

import sys
import json
from datetime import datetime, timedelta

# ── 경로: 실제 운영 디렉터리에서 import 되도록 ───────────────────────────────
sys.path.insert(0, "/var/autobot/TR_PEN")
sys.path.insert(0, "/var/autobot")

import KIS_PEN

SEND_TELE = "--tele" in sys.argv

# 텔레그램은 옵션. 기본은 콘솔만.
def log(msg):
    print(msg)

def tele(msg):
    if SEND_TELE:
        try:
            import telegram_alert as TA
            TA.send_tele(msg)
        except Exception as e:
            print(f"[tele skip] {e}")

# ── 계좌 설정 (PEN_TR.py와 동일하게 유지) ───────────────────────────────────
key_file_path   = "/var/autobot/KIS/kis43685950nkr.txt"
token_file_path = "/var/autobot/KIS/kis43685950_token.json"
cano            = "43685950"
acnt_prdt_cd    = "22"  # 연금저축계좌

PEN_target_path = "/var/autobot/TR_PEN/PEN_target.json"

target = {
    "441800": {"name": "TIME Korea플러스배당액티브",   "weight": 0.18},
    "426030": {"name": "TIME 미국나스닥100액티브",     "weight": 0.18},
    "371160": {"name": "TIGER 차이나항셍테크",         "weight": 0.08},
    "411060": {"name": "ACE KRX금현물",               "weight": 0.15},
    "490490": {"name": "SOL 미국배당미국채혼합50",     "weight": 0.18},
    "148070": {"name": "KIWOOM 국고채10년",           "weight": 0.18},
    "261220": {"name": "KODEX WTI원유선물(H)",        "weight": 0.05},
}

PASS = "✅"
WARN = "⚠️ "
FAIL = "❌"

results = []   # (level, text)

def add(level, text):
    results.append((level, text))
    log(f"{level} {text}")

# ──────────────────────────────────────────────────────────────────────────
log("=" * 70)
log("PEN_preflight 시작  " + datetime.now().strftime("%Y-%m-%d %H:%M:%S UTC"))
log("=" * 70)

# 1) 인스턴스 생성 + 토큰
try:
    KIS = KIS_PEN.KIS_API(key_file_path, token_file_path, cano, acnt_prdt_cd)
    if KIS.access_token:
        add(PASS, f"토큰 OK (앞 12자: {KIS.access_token[:12]}...)")
    else:
        add(FAIL, "토큰 없음 → 종료")
        sys.exit(1)
except SystemExit:
    raise
except Exception as e:
    add(FAIL, f"KIS 인스턴스 생성 실패: {e}")
    sys.exit(1)

# 2) 네트워크
try:
    import socket
    socket.create_connection(("openapi.koreainvestment.com", 9443), timeout=5)
    add(PASS, "KIS 서버 9443 연결 OK")
except Exception as e:
    add(FAIL, f"KIS 서버 접속 불가: {e}")

# 3) 거래일 여부 (오늘 + 6/1)
today = datetime.now()
is_today = KIS.is_KR_trading_day(today)
add(PASS if is_today else WARN,
    f"오늘({today.strftime('%Y-%m-%d')}) 거래일 여부: {is_today}")

jun1 = datetime(today.year, 6, 1)
is_jun1 = KIS.is_KR_trading_day(jun1)
if is_jun1:
    add(PASS, f"6/1({jun1.strftime('%a')}) 거래일 → 정상 실행 예정")
else:
    add(WARN, f"6/1({jun1.strftime('%a')}) 휴장일 → health_check()에서 즉시 sys.exit(0) 종료됨. 의도 확인!")

# 4) 계좌 요약
acct = KIS.get_KR_account_summary()
if not isinstance(acct, dict):
    add(FAIL, f"계좌요약 조회 실패: {acct}")
    acct = None
else:
    ta = acct["total_krw_asset"]
    se = acct["stock_eval_amt"]
    cb = acct["cash_balance"]
    add(PASS, f"총자산(nass_amt): {int(ta):,}원  |  주식: {int(se):,}원  |  현금(파생): {int(cb):,}원")
    # 정합성: 주식 + 현금 = 총자산
    if abs((se + cb) - ta) > 10:
        add(WARN, f"정합성 경고: 주식+현금({int(se+cb):,}) ≠ 총자산({int(ta):,})")
    else:
        add(PASS, "정합성 OK (주식+현금 = 총자산)")
    if cb < 0:
        add(WARN, f"현금이 음수({int(cb):,}) → 미수/대출 의심. 매수 단계 주의")

# 5) 매수가능금액
KRW = KIS.get_KR_orderable_cash()
if not isinstance(KRW, (int, float)):
    add(FAIL, f"매수가능금(nrcvb_buy_amt) 조회 실패: {KRW}")
    KRW = None
else:
    add(PASS, f"매수가능금(nrcvb_buy_amt): {int(KRW):,}원")
    if acct and KRW < acct["cash_balance"] - 10:
        add(WARN, f"매수가능금({int(KRW):,}) < 현금잔고({int(acct['cash_balance']):,}) "
                  f"→ 미체결 매도 미반영분 또는 묶인 예수금 존재 가능")

# 6) weight 합계
total_w = sum(v["weight"] for v in target.values())
if abs(total_w - 1.0) <= 0.01:
    add(PASS, f"target weight 합계 = {total_w:.3f}")
else:
    add(FAIL, f"target weight 합계 = {total_w:.3f} (1.0 아님!)")

# 7) + 8) 현재가 조회 + 1회차 시뮬레이션
add(PASS, "── target 종목 현재가 / 1회차 목표수량 시뮬레이션 ──")
this_asset = acct["total_krw_asset"] if acct else 0
sim_total_invest = 0
price_fail = 0
for code, info in target.items():
    price = KIS.get_KR_current_price(code)
    if not isinstance(price, int) or price == 0:
        add(FAIL, f"  {code} {info['name']}: 현재가 조회 실패 ({price})")
        price_fail += 1
        continue
    t_invest = int(info["weight"] * this_asset)
    t_qty = t_invest // price if price else 0
    sim_total_invest += t_qty * price
    log(f"    {code} {info['name'][:18]:<18} "
        f"현재가 {price:>8,}원  목표 {info['weight']*100:>4.1f}%  "
        f"투자 {t_invest:>12,}원  →  {t_qty:>5,}주")

if price_fail == 0:
    add(PASS, f"전 종목 현재가 OK | 1회차 목표 매수금 합계 약 {int(sim_total_invest):,}원")
else:
    add(FAIL, f"현재가 조회 실패 {price_fail}종목 → 1회차에서 sys.exit(1) 위험")

if acct and sim_total_invest > acct["total_krw_asset"] * 1.02:
    add(WARN, f"목표매수금({int(sim_total_invest):,}) > 총자산 → 비중/현금 점검")

# 9) + 10) 현재 보유 잔고 + 매도가능수량 점검
add(PASS, "── 현재 보유 잔고 ──")
stocks = KIS.get_KR_stock_balance()
if not isinstance(stocks, list):
    add(FAIL, f"잔고 조회 실패: {stocks}")
    stocks = []
else:
    target_codes = set(target.keys())
    held_codes = set()
    for s in stocks:
        code = s["종목코드"]
        held_codes.add(code)
        flag = "" if code in target_codes else "  ← target 외 이상종목!"
        gap = s["보유수량"] - s["매도가능수량"]
        gap_txt = f"  (매도가능 {s['매도가능수량']}, 차이 {gap})" if gap else ""
        log(f"    {code} {s['종목명'][:18]:<18} {s['보유수량']:>5,}주 "
            f"평가 {s['평가금액']:>12,}원{gap_txt}{flag}")
        if code not in target_codes:
            add(WARN, f"  {s['종목명']}({code})는 target에 없음 → 전량 매도 대상")
        if gap > 0:
            add(WARN, f"  {code} 보유({s['보유수량']}) ≠ 매도가능({s['매도가능수량']}) "
                      f"→ 매도 시 min() cap 필요")
    missing = target_codes - held_codes
    if missing:
        add(PASS, f"미보유 target(신규매수 예정): {', '.join(missing)}")
    else:
        add(PASS, "target 전 종목 보유 중")

# 11) 회차 매핑 시뮬레이션
add(PASS, "── order_time() 회차 매핑 (UTC 00:00~05:50, 30분 간격) ──")
def sim_round(hour, minute):
    cur = hour * 60 + minute
    start, end = 0, 5 * 60 + 50
    if start <= cur <= end:
        return min((cur - start) // 30 + 1, 12)
    return 0
for h in range(0, 6):
    row = []
    for m in (0, 30):
        r = sim_round(h, m)
        row.append(f"{h:02d}:{m:02d}→{r}회차")
    log("    " + "   ".join(row))
now_r = sim_round(today.hour, today.minute)
add(PASS, f"현재시각 UTC {today.strftime('%H:%M')} → {now_r}회차 "
          f"({'매매시간' if now_r > 0 else '매매시간 아님'})")

# ── 요약 ────────────────────────────────────────────────────────────────────
log("=" * 70)
n_fail = sum(1 for lv, _ in results if lv == FAIL)
n_warn = sum(1 for lv, _ in results if lv == WARN)
summary = f"PEN_preflight 완료: {FAIL}{n_fail}건 / {WARN}{n_warn}건"
log(summary)
log("=" * 70)

if SEND_TELE:
    tele_lines = [summary]
    tele_lines += [f"{lv}{txt}" for lv, txt in results if lv in (FAIL, WARN)]
    tele("\n".join(tele_lines) if len(tele_lines) > 1 else f"{summary}\n모든 점검 통과 {PASS}")

sys.exit(1 if n_fail else 0)
