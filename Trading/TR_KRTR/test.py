#!/usr/bin/env python3
"""
StockEasy Peak 전략 자동매매 (단일 파일 통합)

실행 흐름:
  1회차 (KST 09:00 = UTC 00:00):
    → 크롤링 → buy/sell 리스트 산출 → peak_target.json 저장
    → 5분 대기 → 매도 → 10분 대기 → 매수
  2~12회차 (KST 09:30~14:30 = UTC 00:30~05:30, 30분 간격):
    → peak_target.json 로드 → 매도 → 10분 대기 → 매수
  12회차 매매 완료 후:
    → 10분 대기 → 미체결 전량취소 → 잔고조회 → peak_data.json 저장 + Telegram 리포트

crontab (UTC+0, EC2):
  0,30 0-5 * * 1-5 timeout -s 9 1500 /usr/bin/python3 /var/autobot/TR_PEAK/PEAK_TR.py

보유 상한: 20종목, 종목당 균등배분 (총자산 / 20)
"""

import sys
import json
import os
import re
import requests
import telegram_alert as TA
from datetime import datetime, timedelta
import time as time_module
from tendo import singleton

try:
    me = singleton.SingleInstance()
except singleton.SingleInstanceException:
    TA.send_tele("PEAK: 이미 실행 중입니다.")
    sys.exit(0)

import KIS_KR

# ================================================================
# 설정 (추후 입력)
# ================================================================
key_file_path   = "/var/autobot/TR_KRTR/kis_43018646.txt"        # PEAK
token_file_path = "/var/autobot/TR_KRTR/kis_43018646_token.json"  # PEAK
cano            = "43018646"   # PEAK
acnt_prdt_cd    = "01"

KIS = KIS_KR.KIS_API(key_file_path, token_file_path, cano, acnt_prdt_cd)

# 파일 경로
BASE_DIR          = "/var/autobot/TR_KRTR"
PEAK_DATA_PATH    = os.path.join(BASE_DIR, "peak_data.json")
PEAK_TARGET_PATH  = os.path.join(BASE_DIR, "peak_target.json")
PEAK_HISTORY_DIR  = os.path.join(BASE_DIR, "history")

os.makedirs(PEAK_HISTORY_DIR, exist_ok=True)

MAX_HOLDINGS = 20   # 최대 보유 종목 수


# ================================================================
# StockEasy 크롤링
# ================================================================
CRAWL_URL = "https://stockeasy.intellio.kr/strategy-room/peak"
CRAWL_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.8",
    "Referer": "https://stockeasy.intellio.kr/strategy-room",
}

def fetch_stockeasy_page() -> str:
    resp = requests.get(CRAWL_URL, headers=CRAWL_HEADERS, timeout=15)
    resp.raise_for_status()
    return resp.text

def extract_data_from_html(html: str) -> dict:
    """Next.js SSR __next_f.push 안의 initialData JSON 추출"""
    scripts = re.findall(r'self\.__next_f\.push\(\[1,"(.+?)"\]\)', html, re.DOTALL)
    for s in scripts:
        if 'initialData' not in s:
            continue
        try:
            decoded = json.loads('"' + s + '"')
        except Exception:
            continue
        m = re.search(r'"initialData":(\{.+\})\}\]', decoded, re.DOTALL)
        if not m:
            continue
        try:
            return json.loads(m.group(1))
        except json.JSONDecodeError:
            continue
    return {}

