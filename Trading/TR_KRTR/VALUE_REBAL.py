#!/usr/bin/env python3
"""
StockEasy Value 전략 - 비중 리밸런싱 (대규모 입/출금 이후 전체 재조정)

기본 TR.py와 차이점:
  - 크롤링 진입/이탈 반영 + 기존 보유종목의 비중 재조정(매수/매도 동시)
  - 목표비중 = 총자산 / MAX_HOLDINGS (균등)
  - 최소 주문 임계: 금액 10만원 이상만 조정 (신규진입/완전이탈은 필터 제외)

실행 흐름 (기존 TR.py와 동일):
  1회차 (KST 09:00 = UTC 00:00):
    → 크롤링 → 리밸런싱 target 산출 → value_target.json 저장
    → 3분 대기 → 매도 → 10분 대기 → 매수
  2~12회차: value_target.json 로드 → 매도 → 10분 대기 → 매수
  12회차 완료: 결산 → value_data.json 저장 + Telegram 리포트

crontab (UTC+0, EC2) - 리밸런싱 날짜만 활성화:
  # 평상시: PEAK_TR.py 실행
  # 0,30 0-5 * * 1-5 timeout -s 9 1500 /usr/bin/python3 /var/autobot/TR_VALUE/PEAK_TR.py
  # 리밸런싱 날 (예: 매월 첫째 월요일): VALUE_REBAL.py 실행
  # 0,30 0-5 1-7 * 1 timeout -s 9 1500 /usr/bin/python3 /var/autobot/TR_VALUE/VALUE_REBAL.py

보유 상한: 10종목, 종목당 균등배분 (총자산 / 10)
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
    TA.send_tele("VALUE_REBAL: 이미 실행 중입니다.")
    sys.exit(0)

import KIS_KR

# ================================================================
# 설정
# ================================================================
key_file_path   = "/var/autobot/KIS/kis44036546nkr.txt"      # VALUE
token_file_path = "/var/autobot/KIS/kis44036546_token.json"  # VALUE
cano            = "44036546"   # VALUE
acnt_prdt_cd    = "01"

KIS = KIS_KR.KIS_API(key_file_path, token_file_path, cano, acnt_prdt_cd)

# 파일 경로 (기존 TR.py와 공유)
BASE_DIR          = "/var/autobot/TR_KRTR"
VALUE_DATA_PATH    = os.path.join(BASE_DIR, "value_data.json")
VALUE_TARGET_PATH  = os.path.join(BASE_DIR, "value_target.json")
VALUE_HISTORY_DIR  = os.path.join(BASE_DIR, "VALUE_history")
OVERRIDE_PATH     = os.path.join(BASE_DIR, "value_override.json")

os.makedirs(VALUE_HISTORY_DIR, exist_ok=True)

MAX_HOLDINGS   = 10        # 최대 보유 종목 수
MIN_ORDER_KRW  = 100_000   # 리밸런싱 최소 주문 임계 (10만원)


# ================================================================
# StockEasy 크롤링 (TR.py와 동일)
# ================================================================
CRAWL_URL = "https://stockeasy.intellio.kr/strategy-room/value"
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

def crawl_value_strategy() -> dict:
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
        TA.send_tele(f"VALUE_REBAL: {path} 저장 실패: {e}")
        backup = os.path.join(BASE_DIR, f"backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json")
        with open(backup, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
        TA.send_tele(f"VALUE_REBAL: 백업 저장: {backup}")


def health_check():
    checks = []
    if not KIS.access_token:
        checks.append("VALUE_REBAL체크: API 토큰 없음")
    try:
        import socket
        socket.create_connection(("openapi.koreainvestment.com", 9443), timeout=5)
    except:
        checks.append("VALUE_REBAL체크: KIS API 서버 접속 불가")
    if not KIS.is_KR_trading_day():
        checks.append("VALUE_REBAL체크: 거래일이 아닙니다.")
    if checks:
        TA.send_tele(checks)
        sys.exit(0)


def order_time():
    now = datetime.now()
    result = {
        'date': str(now.date()),
        'time': now.time().strftime("%H:%M:%S"),
        'round': 0,
        'total_round': 12
    }
    current_total_min = now.hour * 60 + now.minute
    start_min = 0
    end_min   = 5 * 60 + 40

    if start_min <= current_total_min <= end_min:
        result['round'] = (current_total_min // 30) + 1
        result['round'] = min(result['round'], 12)
    return result


def split_data(round_num):
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
        return f"VALUE_REBAL: {summary['success']}/{summary['total']} 주문 취소"
    return "VALUE_REBAL: 주문 취소 에러"


# ================================================================
# 수동 개입 처리 (TR.py와 동일)
# ================================================================
def load_today_override() -> dict:
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
    """리밸런싱 target에 수동 개입 적용 (TR.py와 동일 로직)"""
    ov = load_today_override()
    if not ov:
        return target

    memo = ov.get("memo", "")
    message.append(f"🔧 수동개입 감지: {ov.get('date','')} ({memo})")

    stocks = KIS.get_KR_stock_balance()
    hold_map = {}
    if isinstance(stocks, list):
        hold_map = {s["종목코드"]: (s["보유수량"], s.get("종목명", s["종목코드"]))
                    for s in stocks}

    if ov.get("sell_all") is True:
        target["buy_targets"]  = {}
        target["sell_targets"] = {
            code: {"target_qty": qty, "name": name}
            for code, (qty, name) in hold_map.items() if qty > 0
        }
        target["sell_codes"] = list(target["sell_targets"].keys())
        target["buy_codes"]  = []
        target["override"]   = {"sell_all": True, "memo": memo}
        message.append(f"🔴 전량청산: 크롤링·리밸런싱 결과 무시, 보유 {len(target['sell_targets'])}종목 매도")
        return target

    force_buy  = ov.get("force_buy", [])  or []
    force_sell = ov.get("force_sell", []) or []

    # force_sell: 보유 전량 매도
    for item in force_sell:
        code = str(item.get("stock_code", "")).zfill(6)
        name = item.get("stock_name", code)
        if code not in hold_map or hold_map[code][0] <= 0:
            message.append(f"  ⚠️ force_sell 스킵(미보유): {name}({code})")
            continue
        qty = hold_map[code][0]
        target["sell_targets"][code] = {"target_qty": qty, "name": name}
        if code in target["buy_targets"]:
            del target["buy_targets"][code]
            message.append(f"  ⚠️ 충돌해소: {name}({code}) 리밸매수→수동매도 우선")
        if code not in target["sell_codes"]:
            target["sell_codes"].append(code)
        message.append(f"  🔴 force_sell: {name}({code}) {qty}주 전량")

    # force_buy: per_stock_invest로 수량 산출
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

        # 이미 보유 중이면 부족분만, 아니면 목표수량 전부
        held_qty = hold_map.get(code, (0, ""))[0]
        full_tgt = per_stock_invest // price
        tgt_qty = max(full_tgt - held_qty, full_tgt if held_qty == 0 else 0)
        if tgt_qty < 1:
            message.append(f"  ⚠️ force_buy 스킵(수량<1): {name}({code}) 현재가 {price:,}")
            continue

        target["buy_targets"][code] = {"target_qty": tgt_qty, "name": name}
        if code in target["sell_targets"]:
            del target["sell_targets"][code]
            message.append(f"  ⚠️ 충돌해소: {name}({code}) 리밸매도→수동매수 우선")
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
# 1회차 전용: 크롤링 → 리밸런싱 target 산출
# ================================================================
def do_crawl_and_build_rebal_target(message: list) -> dict:
    """
    리밸런싱 전용 target 생성:
      매수대상 = (기존보유 ∪ 크롤링진입) − 크롤링이탈
      매도대상 = 크롤링이탈 ∪ 초과보유분
      목표수량 = per_stock_invest / 현재가
      주문수량 = 목표수량 − 현재보유수량 (음수면 매도, 양수면 매수)
      필터: |차이금액| ≥ MIN_ORDER_KRW (10만원)
             단, 신규진입/완전이탈은 임계 무시
    """
    message.append(f"VALUE_REBAL 크롤링 시작 ({datetime.now().strftime('%H:%M:%S')} UTC)")

    # 1. 크롤링
    try:
        crawl = crawl_value_strategy()
    except Exception as e:
        TA.send_tele(f"VALUE_REBAL: 크롤링 실패 - {e}")
        sys.exit(1)

    new_entries  = crawl["buy_list"]   # 진입 (holding_days==0)
    exits        = crawl["sell_list"]  # 이탈
    entry_codes  = {e["stock_code"] for e in new_entries}
    exit_codes   = {e["stock_code"] for e in exits}
    crawl_name   = {e["stock_code"]: e["stock_name"] for e in new_entries + exits}

    message.append(
        f"기준일: {crawl['target_date']} | 진입: {len(new_entries)} | 이탈: {len(exits)} | 사이트보유: {len(crawl['holdings'])}"
    )

    # 2. 계좌 잔고 조회
    stocks = KIS.get_KR_stock_balance()
    if not isinstance(stocks, list):
        TA.send_tele(f"VALUE_REBAL: 잔고 조회 실패 ({stocks})")
        sys.exit(1)

    # {code: {"qty":..., "eval":..., "name":..., "current_price":...}}
    my_holdings = {}
    for s in stocks:
        if s["보유수량"] <= 0:
            continue
        my_holdings[s["종목코드"]] = {
            "qty":           s["보유수량"],
            "eval":          s["평가금액"],
            "name":          s["종목명"],
            "current_price": s["현재가"],
        }

    # 3. 계좌 총자산
    account = KIS.get_KR_account_summary()
    if not isinstance(account, dict):
        TA.send_tele(f"VALUE_REBAL: 계좌요약 실패 ({account})")
        sys.exit(1)
    total_asset = account['total_krw_asset']
    per_stock_invest = int(total_asset / MAX_HOLDINGS)
    message.append(f"총자산: {int(total_asset):,}원 | 종목당 목표: {per_stock_invest:,}원")

    # 4. 유지·추가 대상: (기존보유 − 이탈) ∪ 진입
    keep_codes  = set(my_holdings.keys()) - exit_codes
    target_universe = keep_codes | entry_codes   # 리밸런싱 대상 전체

    # 5. 보유상한 초과 체크 (수익률 낮은 종목부터 제외)
    value_data   = load_json(VALUE_DATA_PATH)
    prev_hold   = value_data.get("holdings", {})

    if len(target_universe) > MAX_HOLDINGS:
        overflow = len(target_universe) - MAX_HOLDINGS
        # 진입 종목은 우선 유지 → 기존 유지분 중 수익률 낮은 순
        removable = [c for c in keep_codes if c not in entry_codes]
        removable.sort(key=lambda c: prev_hold.get(c, {}).get("return_rate", 0))
        drop = removable[:overflow]
        for c in drop:
            target_universe.discard(c)
            exit_codes.add(c)  # 이탈 처리로 귀결
        message.append(f"⚠️ 상한초과 {overflow}종목 자동제외: {[my_holdings[c]['name'] for c in drop if c in my_holdings]}")

    # 6. 각 종목별 목표수량/현재수량 비교 → 매수·매도 분류
    buy_targets  = {}
    sell_targets = {}
    sell_codes_list = []
    buy_codes_list  = []

    for code in target_universe:
        # 현재가 조회 (보유 중이면 잔고의 현재가 사용, 아니면 신규 조회)
        if code in my_holdings:
            price = my_holdings[code]["current_price"]
            held_qty = my_holdings[code]["qty"]
            name     = my_holdings[code]["name"]
        else:
            price = KIS.get_KR_current_price(code)
            time_module.sleep(0.125)
            held_qty = 0
            name     = crawl_name.get(code, code)

        if not isinstance(price, int) or price <= 0:
            message.append(f"VALUE_REBAL: {code}({name}) 현재가 불가, 스킵")
            continue

        tgt_qty  = per_stock_invest // price
        diff_qty = tgt_qty - held_qty
        diff_amt = abs(diff_qty * price)

        is_new_entry = (held_qty == 0)

        # 매수 (diff_qty > 0)
        if diff_qty > 0:
            # 신규진입은 임계 무시, 기존보유 추가매수는 임계 적용
            if not is_new_entry and diff_amt < MIN_ORDER_KRW:
                continue  # 조정액 미만이면 스킵
            buy_targets[code] = {"target_qty": diff_qty, "name": name}
            buy_codes_list.append(code)

        # 매도 (diff_qty < 0, 초과보유)
        elif diff_qty < 0:
            if diff_amt < MIN_ORDER_KRW:
                continue  # 초과분 미미하면 스킵
            sell_qty = abs(diff_qty)
            sell_targets[code] = {"target_qty": sell_qty, "name": name}
            sell_codes_list.append(code)

        # diff_qty == 0: 조정 불필요

    # 7. 완전이탈 종목: 보유 전량 매도 (임계 무시)
    for code in exit_codes:
        if code not in my_holdings:
            continue
        qty  = my_holdings[code]["qty"]
        name = my_holdings[code]["name"]
        # 이미 sell_targets에 있으면 전량으로 덮어쓰기 (확실히 전량매도)
        sell_targets[code] = {"target_qty": qty, "name": name}
        if code not in sell_codes_list:
            sell_codes_list.append(code)

    # 8. target 구성
    target = {
        "date":               str(datetime.now().date()),
        "crawl_date":         crawl["target_date"],
        "mode":               "rebalance",
        "sell_codes":         sell_codes_list,
        "buy_codes":          buy_codes_list,
        "buy_targets":        buy_targets,
        "sell_targets":       sell_targets,
        "per_stock_invest":   per_stock_invest,
        "total_asset":        total_asset,
        "current_hold_count": len(my_holdings),
        "target_universe":    sorted(list(target_universe)),
    }

    # 9. 수동 개입 적용
    target = apply_manual_override(target, message, per_stock_invest)
    save_json(target, VALUE_TARGET_PATH)

    # 10. 요약 출력
    total_buy_amt  = sum(info["target_qty"] * (my_holdings.get(c, {}).get("current_price") or KIS.get_KR_current_price(c) or 0)
                         for c, info in target["buy_targets"].items())
    total_sell_amt = sum(info["target_qty"] * my_holdings[c]["current_price"]
                         for c, info in target["sell_targets"].items() if c in my_holdings)

    message.append(f"🔄 리밸런싱 요약: 매수 {len(target['buy_targets'])}종목 (약 {int(total_buy_amt):,}원) | 매도 {len(target['sell_targets'])}종목 (약 {int(total_sell_amt):,}원)")

    for code, info in target["buy_targets"].items():
        held = my_holdings.get(code, {}).get("qty", 0)
        tag  = "🆕진입" if held == 0 else "➕추가"
        message.append(f"  {tag} {info['name']}({code}) +{info['target_qty']}주")
    for code, info in target["sell_targets"].items():
        held = my_holdings.get(code, {}).get("qty", 0)
        tag  = "🔴이탈" if info['target_qty'] >= held else "➖축소"
        message.append(f"  {tag} {info['name']}({code}) -{info['target_qty']}주")

    if not target["buy_targets"] and not target["sell_targets"]:
        TA.send_tele(message + ["VALUE_REBAL: 조정 불필요 (임계 미만). 종료."])
        sys.exit(0)

    return target


# ================================================================
# 12회차 완료 후: 결산 (TR.py와 동일)
# ================================================================
def do_daily_settlement():
    message = []

    time_module.sleep(600)  # 10분 대기

    cancel_msg = cancel_orders(side='all')
    message.append(cancel_msg)

    today = str(datetime.now().date())

    stocks = KIS.get_KR_stock_balance()
    if not isinstance(stocks, list):
        TA.send_tele(f"VALUE_REBAL결산: 잔고 조회 실패 ({stocks})")
        sys.exit(1)

    account = KIS.get_KR_account_summary()
    if not isinstance(account, dict):
        TA.send_tele(f"VALUE_REBAL결산: 계좌요약 실패 ({account})")
        sys.exit(1)

    total_asset  = account['total_krw_asset']
    cash_balance = account['cash_balance']
    stock_eval   = account['stock_eval_amt']

    prev_data     = load_json(VALUE_DATA_PATH)
    prev_holdings = prev_data.get("holdings", {})

    target     = load_json(VALUE_TARGET_PATH)
    sell_codes = target.get("sell_codes", [])

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

    month_return, year_return = 0.0, 0.0
    this_month = datetime.now().strftime("%Y-%m")
    this_year  = datetime.now().strftime("%Y")
    month_start_asset, year_start_asset = None, None

    history_files = sorted([f for f in os.listdir(VALUE_HISTORY_DIR) if f.endswith('.json')])
    for hf in history_files:
        try:
            with open(os.path.join(VALUE_HISTORY_DIR, hf), 'r') as f:
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

    value_data = {
        "total": {
            "date":           today,
            "total_balance":  total_asset,
            "cash_balance":   cash_balance,
            "stock_eval_amt": stock_eval,
            "holdings_count": len(new_holdings),
            "month_return":   month_return,
            "year_return":    year_return,
            "rebalanced":     True,
        },
        "holdings":    new_holdings,
        "exits_today": exits_today,
    }
    save_json(value_data, VALUE_DATA_PATH)
    save_json(value_data, os.path.join(VALUE_HISTORY_DIR, f"value_{today}.json"))

    message.append(
        f"📊 VALUE 리밸런싱 결산 {today}\n"
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

    message.append("✅ value_data.json 저장 완료 (리밸런싱)")
    TA.send_tele(message)


# ================================================================
# 매매 실행 (TR.py와 동일)
# ================================================================
def do_trade(order: dict, target: dict, message: list):
    sell_targets = target.get("sell_targets", {})
    buy_targets  = target.get("buy_targets", {})

    try:
        rs = split_data(order['round'])
    except ValueError as e:
        TA.send_tele(f"VALUE_REBAL: {e}")
        sys.exit(1)
    sell_split = [rs["sell_splits"], rs["sell_price"]]
    buy_split  = [rs["buy_splits"],  rs["buy_price"]]

    current_stocks = KIS.get_KR_stock_balance()
    current_hold = {}
    if isinstance(current_stocks, list):
        for s in current_stocks:
            current_hold[s["종목코드"]] = s["매도가능수량"]

    # ────────────── 매도 ──────────────
    # 리밸런싱은 sell_targets의 target_qty가 "매도할 수량"이므로
    # 보유수량과 target_qty 중 작은 값만큼만 매도 (오매도 방지)
    sell = {}
    for code, info in sell_targets.items():
        tgt = info.get("target_qty", 0)
        hold = current_hold.get(code, 0)
        qty = min(tgt, hold)
        if qty > 0:
            sell[code] = qty

    if len(sell) == 0:
        message.append("VALUE_REBAL: 매도 종목 없음")
    elif sell_split[0] > 0:
        message.append(f"VALUE_REBAL: {order['round']}회차 - 매도 주문")
        for code, qty in sell.items():
            lsc = sell_split[0]
            lsp = sell_split[1][:]
            sq  = int(qty // lsc)
            rem = int(qty - sq * lsc)

            if sq < 1:
                lsc, lsp, sq, rem = 1, [0.99], int(qty), 0

            price = KIS.get_KR_current_price(code)
            if not isinstance(price, int) or price == 0:
                message.append(f"VALUE_REBAL: {code} 현재가 불가, 매도 스킵")
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
        message.append(f"VALUE_REBAL: {order['round']}회차 - 매도 분할횟수 0")

    TA.send_tele(message)
    message = []

    # 매도→매수 딜레이 10분
    time_module.sleep(600)

    # ────────────── 매수 ──────────────
    KRW = KIS.get_KR_orderable_cash()
    if not isinstance(KRW, (int, float)):
        TA.send_tele(f"VALUE_REBAL: 주문가능현금 조회 불가 ({KRW})")
        sys.exit(1)
    orderable_KRW = float(KRW)

    # 잔고 재조회 → 이미 체결된 수량 차감
    # 리밸런싱의 buy_targets["target_qty"]는 "추가로 매수할 수량"(diff)이지
    # "총 보유 목표"가 아니므로, 이번 회차에서 이미 체결된 수량만 차감해야 함.
    # 이를 위해 target에 저장된 시점의 기준수량(baseline)을 사용.
    baseline = target.get("baseline_hold", {})
    refreshed = KIS.get_KR_stock_balance()
    hold_qty_map = {}
    if isinstance(refreshed, list):
        hold_qty_map = {s["종목코드"]: s["보유수량"] for s in refreshed}

    buy, buy_prices = {}, {}
    for code, info in buy_targets.items():
        base = baseline.get(code, 0)
        now_held = hold_qty_map.get(code, 0)
        bought_this_session = max(now_held - base, 0)
        remaining = info["target_qty"] - bought_this_session
        if remaining > 0:
            buy[code] = remaining

    target_KRW = 0
    buy_rate = buy_split[1][-1] if buy_split[1] else 1.0
    for code, qty in buy.items():
        p = KIS.get_KR_current_price(code)
        if not isinstance(p, int) or p == 0:
            message.append(f"VALUE_REBAL: {code} 현재가 불가, 매수 스킵")
            buy[code] = 0
            continue
        buy_prices[code] = p
        target_KRW += p * buy_rate * qty
        time_module.sleep(0.125)

    buy = {k: v for k, v in buy.items() if v > 0}

    message.append(
        f"VALUE_REBAL 매수가능: {int(orderable_KRW):,}원 | 목표매수금: {int(target_KRW):,}원"
        + (f" | 조정비율: {orderable_KRW/target_KRW:.4f}" if target_KRW > 0 else "")
    )

    if target_KRW > orderable_KRW and target_KRW > 0:
        adj = orderable_KRW / target_KRW
        for code in buy:
            buy[code] = int(buy[code] * adj)
        buy = {k: v for k, v in buy.items() if v > 0}
        message.append(f"VALUE_REBAL 매수수량 조정 (adjust_rate={adj:.4f})")
    else:
        message.append("VALUE_REBAL 매수가능금 충분")

    if len(buy) == 0:
        message.append("VALUE_REBAL: 매수 종목 없음")
    elif buy_split[0] > 0:
        message.append(f"VALUE_REBAL: {order['round']}회차 - 매수 주문")
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
    TA.send_tele("VALUE_REBAL: 매매시간이 아닙니다.")
    sys.exit(0)

message.append(f"VALUE_REBAL: {order['date']} {order['time']} {order['round']}/{order['total_round']}회차 [리밸런싱]")

# 전회 미체결 취소
cancel_msg = cancel_orders(side='all')
message.append(cancel_msg)

# ── 1회차: 크롤링 + 리밸런싱 target 생성 + 3분 대기 ──
if order['round'] == 1:
    # 1회차 시작 시점의 보유수량을 baseline으로 저장 (매수 누적 추적용)
    init_stocks = KIS.get_KR_stock_balance()
    baseline_hold = {}
    if isinstance(init_stocks, list):
        baseline_hold = {s["종목코드"]: s["보유수량"] for s in init_stocks}

    target = do_crawl_and_build_rebal_target(message)
    target["baseline_hold"] = baseline_hold
    save_json(target, VALUE_TARGET_PATH)

    message.append("VALUE_REBAL: 리밸런싱 target 생성 완료, 3분 대기 후 매매 시작...")
    time_module.sleep(180)

# ── 2~12회차: target 로드 ──
else:
    target = load_json(VALUE_TARGET_PATH)
    if not target:
        TA.send_tele("VALUE_REBAL: value_target.json 없음. 1회차 미실행?")
        sys.exit(1)

# ── 매매 실행 ──
do_trade(order, target, message)

# ── 12회차 후 결산 ──
if order['round'] == 12:
    do_daily_settlement()

sys.exit(0)
