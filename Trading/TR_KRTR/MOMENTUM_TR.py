#!/usr/bin/env python3
"""
StockEasy Momentum 전략 자동매매 (단일 파일 통합)

실행 흐름:
  1회차 (KST 09:00 = UTC 00:00):
    → 크롤링 → buy/sell 리스트 산출 → momentum_target.json 저장
    → 5분 대기 → 매도 → 10분 대기 → 매수
  2~12회차 (KST 09:30~14:30 = UTC 00:30~05:30, 30분 간격):
    → momentum_target.json 로드 → 매도 → 10분 대기 → 매수
  12회차 매매 완료 후:
    → 10분 대기 → 미체결 전량취소 → 잔고조회 → momentum_data.json 저장 + Telegram 리포트

crontab (UTC+0, EC2):
  6,36 0-5 * * 1-5 timeout -s 9 1500 /usr/bin/python3 /var/autobot/TR_KRTR/MOMENTUM_TR.py

보유 상한: 28종목, 종목당 균등배분 (총자산 / 28)
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
    TA.send_tele("MOMENTUM: 이미 실행 중입니다.")
    sys.exit(0)

import KIS_KR

# ================================================================
# 설정
# ================================================================
key_file_path   = "/var/autobot/KIS/kis44287475nkr.txt"        # MOMENTUM
token_file_path = "/var/autobot/KIS/kis44287475_token.json"  # MOMENTUM
cano            = "44287475"   # MOMENTUM
acnt_prdt_cd    = "01"

KIS = KIS_KR.KIS_API(key_file_path, token_file_path, cano, acnt_prdt_cd)

# 파일 경로
BASE_DIR          = "/var/autobot/TR_KRTR"
MOMENTUM_DATA_PATH    = os.path.join(BASE_DIR, "momentum_data.json")
MOMENTUM_TARGET_PATH  = os.path.join(BASE_DIR, "momentum_target.json")
MOMENTUM_HISTORY_DIR  = os.path.join(BASE_DIR, "MOMENTUM_history")

os.makedirs(MOMENTUM_HISTORY_DIR, exist_ok=True)
OVERRIDE_PATH = os.path.join(BASE_DIR, "momentum_override.json") # 수동 개입 경로
MAX_HOLDINGS = 28   # 최대 보유 종목 수


# ================================================================
# StockEasy 크롤링
# ================================================================
CRAWL_URL = "https://stockeasy.intellio.kr/strategy-room/momentum"
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
    """Next.js SSR __next_f.push 안의 initialData JSON 추출
    
    ※ 정규식 greedy 매칭은 중첩 {} 에서 범위를 잘못 잡음
       → 중괄호 깊이 추적(brace matching)으로 정확한 JSON 범위 추출
    """
    scripts = re.findall(r'self\.__next_f\.push\(\[1,"(.+?)"\]\)', html, re.DOTALL)
    for s in scripts:
        if 'initialData' not in s:
            continue
        try:
            decoded = json.loads('"' + s + '"')
        except Exception:
            continue
 
        marker = '"initialData":'
        idx = decoded.find(marker)
        if idx == -1:
            continue
 
        start = idx + len(marker)
        # 중괄호 깊이 추적으로 JSON 객체 끝 위치 찾기
        depth = 0
        end_pos = start
        for j in range(start, len(decoded)):
            if decoded[j] == '{':
                depth += 1
            elif decoded[j] == '}':
                depth -= 1
                if depth == 0:
                    end_pos = j + 1
                    break
 
        try:
            return json.loads(decoded[start:end_pos])
        except json.JSONDecodeError:
            continue
    return {}

def crawl_momentum_strategy() -> dict:
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
        TA.send_tele(f"MOMENTUM: {path} 저장 실패: {e}")
        backup = os.path.join(BASE_DIR, f"backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json")
        with open(backup, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
        TA.send_tele(f"MOMENTUM: 백업 저장: {backup}")


def health_check():
    checks = []
    if not KIS.access_token:
        checks.append("MOMENTUM체크: API 토큰 없음")
    try:
        import socket
        socket.create_connection(("openapi.koreainvestment.com", 9443), timeout=5)
    except:
        checks.append("MOMENTUM체크: KIS API 서버 접속 불가")
    if not KIS.is_KR_trading_day():
        checks.append("MOMENTUM체크: 거래일이 아닙니다.")
    if checks:
        TA.send_tele(checks)
        sys.exit(0)


def order_time():
    """
    거래회차 산출 (UTC 기준)
    1회차:  UTC 00:06 (KST 09:06)
    2회차:  UTC 00:36 (KST 09:36)
    ...
    12회차: UTC 05:36 (KST 14:36)
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
    end_min   = 5 * 60 + 40 # UTC 05:40 (KST 14:40) — 마진

    if start_min <= current_total_min <= end_min:
        result['round'] = (current_total_min // 30) + 1
        result['round'] = min(result['round'], 12)
    return result


def split_data(round_num):
    """회차별 분할횟수·가격배율"""
    table = {
        1:  {"sell_splits": 5, "sell_price": [1.0125, 1.0100, 1.0075, 1.0050, 1.0025],
             "buy_splits":  6, "buy_price":  [0.9850, 0.9875, 0.9900, 0.9925, 0.9950, 1.0000]},
        2:  {"sell_splits": 5, "sell_price": [1.0125, 1.0100, 1.0075, 1.0050, 1.0000],
             "buy_splits":  5, "buy_price":  [0.9875, 0.9900, 0.9925, 0.9950, 0.9975]},
        3:  {"sell_splits": 4, "sell_price": [1.0100, 1.0075, 1.0050, 1.0025],
             "buy_splits":  5, "buy_price":  [0.9875, 0.9900, 0.9925, 0.9950, 1.0000]},
        4:  {"sell_splits": 4, "sell_price": [1.0100, 1.0075, 1.0050, 1.0000],
             "buy_splits":  4, "buy_price":  [0.9900, 0.9925, 0.9950, 0.9975]},
        5:  {"sell_splits": 3, "sell_price": [1.0075, 1.0050, 1.0025],
             "buy_splits":  4, "buy_price":  [0.9900, 0.9925, 0.9950, 1.0000]},
        6:  {"sell_splits": 3, "sell_price": [1.0075, 1.0050, 1.0000],
             "buy_splits":  3, "buy_price":  [0.9925, 0.9950, 0.9975]},
        7:  {"sell_splits": 2, "sell_price": [1.0050, 1.0025],
             "buy_splits":  3, "buy_price":  [0.9925, 0.9950, 1.0000]},
        8:  {"sell_splits": 2, "sell_price": [1.0050, 1.0000],
             "buy_splits":  2, "buy_price":  [0.9950, 0.9975]},
        9:  {"sell_splits": 1, "sell_price": [1.0025],
             "buy_splits":  2, "buy_price":  [0.9950, 1.0000]},
        10: {"sell_splits": 1, "sell_price": [1.0000],
             "buy_splits":  1, "buy_price":  [0.9975]},
        11: {"sell_splits": 1, "sell_price": [0.9800],
             "buy_splits":  1, "buy_price":  [1.0000]},
        12: {"sell_splits": 0, "sell_price": [],
             "buy_splits":  1, "buy_price":  [1.0200]},
    }
    if round_num not in table:
        raise ValueError(f"유효하지 않은 회차: {round_num}")
    return table[round_num]


def cancel_orders(side="all"):
    summary = KIS.cancel_all_KR_unfilled_orders(side)
    if isinstance(summary, dict):
        return f"MOMENTUM: {summary['success']}/{summary['total']} 주문 취소"
    return "MOMENTUM: 주문 취소 에러"


def load_today_override() -> dict:
    """override JSON에서 오늘 날짜 엔트리만 추출.
    없거나 오늘 날짜 아니면 {} 반환."""
    if not os.path.exists(OVERRIDE_PATH):
        return {}
    try:
        with open(OVERRIDE_PATH, 'r', encoding='utf-8') as f:
            raw = json.load(f)
    except Exception as e:
        TA.send_tele(f"Override JSON 로드 실패: {e}")
        return {}

    today = str(datetime.now().date())
    for entry in raw.get("overrides", []):
        if entry.get("date") == today:
            return entry
    return {}


def apply_manual_override(target: dict, message: list,
                          per_stock_invest: int) -> dict:
    """
    1회차 전용: 크롤링으로 생성된 target에 수동 개입 적용.
    
    규칙:
      - sell_all=True  : 크롤링 buy/sell 전량 무시 + 계좌 보유 전량 매도
      - force_sell     : 항상 보유 전량 매도, 크롤링 buy_targets에서 제거(충돌 시)
      - force_buy      : per_stock_invest로 수량 산출, 크롤링 sell_targets에서 제거(충돌 시)
    
    target dict를 in-place 수정 + 반환.
    """
    ov = load_today_override()
    if not ov:
        return target

    memo = ov.get("memo", "")
    message.append(f"🔧 수동개입 감지: {ov.get('date','')} ({memo})")

    # 실제 계좌 보유 (전량매도/force_sell 수량 산출용)
    stocks = KIS.get_KR_stock_balance()
    hold_map = {}
    if isinstance(stocks, list):
        hold_map = {s["종목코드"]: (s["보유수량"], s.get("종목명", s["종목코드"]))
                    for s in stocks}

    # ─── sell_all: 크롤링 결과 전량 무시 + 계좌 보유 전량 매도 ───
    if ov.get("sell_all") is True:
        target["buy_targets"]  = {}
        target["sell_targets"] = {
            code: {"target_qty": qty, "name": name}
            for code, (qty, name) in hold_map.items() if qty > 0
        }
        target["sell_codes"] = list(target["sell_targets"].keys())
        target["buy_codes"]  = []
        target["override"]   = {"sell_all": True, "memo": memo}
        message.append(f"🔴 전량청산: 크롤링 결과 무시, 보유 {len(target['sell_targets'])}종목 매도")
        return target

    force_buy  = ov.get("force_buy", [])  or []
    force_sell = ov.get("force_sell", []) or []

    # ─── force_sell: 보유 전량 매도 ───
    for item in force_sell:
        code = str(item.get("stock_code", "")).zfill(6)
        name = item.get("stock_name", code)
        if code not in hold_map or hold_map[code][0] <= 0:
            message.append(f"  ⚠️ force_sell 스킵(미보유): {name}({code})")
            continue
        qty = hold_map[code][0]
        target["sell_targets"][code] = {"target_qty": qty, "name": name}
        # 충돌: 크롤링 buy와 동일 종목이면 buy에서 제거
        if code in target["buy_targets"]:
            del target["buy_targets"][code]
            message.append(f"  ⚠️ 충돌해소: {name}({code}) 크롤링매수→수동매도 우선")
        if code not in target["sell_codes"]:
            target["sell_codes"].append(code)
        message.append(f"  🔴 force_sell: {name}({code}) {qty}주 전량")

    # ─── force_buy: per_stock_invest로 수량 산출 ───
    for item in force_buy:
        code = str(item.get("stock_code", "")).zfill(6)
        name = item.get("stock_name", code)

        if per_stock_invest <= 0:
            message.append(f"  ⚠️ force_buy 스킵(per_stock_invest=0): {name}({code})")
            continue

        price = KIS.get_KR_current_price(code)
        if not isinstance(price, int) or price == 0:
            message.append(f"  ⚠️ force_buy 스킵(현재가 실패): {name}({code})")
            continue

        tgt_qty = per_stock_invest // price
        if tgt_qty < 1:
            message.append(f"  ⚠️ force_buy 스킵(수량<1): {name}({code}) 현재가 {price:,}")
            continue

        target["buy_targets"][code] = {"target_qty": tgt_qty, "name": name}
        # 충돌: 크롤링 sell과 동일 종목이면 sell에서 제거
        if code in target["sell_targets"]:
            del target["sell_targets"][code]
            message.append(f"  ⚠️ 충돌해소: {name}({code}) 크롤링매도→수동매수 우선")
        if code in target["sell_codes"]:
            target["sell_codes"].remove(code)
        if code not in target["buy_codes"]:
            target["buy_codes"].append(code)
        message.append(f"  🟢 force_buy: {name}({code}) {tgt_qty}주 ({price*tgt_qty:,}원)")
        time_module.sleep(0.125)

    target["override"] = {
        "sell_all":   False,
        "force_buy":  [i.get("stock_code") for i in force_buy],
        "force_sell": [i.get("stock_code") for i in force_sell],
        "memo":       memo,
    }
    return target


# ================================================================
# 1회차 전용: 크롤링 → 매매대상 산출 → momentum_target.json 저장
# ================================================================
def do_crawl_and_build_target(message: list) -> dict:
    """크롤링 후 target dict를 생성·저장하고 반환"""
    message.append(f"MOMENTUM 크롤링 시작 ({datetime.now().strftime('%H:%M:%S')} UTC)")

    try:
        crawl = crawl_momentum_strategy()
    except Exception as e:
        TA.send_tele(f"MOMENTUM: 크롤링 실패 - {e}")
        sys.exit(1)

    new_entries  = crawl["buy_list"]
    exits        = crawl["sell_list"]
    all_holdings = crawl["holdings"]
    message.append(f"기준일: {crawl['target_date']} | 진입: {len(new_entries)} | 이탈: {len(exits)} | 사이트보유: {len(all_holdings)}")

    # 기존 momentum_data.json (내 실제 보유이력)
    momentum_data    = load_json(MOMENTUM_DATA_PATH)
    my_holdings  = momentum_data.get("holdings", {})
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
        TA.send_tele(f"MOMENTUM: 계좌요약 조회 불가 ({account})")
        sys.exit(1)
    total_asset = account['total_krw_asset']
    per_stock_invest = int(total_asset / MAX_HOLDINGS)
    message.append(f"총자산: {int(total_asset):,}원 | 종목당: {per_stock_invest:,}원")

    # 매수 종목별 목표수량
    buy_targets = {}
    for code in buy_codes:
        price = KIS.get_KR_current_price(code)
        if not isinstance(price, int) or price == 0:
            message.append(f"MOMENTUM: {code} 현재가 조회 실패, 매수 스킵")
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
    # ▼ 추가: 수동 개입 적용
    target = apply_manual_override(target, message, per_stock_invest)
    save_json(target, MOMENTUM_TARGET_PATH)

    for code, info in target["buy_targets"].items():
        message.append(f"  매수목표: {info['name']}({code}) {info['target_qty']}주")
    for code, info in target["sell_targets"].items():
        message.append(f"  매도목표: {info['name']}({code}) {info['target_qty']}주")

    if not target["buy_targets"] and not target["sell_targets"]:
        TA.send_tele(message + ["MOMENTUM: 오늘 매매 대상 없음. 종료."])
        sys.exit(0)

    return target


# ================================================================
# 12회차 완료 후: 결산 → momentum_data.json 저장
# ================================================================
def do_daily_settlement():
    """12회차 매매 종료 후 10분 대기 → 미체결 취소 → 잔고 저장 → Telegram 리포트"""
    # message = []
    # message.append("MOMENTUM: 12회차 완료, 10분 대기 후 결산...")
    # TA.send_tele(message)
    message = []

    time_module.sleep(600)  # 10분 대기

    # 미체결 전량 취소
    cancel_msg = cancel_orders(side='all')
    message.append(cancel_msg)

    today = str(datetime.now().date())

    # 잔고 조회
    stocks = KIS.get_KR_stock_balance()
    if not isinstance(stocks, list):
        TA.send_tele(f"MOMENTUM결산: 잔고 조회 실패 ({stocks})")
        sys.exit(1)

    account = KIS.get_KR_account_summary()
    if not isinstance(account, dict):
        TA.send_tele(f"MOMENTUM결산: 계좌요약 실패 ({account})")
        sys.exit(1)

    total_asset  = account['total_krw_asset']
    cash_balance = account['cash_balance']
    stock_eval   = account['stock_eval_amt']

    # 이전 momentum_data (보유이력 유지용)
    prev_data     = load_json(MOMENTUM_DATA_PATH)
    prev_holdings = prev_data.get("holdings", {})

    # 오늘 target (이탈 코드 참조)
    target     = load_json(MOMENTUM_TARGET_PATH)
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

    history_files = sorted([f for f in os.listdir(MOMENTUM_HISTORY_DIR) if f.endswith('.json')])
    for hf in history_files:
        try:
            with open(os.path.join(MOMENTUM_HISTORY_DIR, hf), 'r') as f:
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

    # momentum_data.json 저장
    momentum_data = {
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
    save_json(momentum_data, MOMENTUM_DATA_PATH)
    save_json(momentum_data, os.path.join(MOMENTUM_HISTORY_DIR, f"momentum_{today}.json"))

    # Telegram 리포트
    message.append(
        f"📊 MOMENTUM 일일결산 {today}\n"
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

    message.append("✅ momentum_data.json 저장 완료")
    TA.send_tele(message)


# ================================================================
# 매매 실행 (매 회차 공통)
# ================================================================
def do_trade(order: dict, target: dict, message: list):
    """매도 → 10분 대기 → 매수"""
    # message = []
    sell_targets = target.get("sell_targets", {})
    buy_targets  = target.get("buy_targets", {})

    # 분할 데이터
    try:
        rs = split_data(order['round'])
    except ValueError as e:
        TA.send_tele(f"MOMENTUM: {e}")
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
        message.append("MOMENTUM: 매도 종목 없음")
    elif sell_split[0] > 0:
        message.append(f"MOMENTUM: {order['round']}회차 - 매도 주문")
        for code, qty in sell.items():
            lsc = sell_split[0]
            lsp = sell_split[1][:]
            sq  = int(qty // lsc)
            rem = int(qty - sq * lsc)

            if sq < 1:
                lsc, lsp, sq, rem = 1, [0.99], int(qty), 0

            price = KIS.get_KR_current_price(code)
            if not isinstance(price, int) or price == 0:
                message.append(f"MOMENTUM: {code} 현재가 불가, 매도 스킵")
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
        message.append(f"MOMENTUM: {order['round']}회차 - 매도 분할횟수 0")

    TA.send_tele(message)
    message = []

    # 매도→매수 딜레이 10분
    time_module.sleep(600)

    # ────────────── 매수 ──────────────
    KRW = KIS.get_KR_orderable_cash()
    if not isinstance(KRW, (int, float)):
        TA.send_tele(f"MOMENTUM: 주문가능현금 조회 불가 ({KRW})")
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
            message.append(f"MOMENTUM: {code} 현재가 불가, 매수 스킵")
            buy[code] = 0
            continue
        buy_prices[code] = p
        target_KRW += p * buy_rate * qty
        time_module.sleep(0.125)

    buy = {k: v for k, v in buy.items() if v > 0}

    message.append(
        f"MOMENTUM 매수가능: {int(orderable_KRW):,}원 | 목표매수금: {int(target_KRW):,}원"
        + (f" | 조정비율: {orderable_KRW/target_KRW:.4f}" if target_KRW > 0 else "")
    )

    if target_KRW > orderable_KRW and target_KRW > 0:
        adj = orderable_KRW / target_KRW
        for code in buy:
            buy[code] = int(buy[code] * adj)
        buy = {k: v for k, v in buy.items() if v > 0}
        message.append(f"MOMENTUM 매수수량 조정 (adjust_rate={adj:.4f})")
    else:
        message.append("MOMENTUM 매수가능금 충분")

    if len(buy) == 0:
        message.append("MOMENTUM: 매수 종목 없음")
    elif buy_split[0] > 0:
        message.append(f"MOMENTUM: {order['round']}회차 - 매수 주문")
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
    TA.send_tele("MOMENTUM: 매매시간이 아닙니다.")
    sys.exit(0)

message.append(f"MOMENTUM: {order['date']} {order['time']} {order['round']}/{order['total_round']}회차")

# 전회 미체결 취소
cancel_msg = cancel_orders(side='all')
message.append(cancel_msg)

# ── 1회차: 크롤링 + target 생성 + 3분 대기 ──
if order['round'] == 1:
    target = do_crawl_and_build_target(message)
    message.append("MOMENTUM: 크롤링 완료, 3분 대기 후 매매 시작...")
    # TA.send_tele(message)
    # message = []
    time_module.sleep(180)   # 3분 대기

# ── 2~12회차: target 로드 ──
else:
    target = load_json(MOMENTUM_TARGET_PATH)
    if not target:
        TA.send_tele("MOMENTUM: momentum_target.json 없음. 1회차 미실행?")
        sys.exit(1)
    # TA.send_tele(message)
    # message = []

# ── 매매 실행 ──
do_trade(order, target, message)

# ── 12회차 후 결산 ──
if order['round'] == 12:
    do_daily_settlement()

sys.exit(0)