def crawl_peak_strategy() -> dict:
    """크롤링 → 진입/이탈/보유 종목 dict 반환"""
    html = fetch_stockeasy_page()
    raw = extract_data_from_html(html)
    if not raw or not raw.get("success"):
        raise ValueError("StockEasy 데이터 추출 실패")

    meta = raw.get("metadata", {})
    all_holdings, buy_list = [], []

    for sector, stocks in raw.get("holdings", {}).items():
        for s in stocks:
            item = {
                "stock_code":    s.get("stock_code", ""),
                "stock_name":    s.get("stock_name", ""),
                "sector":        sector,
                "buy_price":     s.get("buy_price", 0),
                "current_price": s.get("current_price", 0),
                "buy_date":      s.get("buy_date", ""),
                "holding_days":  s.get("holding_days", 0),
                "return_rate":   s.get("return_rate", 0),
            }
            all_holdings.append(item)
            if s.get("holding_days", 0) == 0:
                buy_list.append(item)

    sell_list = []
    for sector, stocks in raw.get("exits", {}).items():
        for s in stocks:
            sell_list.append({
                "stock_code":    s.get("stock_code", ""),
                "stock_name":    s.get("stock_name", ""),
                "sector":        sector,
                "buy_price":     s.get("buy_price", 0),
                "sell_price":    s.get("current_price", 0),
                "buy_date":      s.get("buy_date", ""),
                "holding_days":  s.get("holding_days", 0),
                "return_rate":   s.get("final_return_rate", 0),
            })

    return {
        "target_date": meta.get("target_date", ""),
        "updated_at":  meta.get("updated_at", ""),
        "buy_list":    buy_list,
        "sell_list":   sell_list,
        "holdings":    all_holdings,
    }


# ================================================================
# 유틸리티
# ================================================================
def load_json(path: str) -> dict:
    if os.path.exists(path):
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}

def save_json(data: dict, path: str):
    try:
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
    except Exception as e:
        TA.send_tele(f"PEAK: {path} 저장 실패: {e}")
        backup = os.path.join(BASE_DIR, f"backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json")
        with open(backup, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
        TA.send_tele(f"PEAK: 백업 저장: {backup}")


def health_check():
    checks = []
    if not KIS.access_token:
        checks.append("PEAK체크: API 토큰 없음")
    try:
        import socket
        socket.create_connection(("openapi.koreainvestment.com", 9443), timeout=5)
    except:
        checks.append("PEAK체크: KIS API 서버 접속 불가")
    if not KIS.is_KR_trading_day():
        checks.append("PEAK체크: 거래일이 아닙니다.")
    if checks:
        TA.send_tele(checks)
        sys.exit(0)


def order_time():
    """
    거래회차 산출 (UTC 기준)
    1회차:  UTC 00:02 (KST 09:02)
    2회차:  UTC 00:32 (KST 09:32)
    ...
    12회차: UTC 05:32 (KST 14:32)
    """
    now = datetime.now()
    result = {
        'date': str(now.date()),
        'time': now.time().strftime("%H:%M:%S"),
        'round': 0,
        'total_round': 12
    }
    current_total_min = now.hour * 60 + now.minute
    # UTC 00:00 ~ 05:35 범위 내에서 30분 단위 회차 산출
    start_min = 0           # UTC 00:00 (KST 09:00)
    end_min   = 5 * 60 + 35 # UTC 05:35 (KST 14:35) — 마진

    if start_min <= current_total_min <= end_min:
        result['round'] = (current_total_min // 30) + 1
        result['round'] = min(result['round'], 12)
    return result


def split_data(round_num):
    """회차별 분할횟수·가격배율"""
    table = {
        1:  {"sell_splits": 5, "sell_price": [1.025, 1.020, 1.015, 1.010, 1.005],
             "buy_splits":  6, "buy_price":  [0.970, 0.975, 0.980, 0.985, 0.990, 1.000]},
        2:  {"sell_splits": 5, "sell_price": [1.025, 1.020, 1.015, 1.010, 1.000],
             "buy_splits":  5, "buy_price":  [0.975, 0.980, 0.985, 0.990, 0.995]},
        3:  {"sell_splits": 4, "sell_price": [1.020, 1.015, 1.010, 1.005],
             "buy_splits":  5, "buy_price":  [0.975, 0.980, 0.985, 0.990, 1.000]},
        4:  {"sell_splits": 4, "sell_price": [1.020, 1.015, 1.010, 1.000],
             "buy_splits":  4, "buy_price":  [0.980, 0.985, 0.990, 0.995]},
        5:  {"sell_splits": 3, "sell_price": [1.015, 1.010, 1.005],
             "buy_splits":  4, "buy_price":  [0.980, 0.985, 0.990, 1.000]},
        6:  {"sell_splits": 3, "sell_price": [1.015, 1.010, 1.000],
             "buy_splits":  3, "buy_price":  [0.985, 0.990, 0.995]},
        7:  {"sell_splits": 2, "sell_price": [1.010, 1.005],
             "buy_splits":  3, "buy_price":  [0.985, 0.990, 1.000]},
        8:  {"sell_splits": 2, "sell_price": [1.010, 1.000],
             "buy_splits":  2, "buy_price":  [0.990, 0.995]},
        9:  {"sell_splits": 1, "sell_price": [1.005],
             "buy_splits":  2, "buy_price":  [0.990, 1.000]},
        10: {"sell_splits": 1, "sell_price": [1.000],
             "buy_splits":  1, "buy_price":  [0.995]},
        11: {"sell_splits": 1, "sell_price": [0.980],
             "buy_splits":  1, "buy_price":  [1.000]},
        12: {"sell_splits": 0, "sell_price": [],
             "buy_splits":  1, "buy_price":  [1.020]},
    }
    if round_num not in table:
        raise ValueError(f"유효하지 않은 회차: {round_num}")
    return table[round_num]


def cancel_orders(side="all"):
    summary = KIS.cancel_all_KR_unfilled_orders(side)
    if isinstance(summary, dict):
        return f"PEAK: {summary['success']}/{summary['total']} 주문 취소"
    return "PEAK: 주문 취소 에러"


# ================================================================
# 1회차 전용: 크롤링 → 매매대상 산출 → peak_target.json 저장
# ================================================================
def do_crawl_and_build_target(message: list) -> dict:
    """크롤링 후 target dict를 생성·저장하고 반환"""
    message.append(f"PEAK 크롤링 시작 ({datetime.now().strftime('%H:%M:%S')} UTC)")

    try:
        crawl = crawl_peak_strategy()
    except Exception as e:
        TA.send_tele(f"PEAK: 크롤링 실패 - {e}")
        sys.exit(1)

    new_entries  = crawl["buy_list"]
    exits        = crawl["sell_list"]
    all_holdings = crawl["holdings"]
    message.append(f"기준일: {crawl['target_date']} | 진입: {len(new_entries)} | 이탈: {len(exits)} | 사이트보유: {len(all_holdings)}")

    # 기존 peak_data.json (내 실제 보유이력)
    peak_data    = load_json(PEAK_DATA_PATH)
    my_holdings  = peak_data.get("holdings", {})
    cur_hold_cnt = len(my_holdings)

    # 매도 = 이탈 종목 중 내가 보유한 것
    sell_codes = [ex["stock_code"] for ex in exits if ex["stock_code"] in my_holdings]

    # 매수 = 진입 종목 중 아직 미보유
    buy_codes = [e["stock_code"] for e in new_entries if e["stock_code"] not in my_holdings]

    # 보유 상한 초과 체크
    expected = cur_hold_cnt - len(sell_codes) + len(buy_codes)
    if expected > MAX_HOLDINGS:
        overflow = expected - MAX_HOLDINGS
        remaining = {c: info for c, info in my_holdings.items()
                     if c not in sell_codes and c not in buy_codes}
        sorted_rem = sorted(remaining.items(), key=lambda x: x[1].get("return_rate", 0))
        extra = [sorted_rem[i][0] for i in range(min(overflow, len(sorted_rem)))]
        sell_codes.extend(extra)
        message.append(f"⚠️ 보유초과 {overflow}종목 추가매도: {[my_holdings[c].get('name','') for c in extra]}")

    # 계좌 조회 → 종목당 투자금
    account = KIS.get_KR_account_summary()
    if not isinstance(account, dict):
        TA.send_tele(f"PEAK: 계좌요약 조회 불가 ({account})")
        sys.exit(1)
    total_asset = account['total_krw_asset']
    per_stock_invest = int(total_asset / MAX_HOLDINGS) if len(buy_codes) > 0 else 0
    message.append(f"총자산: {int(total_asset):,}원 | 종목당: {per_stock_invest:,}원")

    # 매수 종목별 목표수량
    buy_targets = {}
    for code in buy_codes:
        price = KIS.get_KR_current_price(code)
        if not isinstance(price, int) or price == 0:
            message.append(f"PEAK: {code} 현재가 조회 실패, 매수 스킵")
            continue
        tgt_qty = per_stock_invest // price
        if tgt_qty > 0:
            name = ""
            for e in new_entries:
                if e["stock_code"] == code:
                    name = e["stock_name"]
                    break
            buy_targets[code] = {"target_qty": tgt_qty, "name": name}
        time_module.sleep(0.125)

    # 매도 종목별 보유수량 (실제 잔고)
    sell_targets = {}
    stocks = KIS.get_KR_stock_balance()
    if isinstance(stocks, list):
        hold_map = {s["종목코드"]: s["보유수량"] for s in stocks}
        for code in sell_codes:
            qty = hold_map.get(code, 0)
            if qty > 0:
                sell_targets[code] = {
                    "target_qty": qty,
                    "name": my_holdings.get(code, {}).get("name", code),
                }

    # target 저장
    target = {
        "date":              str(datetime.now().date()),
        "crawl_date":        crawl["target_date"],
        "sell_codes":        sell_codes,
        "buy_codes":         buy_codes,
        "buy_targets":       buy_targets,
        "sell_targets":      sell_targets,
        "per_stock_invest":  per_stock_invest,
        "current_hold_count": cur_hold_cnt,
        "expected_after":    cur_hold_cnt - len(sell_codes) + len(buy_codes),
    }
    save_json(target, PEAK_TARGET_PATH)

    for code, info in buy_targets.items():
        message.append(f"  매수목표: {info['name']}({code}) {info['target_qty']}주")
    for code, info in sell_targets.items():
        message.append(f"  매도목표: {info['name']}({code}) {info['target_qty']}주")

    if not buy_targets and not sell_targets:
        TA.send_tele(message + ["PEAK: 오늘 매매 대상 없음. 종료."])
        sys.exit(0)

    return target


# ================================================================
# 12회차 완료 후: 결산 → peak_data.json 저장
# ================================================================
def do_daily_settlement():
    """12회차 매매 종료 후 10분 대기 → 미체결 취소 → 잔고 저장 → Telegram 리포트"""
    message = []
    message.append("PEAK: 12회차 완료, 10분 대기 후 결산...")
    TA.send_tele(message)
    message = []

    time_module.sleep(600)  # 10분 대기

    # 미체결 전량 취소
    cancel_msg = cancel_orders(side='all')
    message.append(cancel_msg)

    today = str(datetime.now().date())

    # 잔고 조회
    stocks = KIS.get_KR_stock_balance()
    if not isinstance(stocks, list):
        TA.send_tele(f"PEAK결산: 잔고 조회 실패 ({stocks})")
        sys.exit(1)

    account = KIS.get_KR_account_summary()
    if not isinstance(account, dict):
        TA.send_tele(f"PEAK결산: 계좌요약 실패 ({account})")
        sys.exit(1)

    total_asset  = account['total_krw_asset']
    cash_balance = account['cash_balance']
    stock_eval   = account['stock_eval_amt']

    # 이전 peak_data (보유이력 유지용)
    prev_data     = load_json(PEAK_DATA_PATH)
    prev_holdings = prev_data.get("holdings", {})

    # 오늘 target (이탈 코드 참조)
    target     = load_json(PEAK_TARGET_PATH)
    sell_codes = target.get("sell_codes", [])

    # 현재 보유종목 정리
    new_holdings = {}
    for s in stocks:
        code = s["종목코드"]
        qty  = s["보유수량"]
        if qty <= 0:
            continue

        if code in prev_holdings:
            buy_date = prev_holdings[code].get("buy_date", today)
            try:
                bd = datetime.strptime(buy_date, "%Y-%m-%d")
                holding_days = (datetime.now() - bd).days
            except:
                holding_days = prev_holdings[code].get("holding_days", 0) + 1
        else:
            buy_date = today
            holding_days = 0

        buy_price_avg = s["매입단가"]
        current_price = s["현재가"]
        return_rate = round((current_price - buy_price_avg) / buy_price_avg * 100, 2) if buy_price_avg > 0 else 0.0

        new_holdings[code] = {
            "name":          s["종목명"],
            "qty":           qty,
            "buy_date":      buy_date,
            "holding_days":  holding_days,
            "buy_price":     buy_price_avg,
            "current_price": current_price,
            "eval_amt":      s["평가금액"],
            "return_rate":   return_rate,
        }

    # 이탈 종목 기록
    exits_today = []
    for code in sell_codes:
        if code in prev_holdings and code not in new_holdings:
            prev = prev_holdings[code]
            exits_today.append({
                "stock_code":  code,
                "name":        prev.get("name", ""),
                "buy_date":    prev.get("buy_date", ""),
                "sell_date":   today,
                "qty":         prev.get("qty", 0),
                "buy_price":   prev.get("buy_price", 0),
                "return_rate": prev.get("return_rate", 0),
            })

    # 월/연 수익률 (히스토리 기반)
    month_return, year_return = 0.0, 0.0
    this_month = datetime.now().strftime("%Y-%m")
    this_year  = datetime.now().strftime("%Y")
    month_start_asset, year_start_asset = None, None

    history_files = sorted([f for f in os.listdir(PEAK_HISTORY_DIR) if f.endswith('.json')])
    for hf in history_files:
        try:
            with open(os.path.join(PEAK_HISTORY_DIR, hf), 'r') as f:
                hdata = json.load(f)
            hdate  = hdata.get("total", {}).get("date", "")
            hasset = hdata.get("total", {}).get("total_balance", 0)
            if hdate.startswith(this_month) and month_start_asset is None:
                month_start_asset = hasset
            if hdate.startswith(this_year) and year_start_asset is None:
                year_start_asset = hasset
        except:
            continue

    if month_start_asset and month_start_asset > 0:
        month_return = round((total_asset - month_start_asset) / month_start_asset * 100, 2)
    if year_start_asset and year_start_asset > 0:
        year_return = round((total_asset - year_start_asset) / year_start_asset * 100, 2)

    # peak_data.json 저장
    peak_data = {
        "total": {
            "date":           today,
            "total_balance":  total_asset,
            "cash_balance":   cash_balance,
            "stock_eval_amt": stock_eval,
            "holdings_count": len(new_holdings),
            "month_return":   month_return,
            "year_return":    year_return,
        },
        "holdings":    new_holdings,
        "exits_today": exits_today,
    }
    save_json(peak_data, PEAK_DATA_PATH)
    save_json(peak_data, os.path.join(PEAK_HISTORY_DIR, f"peak_{today}.json"))

    # Telegram 리포트
    message.append(
        f"📊 PEAK 일일결산 {today}\n"
        f"💰 총자산: {int(total_asset):,}원\n"
        f"   주식: {int(stock_eval):,}원 | 현금: {int(cash_balance):,}원\n"
        f"   보유: {len(new_holdings)}종목 | 월수익: {month_return:+.2f}% | 연수익: {year_return:+.2f}%"
    )

    if new_holdings:
        message.append("\n📋 보유종목:")
        for code, info in sorted(new_holdings.items(), key=lambda x: x[1]["return_rate"], reverse=True):
            days_str = f"{info['holding_days']}일" if info['holding_days'] > 0 else "진입"
            message.append(
                f"  {info['name']}({code}) {info['qty']}주 "
                f"매입:{info['buy_price']:,.0f} 현재:{info['current_price']:,} "
                f"수익:{info['return_rate']:+.2f}% ({days_str})"
            )

    if exits_today:
        message.append("\n🔴 이탈종목:")
        for ex in exits_today:
            message.append(
                f"  {ex['name']}({ex['stock_code']}) {ex['qty']}주 "
                f"매입:{ex['buy_price']:,.0f} 수익:{ex['return_rate']:+.2f}% "
                f"({ex['buy_date']}→{ex['sell_date']})"
            )

    message.append("✅ peak_data.json 저장 완료")
    TA.send_tele(message)


# ================================================================
# 매매 실행 (매 회차 공통)
# ================================================================
def do_trade(order: dict, target: dict):
    """매도 → 10분 대기 → 매수"""
    message = []
    sell_targets = target.get("sell_targets", {})
    buy_targets  = target.get("buy_targets", {})

    # 분할 데이터
    try:
        rs = split_data(order['round'])
    except ValueError as e:
        TA.send_tele(f"PEAK: {e}")
        sys.exit(1)
    sell_split = [rs["sell_splits"], rs["sell_price"]]
    buy_split  = [rs["buy_splits"],  rs["buy_price"]]

    # 현재 잔고 (매도가능수량)
    current_stocks = KIS.get_KR_stock_balance()
    current_hold = {}
    if isinstance(current_stocks, list):
        for s in current_stocks:
            current_hold[s["종목코드"]] = s["매도가능수량"]

    # ────────────── 매도 ──────────────
    sell = {code: current_hold.get(code, 0) for code in sell_targets if current_hold.get(code, 0) > 0}

    if len(sell) == 0:
        message.append("PEAK: 매도 종목 없음")
    elif sell_split[0] > 0:
        message.append(f"PEAK: {order['round']}회차 - 매도 주문")
        for code, qty in sell.items():
            lsc = sell_split[0]
            lsp = sell_split[1][:]
            sq  = int(qty // lsc)
            rem = int(qty - sq * lsc)

            if sq < 1:
                lsc, lsp, sq, rem = 1, [0.99], int(qty), 0

            price = KIS.get_KR_current_price(code)
            if not isinstance(price, int) or price == 0:
                message.append(f"PEAK: {code} 현재가 불가, 매도 스킵")
                continue

            name = sell_targets.get(code, {}).get("name", code)
            for i in range(lsc):
                tq = sq + (rem if i == lsc - 1 else 0)
                if tq < 1:
                    continue
                op = KIS.round_to_tick(price * lsp[i], "KR")
                oi = KIS.order_sell_KR(code, tq, op, "00")
                if oi is None:
                    message.append(f"매도오류: {name}({code}) API 응답없음")
                elif oi.get("success"):
                    message.append(f"매도 {name} {tq}주 {op:,}원 #{oi.get('order_number','')}")
                else:
                    message.append(f"매도실패 {name}: {oi.get('error_message','')}")
                time_module.sleep(0.125)
    else:
        message.append(f"PEAK: {order['round']}회차 - 매도 분할횟수 0")

    TA.send_tele(message)
    message = []

    # 매도→매수 딜레이 10분
    time_module.sleep(600)

    # ────────────── 매수 ──────────────
    KRW = KIS.get_KR_orderable_cash()
    if not isinstance(KRW, (int, float)):
        TA.send_tele(f"PEAK: 주문가능현금 조회 불가 ({KRW})")
        sys.exit(1)
    orderable_KRW = float(KRW)

    # 잔고 재조회 → 이미 체결된 수량 차감
    refreshed = KIS.get_KR_stock_balance()
    hold_qty_map = {}
    if isinstance(refreshed, list):
        hold_qty_map = {s["종목코드"]: s["보유수량"] for s in refreshed}

    buy, buy_prices = {}, {}
    for code, info in buy_targets.items():
        held = hold_qty_map.get(code, 0)
        remaining = info["target_qty"] - held
        if remaining > 0:
            buy[code] = remaining

    # 현재가 + 매수총액 산출
    target_KRW = 0
    buy_rate = buy_split[1][-1] if buy_split[1] else 1.0
    for code, qty in buy.items():
        p = KIS.get_KR_current_price(code)
        if not isinstance(p, int) or p == 0:
            message.append(f"PEAK: {code} 현재가 불가, 매수 스킵")
            buy[code] = 0
            continue
        buy_prices[code] = p
        target_KRW += p * buy_rate * qty
        time_module.sleep(0.125)

    buy = {k: v for k, v in buy.items() if v > 0}

    message.append(
        f"PEAK 매수가능: {int(orderable_KRW):,}원 | 목표매수금: {int(target_KRW):,}원"
        + (f" | 조정비율: {orderable_KRW/target_KRW:.4f}" if target_KRW > 0 else "")
    )

    if target_KRW > orderable_KRW and target_KRW > 0:
        adj = orderable_KRW / target_KRW
        for code in buy:
            buy[code] = int(buy[code] * adj)
        buy = {k: v for k, v in buy.items() if v > 0}
        message.append(f"PEAK 매수수량 조정 (adjust_rate={adj:.4f})")
    else:
        message.append("PEAK 매수가능금 충분")

    if len(buy) == 0:
        message.append("PEAK: 매수 종목 없음")
    elif buy_split[0] > 0:
        message.append(f"PEAK: {order['round']}회차 - 매수 주문")
        for code, qty in buy.items():
            lsc = buy_split[0]
            lsp = buy_split[1][:]
            sq  = int(qty // lsc)
            rem = int(qty - sq * lsc)

            if sq < 1:
                if qty < 1:
                    continue
                lsc, lsp, sq, rem = 1, [1.01], int(qty), 0

            price = buy_prices.get(code)
            if not isinstance(price, int) or price == 0:
                continue

            name = buy_targets.get(code, {}).get("name", code)
            for i in range(lsc):
                tq = sq + (rem if i == lsc - 1 else 0)
                if tq < 1:
                    continue
                op = KIS.round_to_tick(price * lsp[i], "KR")
                oi = KIS.order_buy_KR(code, tq, op, "00")
                if oi is None:
                    time_module.sleep(2)
                    oi = KIS.order_buy_KR(code, tq, op, "00")
                if oi is None:
                    message.append(f"매수오류: {name}({code}) API 응답없음")
                elif oi.get("success"):
                    message.append(f"매수 {name} {tq}주 {op:,}원 #{oi.get('order_number','')}")
                else:
                    message.append(f"매수실패 {name}: {oi.get('error_message','')}")
                time_module.sleep(0.125)

    TA.send_tele(message)


# ================================================================
# 메인
# ================================================================
health_check()
message = []

order = order_time()
if order['round'] == 0:
    TA.send_tele("PEAK: 매매시간이 아닙니다.")
    sys.exit(0)

message.append(f"PEAK: {order['date']} {order['time']} {order['round']}/{order['total_round']}회차")

# 전회 미체결 취소
cancel_msg = cancel_orders(side='all')
message.append(cancel_msg)

# ── 1회차: 크롤링 + target 생성 + 5분 대기 ──
if order['round'] == 1:
    target = do_crawl_and_build_target(message)
    TA.send_tele(message)
    message = []

    TA.send_tele("PEAK: 크롤링 완료, 5분 대기 후 매매 시작...")
    time_module.sleep(300)   # 5분 대기

# ── 2~12회차: target 로드 ──
else:
    target = load_json(PEAK_TARGET_PATH)
    if not target:
        TA.send_tele("PEAK: peak_target.json 없음. 1회차 미실행?")
        sys.exit(1)
    TA.send_tele(message)
    message = []

# ── 매매 실행 ──
do_trade(order, target)

# ── 12회차 후 결산 ──
if order['round'] == 12:
    do_daily_settlement()

sys.exit(0)
