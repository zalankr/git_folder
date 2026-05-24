"""
USQT Hedge 24회차 매매 메인 스크립트
경로: /var/autobot/TR_USQT/USQT_Hedge.py

운영 흐름:
1. crontab으로 매 30분(또는 매 정각/30분)마다 호출
2. 분기 리밸런싱일이면 자기 자신 종료 → 통합 처리는 USQT_TR.py 가 담당
3. 1회차에서: 신호 계산 → 적용 비중 결정 → target 산출(USQT 개별종목 + IAU + IEF/SGOV)
   → USQT_hedge_state.json 갱신, USQT_target.json 갱신
4. 2~23회차: target 불러와서 분할 매매 (USAA 의 split_data 패턴 차용)
5. 24회차: 미체결 취소, 최종 잔고 출력

USQT 종목 비중 적용:
- USQT_target.json (직전 분기 리밸 시 저장된 csv weight) 의 weight × hedge_usqt_ratio
- CASH 포함 weight 합이 1.0 이므로, csv weight × usqt_ratio + (1 - usqt_ratio) = CASH 영역
- IAU, IEF/SGOV 는 (1 - usqt_ratio) 영역 안에서 별도 비중 배분

미체결 + 매도가능수량 처리:
- ord_psbl_qty 로 매도 캡핑
- ccld_qty_smtl1 (= hold_qty) 으로 실보유 확인 (T+1 무관)

크론 설정 예시 (UTC):
  # DST(서머타임): 1회차 = UTC 08:00 → 매 30분 ~ 20:30
  0,30 8-20 * * 1-5 timeout -s 9 28m /usr/bin/python3 /var/autobot/TR_USQT/USQT_Hedge.py
  # EST(겨울): 1회차 = UTC 09:00 → 매 30분 ~ 21:30
  0,30 9-21 * * 1-5 timeout -s 9 28m /usr/bin/python3 /var/autobot/TR_USQT/USQT_Hedge.py
  (실제는 USQT_hedge_day.json 에 등록된 날만 동작)
"""

import sys
import os
import json
import time as time_module
from datetime import datetime, timezone
from collections import defaultdict
from typing import Dict, List, Tuple, Optional

import pandas as pd
from tendo import singleton

import telegram_alert as TA
import KIS_US

# USAA 폴더 공용 캘린더
sys.path.insert(0, "/var/autobot/TR_USAA")
import USQT_Calender

# 로컬 모듈
sys.path.insert(0, "/var/autobot/TR_USQT")
import USQT_Hedge_signal as Sig


# ============================================
# 싱글톤 락
# ============================================
try:
    _me = singleton.SingleInstance()
except singleton.SingleInstanceException:
    TA.send_tele("USQT_Hedge: 이미 실행 중입니다.")
    sys.exit(0)


# ============================================
# 계좌/경로 (기존 USQT_TR.py 와 동일)
# ============================================
key_file_path   = "/var/autobot/KIS/kis63692011nkr.txt"
token_file_path = "/var/autobot/KIS/kis63692011_token.json"
cano            = "63692011"
acnt_prdt_cd    = "01"
KIS = KIS_US.KIS_API(key_file_path, token_file_path, cano, acnt_prdt_cd)

fee_rate                = KIS.SELL_FEE_RATE
USQT_target_path        = "/var/autobot/TR_USQT/USQT_target.json"
USQT_stock_path         = "/var/autobot/TR_USQT/USQT_stock.csv"
USQT_hedge_state_path   = "/var/autobot/TR_USQT/USQT_hedge_state.json"
USQT_hedge_target_path  = "/var/autobot/TR_USQT/USQT_hedge_target.json"  # 헤지 회차간 target 보관


# ============================================
# 유틸
# ============================================
def save_json(data, path, order):
    msgs = []
    try:
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=4, default=str)
        msgs.append(f"USQT_Hedge: {order['date']} {order['round']}/{order['total_round']}회차 저장: {path}")
    except Exception as e:
        msgs.append(f"USQT_Hedge: {path} 저장 실패: {e}")
        bp = f"/var/autobot/TR_USQT/backup_hedge_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        try:
            with open(bp, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=4, default=str)
            msgs.append(f"USQT_Hedge: 백업 생성: {bp}")
        except Exception as be:
            msgs.append(f"USQT_Hedge: 백업 실패: {be}")
    return msgs


def health_check():
    checks = []
    if not KIS.access_token:
        checks.append("USQT_Hedge: API 토큰 없음")
    for f in (USQT_stock_path,):
        if not os.path.exists(f):
            checks.append(f"USQT_Hedge: 파일 없음: {f}")
    try:
        import socket
        socket.create_connection(("openapi.koreainvestment.com", 9443), timeout=5)
    except:
        checks.append("USQT_Hedge: KIS API 서버 접속 불가")
    if checks:
        TA.send_tele("\n".join(checks))
        sys.exit(1)


def cancel_orders():
    try:
        summary, msgs = KIS.cancel_all_unfilled_orders()
        return f"USQT_Hedge: {summary['success']}/{summary['total']} 주문 취소", summary
    except Exception as e:
        return f"USQT_Hedge: 주문취소 에러 ({e})", {"success": 0, "total": 0}


def is_US_trading_day():
    try:
        import exchange_calendars as xcals
        import pytz
        cal = xcals.get_calendar("XNYS")
        eastern = pytz.timezone('America/New_York')
        today_et = datetime.now(timezone.utc).astimezone(eastern).date()
        return cal.is_session(pd.Timestamp(today_et))
    except ImportError:
        try:
            import pytz
            eastern = pytz.timezone('America/New_York')
            wd = datetime.now(timezone.utc).astimezone(eastern).weekday()
        except ImportError:
            wd = datetime.now(timezone.utc).weekday()
        return wd < 5
    except Exception:
        return True


# ============================================
# 분할 매매 가격 multiplier (USAA HAA 패턴 차용 → 헤지는 보수적)
# round 1~11 Pre-Market, 12~24 Regular
# 모든 종목(USQT 개별 + IAU + 채권) 공통 HAA 패턴 사용
# ============================================
def split_data(round_num):
    if round_num in range(1, 12):           # Pre-Market
        sell_splits = 4
        sell_price  = [1.0075, 1.0150, 1.0225, 1.0300]
        buy_splits  = 2
        buy_price   = [0.9925, 0.9850]

    elif round_num in range(12, 25):        # Regular
        sell_splits = 5
        sell_price  = [1.003, 1.006, 1.009, 1.012, 1.015]
        buy_splits  = 5
        buy_price   = [0.997, 0.994, 0.991, 0.988, 0.985]

        if round_num == 12:
            pass
        elif round_num == 13:
            sell_price[0] = 0.99
        elif round_num == 14:
            sell_splits = 4
            sell_price  = sell_price[:4]
            buy_price[0] = 1.01
        elif round_num == 15:
            sell_splits = 4; sell_price = sell_price[:4]
            buy_splits  = 4; buy_price  = buy_price[:4]
        elif round_num == 16:
            sell_splits = 4; sell_price = sell_price[:4]
            sell_price[0] = 0.99
            buy_splits  = 4; buy_price  = buy_price[:4]
        elif round_num == 17:
            sell_splits = 3; sell_price = sell_price[:3]
            buy_splits  = 4; buy_price  = buy_price[:4]
            buy_price[0] = 1.01
        elif round_num == 18:
            sell_splits = 3; sell_price = sell_price[:3]
            buy_splits  = 3; buy_price  = buy_price[:3]
        elif round_num == 19:
            sell_splits = 3; sell_price = sell_price[:3]
            sell_price[0] = 0.99
            buy_splits  = 3; buy_price  = buy_price[:3]
        elif round_num == 20:
            sell_splits = 2; sell_price = sell_price[:2]
            buy_splits  = 3; buy_price  = buy_price[:3]
            buy_price[0] = 1.01
        elif round_num == 21:
            sell_splits = 2; sell_price = sell_price[:2]
            buy_splits  = 2; buy_price  = buy_price[:2]
        elif round_num == 22:
            sell_splits = 2; sell_price = sell_price[:2]
            sell_price[0] = 0.99
            buy_splits  = 2; buy_price  = buy_price[:2]
        elif round_num == 23:
            sell_splits = 1; sell_price = [0.98]
            buy_splits  = 2; buy_price  = buy_price[:2]
            buy_price[0] = 1.01
        elif round_num == 24:
            sell_splits = 1; sell_price = [0.98]
            buy_splits  = 1; buy_price  = [1.02]
    else:
        TA.send_tele(f"USQT_Hedge: 유효하지 않은 round 값: {round_num}")
        sys.exit(1)

    return {"sell_splits": sell_splits, "sell_price": sell_price,
            "buy_splits":  buy_splits,  "buy_price":  buy_price}


# ============================================
# 상태 파일 로드/세이브
# ============================================
def load_state():
    """USQT_hedge_state.json 로드. 없으면 기본값."""
    default = {
        "in_rsi_hedge": False,
        "last_monthly_target": {"USQT": 1.0, "IAU": 0.0, "BOND": 0.0, "bond_ticker": "IEF"},
        "last_monthly_state": "Bull",
        "last_monthly_vol":   0.15,
        "last_signal_date":   "1970-01-01",
        "current_target":     {"USQT": 1.0, "IAU": 0.0, "BOND": 0.0, "bond_ticker": "IEF"},
        "active_since":       "1970-01-01",
        "active_trading_day": "1970-01-01"   # ✅ 매매 진행 중인 날짜 (1회차 매매 결정 시 세팅, 24회차 종료 시 클리어)
    }
    if not os.path.exists(USQT_hedge_state_path):
        return default
    try:
        with open(USQT_hedge_state_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        TA.send_tele(f"USQT_Hedge: state 로드 실패 → 기본값 사용 ({e})")
        return default


def save_state(state):
    try:
        with open(USQT_hedge_state_path, 'w', encoding='utf-8') as f:
            json.dump(state, f, ensure_ascii=False, indent=4, default=str)
        return True
    except Exception as e:
        TA.send_tele(f"USQT_Hedge: state 저장 실패 ({e})")
        return False


# ============================================
# USQT csv → 개별종목 target_qty 산출 (헤지 USQT 비중 반영)
# ============================================
def build_hedge_targets(applied_target: Dict, total_usd_asset: float) -> Tuple[Dict, List[str]]:
    """csv 의 USQT 개별종목 weight × hedge_usqt_ratio 로 target_qty 산출
    + IAU, BOND 비중에 따른 target_qty 산출

    Returns:
        (target dict, log msgs)
        target = {
            ticker: {
                "name": str, "weight_eff": float,  # 전체 자산 대비 실효 비중
                "current_price": float,
                "target_invest": float,
                "target_qty": int,
                "kind": "USQT" | "IAU" | "BOND"
            },
            ...
        }
    """
    msgs = []
    usqt_ratio = applied_target.get("USQT", 0.0)
    iau_ratio  = applied_target.get("IAU",  0.0)
    bond_ratio = applied_target.get("BOND", 0.0)
    bond_ticker = applied_target.get("bond_ticker", "IEF")

    target = {}

    # 1) USQT 개별종목: USQT_target.json (직전 분기 리밸 시 저장)의 csv weight × usqt_ratio
    if usqt_ratio > 0:
        try:
            with open(USQT_target_path, 'r', encoding='utf-8') as f:
                base = json.load(f)
        except Exception as e:
            msgs.append(f"USQT_target.json 로드 실패 → USQT 개별종목 매매 스킵 ({e})")
            base = {}

        # CSV weight 합 정규화: CASH 제외한 종목 weight 합 = stock_weight_sum
        stock_weight_sum = 0.0
        for code, v in base.items():
            if code == "CASH":
                continue
            stock_weight_sum += float(v.get("weight", 0))

        if stock_weight_sum <= 0:
            msgs.append("USQT_target.json: 종목 weight 합이 0 → USQT 개별종목 스킵")
        else:
            for code, v in base.items():
                if code == "CASH":
                    continue
                csv_w = float(v.get("weight", 0))
                # 정규화 후 usqt_ratio 적용: (csv_w / stock_weight_sum) × usqt_ratio
                w_eff = (csv_w / stock_weight_sum) * usqt_ratio
                price = KIS.get_US_current_price(code)
                if not isinstance(price, float) or price <= 0:
                    msgs.append(f"USQT 개별 {code} 현재가 조회 실패 → 스킵")
                    time_module.sleep(0.15)
                    continue
                invest = w_eff * total_usd_asset
                qty    = int(invest / price)
                target[code] = {
                    "name":          v.get("name", code),
                    "weight_eff":    w_eff,
                    "current_price": price,
                    "target_invest": invest,
                    "target_qty":    qty,
                    "kind":          "USQT"
                }
                time_module.sleep(0.15)

    # 2) IAU
    if iau_ratio > 0:
        price = KIS.get_US_current_price("IAU")
        if isinstance(price, float) and price > 0:
            invest = iau_ratio * total_usd_asset
            target["IAU"] = {
                "name": "iShares Gold Trust",
                "weight_eff":    iau_ratio,
                "current_price": price,
                "target_invest": invest,
                "target_qty":    int(invest / price),
                "kind":          "IAU"
            }
        else:
            msgs.append("IAU 현재가 조회 실패 → 스킵")
        time_module.sleep(0.15)

    # 3) BOND (IEF or SGOV)
    if bond_ratio > 0:
        price = KIS.get_US_current_price(bond_ticker)
        if isinstance(price, float) and price > 0:
            invest = bond_ratio * total_usd_asset
            target[bond_ticker] = {
                "name": bond_ticker,
                "weight_eff":    bond_ratio,
                "current_price": price,
                "target_invest": invest,
                "target_qty":    int(invest / price),
                "kind":          "BOND"
            }
        else:
            msgs.append(f"{bond_ticker} 현재가 조회 실패 → 스킵")
        time_module.sleep(0.15)

    # 4) 반대 채권은 target_qty=0 으로 명시 (보유시 전량 매도되게)
    other_bond = "SGOV" if bond_ticker == "IEF" else "IEF"
    if other_bond not in target:
        target[other_bond] = {
            "name":          other_bond,
            "weight_eff":    0.0,
            "current_price": 0.0,
            "target_invest": 0.0,
            "target_qty":    0,
            "kind":          "BOND_OTHER"
        }

    return target, msgs


# ============================================
# 신호 계산 + 상태 갱신 (1회차 진입시)
# ============================================
def signal_and_decide(message: List[str]) -> Tuple[Optional[Dict], Optional[str]]:
    """신호 계산 → 적용비중 결정 → 상태파일 갱신. (applied_target, mode) 반환."""
    state = load_state()

    # 신호 계산
    signals = Sig.compute_signals(KIS)
    if signals is None:
        message.append("USQT_Hedge: 신호 계산 실패 → 직전 비중으로 매매 진행")
        applied = state.get("current_target", state["last_monthly_target"])
        return applied, "no_change"

    message.append(
        f"USQT 신호 [{signals['asof_date']}]: SPY={signals['spy_close']:.2f} "
        f"MA200={signals['spy_ma200']:.2f} ab200={signals['ab200']} "
        f"MOM12={signals['mom12']*100:+.1f}% VOL20={signals['vol20']*100:.1f}%({signals['vol_band']}) "
        f"RSI14={signals['rsi14']:.1f} | IEF={signals['ief_close']:.2f}/MA200={signals['ief_ma200']:.2f} "
        f"bond={signals['bond_ticker']} | state={signals['state']}"
    )

    today = datetime.now(timezone.utc).date()
    is_month_end = _is_month_end_signal(today)
    is_friday    = _is_friday_signal(today)

    applied, mode, log = Sig.decide_target(signals, state, is_month_end, is_friday)
    for l in log:
        message.append("USQT 결정: " + l)

    # 상태 갱신
    new_state = dict(state)
    new_state["last_signal_date"] = str(today)
    new_state["current_target"]   = applied
    new_state["active_since"]     = str(today)

    if mode == "monthly":
        new_state["in_rsi_hedge"]        = False
        new_state["last_monthly_target"] = signals["monthly_target"]
        new_state["last_monthly_state"]  = signals["state"]
        new_state["last_monthly_vol"]    = signals["vol20"]
    elif mode == "rsi_enter":
        new_state["in_rsi_hedge"] = True
    elif mode == "rsi_exit":
        new_state["in_rsi_hedge"] = False
    # rsi_hold / no_change → in_rsi_hedge 유지

    save_state(new_state)
    return applied, mode


def _is_month_end_signal(today):
    """오늘이 '월말 정기 신호 후 익일 매매일'인지 판정.
    운영상: USQT_hedge_day.json 에 등록된 매매일 중 '월의 첫 거래일'을 월말 신호로 본다.
    간이 판정: 어제(또는 직전 거래일)의 월 ≠ 오늘의 월.
    """
    try:
        with open(USQT_Calender.USQT_HEDGE_DAY_PATH, 'r', encoding='utf-8') as f:
            hd = json.load(f)
    except Exception:
        return False
    all_days = sorted(set(hd.get("summer_dst", []) + hd.get("winter_standard", [])))
    today_s = str(today)
    if today_s not in all_days:
        return False
    idx = all_days.index(today_s)
    if idx == 0:
        return True
    prev = datetime.strptime(all_days[idx - 1], "%Y-%m-%d").date()
    return prev.month != today.month


def _is_friday_signal(today):
    """오늘이 '주간 RSI 신호 후 익일 매매일'인지 판정.
    실제 신호는 직전 금요일 종가 기준이므로,
    오늘이 'USQT 헤지 매매일' 이면서 '직전 거래일이 금요일'인 경우.
    간단히: 오늘이 월요일이면 True (또는 화요일이면서 직전 평일이 금요일인 케이스).
    """
    try:
        with open(USQT_Calender.USQT_HEDGE_DAY_PATH, 'r', encoding='utf-8') as f:
            hd = json.load(f)
    except Exception:
        return False
    all_days = sorted(set(hd.get("summer_dst", []) + hd.get("winter_standard", [])))
    if str(today) not in all_days:
        return False
    # 월요일=0
    return today.weekday() == 0


# ============================================
# 메인
# ============================================
def main():
    # 거래일 체크
    if not is_US_trading_day():
        TA.send_tele("USQT_Hedge: 미국 거래일이 아닙니다.")
        return

    # 분기 리밸런싱일이면 USQT_TR.py 가 통합 처리하므로 종료
    today = datetime.now(timezone.utc).date()
    if USQT_Calender.check_USQT_rebal_day(today):
        TA.send_tele("USQT_Hedge: 오늘은 분기 리밸런싱일 → USQT_TR.py 가 헤지 통합 처리. 헤지 스크립트 종료.")
        return

    health_check()

    # 회차 확인
    ot = USQT_Calender.check_order_time()
    if ot['season'] == "USQT_not_hedge_day" or ot['round'] == 0:
        TA.send_tele(f"USQT_Hedge: 매매시간/매매일 아님 ({ot['date']} {ot['time']})")
        return

    message = []
    message.append(f"USQT_Hedge: {ot['date']} {ot['round']}/{ot['total_round']}회차 시작 (season={ot['season']})")

    # ============================================
    # ✅ [신규] 2회차 이후: active_trading_day 체크
    # 1회차에서 "매매 필요 없음"으로 판정된 날에는
    # 2~24회차 진입 시 즉시 조용히 종료 (알림도 보내지 않음)
    # ============================================
    if ot['round'] >= 2:
        _state_check = load_state()
        if _state_check.get("active_trading_day", "1970-01-01") != str(ot['date']):
            # 1회차에서 매매 결정이 없었던 날 → 조용히 종료
            return

    # 전회 주문 취소
    cmsg, _ = cancel_orders()
    message.append(cmsg)
    time_module.sleep(3)

    # ============================================
    # 1회차: 신호 + target 산출 + 저장
    # ============================================
    if ot['round'] == 1:
        # 1) 신호 계산 + 적용비중 결정
        applied, mode = signal_and_decide(message)
        message.append(f"USQT_Hedge 적용 비중 [{mode}]: USQT={applied['USQT']:.2%}, "
                       f"IAU={applied['IAU']:.2%}, BOND({applied['bond_ticker']})={applied['BOND']:.2%}")

        # 2) 총 USD 자산
        stocks_list = KIS.get_US_stock_balance()
        if not isinstance(stocks_list, list):
            TA.send_tele(f"USQT_Hedge: 잔고 조회 불가 종료 ({stocks_list})")
            sys.exit(1)
        stock_eval = sum(s['eval_amt'] for s in stocks_list)
        time_module.sleep(0.2)

        orderable = KIS.get_US_order_available()
        if orderable is None:
            TA.send_tele("USQT_Hedge: USD 주문가능금액 조회 불가 종료")
            sys.exit(1)
        total_usd = float(stock_eval) + float(orderable)
        message.append(f"USQT_Hedge 총자산: ${total_usd:,.2f} "
                       f"(주식:${stock_eval:,.2f} + 현금:${orderable:,.2f})")

        # 3) target 산출
        target, tmsgs = build_hedge_targets(applied, total_usd)
        message.extend(tmsgs)

        # 4) 저장 (회차간 보관용 헤지 전용 target)
        message.extend(save_json(target, USQT_hedge_target_path, ot))
    else:
        # 회차 2~ : 저장된 target 로드
        if not os.path.exists(USQT_hedge_target_path):
            TA.send_tele(f"USQT_Hedge: {USQT_hedge_target_path} 없음. 1회차부터 실행 필요. 종료.")
            return
        with open(USQT_hedge_target_path, 'r', encoding='utf-8') as f:
            target = json.load(f)

    target_code = list(target.keys())

    # ============================================
    # 보유 잔고
    # ============================================
    stocks = KIS.get_US_stock_balance()
    if not isinstance(stocks, list):
        TA.send_tele(f"USQT_Hedge: 잔고 조회 불가 종료 ({stocks})")
        sys.exit(1)

    hold = {}
    for s in stocks:
        t = s["ticker"]
        hold[t] = {
            "name":          s["name"],
            "hold_qty":      s["quantity"],
            "ord_psbl_qty":  s.get("ord_psbl_qty") or s["quantity"],
            "current_price": s["current_price"],
            "exchange":      s["exchange"],
        }
    hold_code = list(hold.keys())

    # ============================================
    # 매수/매도 수량 계산
    # ============================================
    buy, sell = {}, {}
    for t in hold_code:
        if t in target_code:
            tgt_qty = int(target[t].get("target_qty", 0))
            hld_qty = int(hold[t]["hold_qty"])
            if tgt_qty > hld_qty:
                buy[t] = tgt_qty - hld_qty
            elif tgt_qty < hld_qty:
                need = hld_qty - tgt_qty
                sellable = min(need, hold[t]["ord_psbl_qty"])
                if sellable > 0:
                    sell[t] = sellable
                else:
                    message.append(f"USQT_Hedge 매도스킵: {t} 필요{need}, 가능{hold[t]['ord_psbl_qty']}")
        else:
            sellable = min(hold[t]["hold_qty"], hold[t]["ord_psbl_qty"])
            if sellable > 0:
                sell[t] = sellable

    for t in target_code:
        tgt_qty = int(target[t].get("target_qty", 0))
        if t not in hold_code and tgt_qty > 0:
            buy[t] = tgt_qty

    # ============================================
    # ✅ [신규] 1회차 분기: 매매 필요 여부 확인
    # 매매할 종목이 1개도 없으면 알림 1회 후 즉시 종료
    # (이후 2~24회차는 active_trading_day 미일치로 자동 스킵됨)
    # 매매 필요시 active_trading_day 저장 → 24회차까지 진행
    # ============================================
    if ot['round'] == 1:
        total_orders = len(buy) + len(sell)
        if total_orders == 0:
            message.append(
                f"USQT_Hedge: 헤지 비중 변경 없음 → 매매 종목 0건. "
                f"오늘 24회차 매매 모두 스킵하고 종료."
            )
            # active_trading_day 명시적으로 클리어 (안전장치)
            _st = load_state()
            _st["active_trading_day"] = "1970-01-01"
            save_state(_st)
            TA.send_tele(message)
            return
        else:
            # 매매 진행 결정 → active_trading_day 저장
            _st = load_state()
            _st["active_trading_day"] = str(ot['date'])
            save_state(_st)
            message.append(
                f"USQT_Hedge: 매매 진행 결정 → 매도 {len(sell)}종목, 매수 {len(buy)}종목, "
                f"오늘 24회차 매매 활성화"
            )

    # ============================================
    # 분할 매매 (HAA 패턴)
    # ============================================
    rsplit = split_data(ot['round'])
    sell_split = [rsplit["sell_splits"], rsplit["sell_price"]]
    buy_split  = [rsplit["buy_splits"],  rsplit["buy_price"]]

    # 매도
    if not sell:
        message.append("USQT_Hedge: 매도 종목 없음")
    elif sell_split[0] > 0:
        message.append(f"USQT_Hedge: {ot['round']}회차 - 매도 주문")
        for t, qty in sell.items():
            sc = sell_split[0]
            sp = sell_split[1][:]
            sq = int(qty // sc)
            rm = int(qty - sq * sc)
            if sq < 1:
                sc = 1; sp = [0.99]; sq = int(qty); rm = 0

            price = KIS.get_US_current_price(t)
            if not isinstance(price, float) or price <= 0:
                message.append(f"USQT_Hedge 매도스킵: {t} 현재가 조회 실패")
                continue

            raw_excd = hold.get(t, {}).get("exchange", "")
            excd_map = {"NAS":"NASD","NYS":"NYSE","AMS":"AMEX","NASD":"NASD","NYSE":"NYSE","AMEX":"AMEX"}
            tex = excd_map.get(raw_excd, None)

            for i in range(sc):
                tq = sq + (rm if i == sc - 1 else 0)
                if tq < 1:
                    continue
                op = round(price * sp[i], 2)
                oi, om = KIS.order_sell_US(t, tq, op, exchange=tex)
                if oi is None:
                    time_module.sleep(2)
                    oi, om = KIS.order_sell_US(t, tq, op, exchange=tex)
                if oi is None:
                    message.append(f"USQT_Hedge 매도 오류: {t} {tq}주 ${op:.2f}")
                elif oi.get("success"):
                    message.append(f"매도 {t} {tq}주 ${op:.2f} #{oi.get('order_number','')}")
                else:
                    message.append(f"매도 실패 {t} {tq}주: {oi.get('error_message','')}")
                time_module.sleep(0.2)
    else:
        message.append(f"USQT_Hedge: {ot['round']}회차 매도 스킵 - 미처분 잔량: {list(sell.keys())}")

    TA.send_tele(message)
    message = []

    # 매도 → 매수 대기
    time_module.sleep(600)

    # 매수 전 가능금액 확인 후 비례 축소
    USD = KIS.get_US_order_available()
    if USD is None:
        TA.send_tele("USQT_Hedge: 매수 전 USD 주문가능금액 조회 불가 종료")
        sys.exit(1)
    orderable_USD = float(USD)

    target_USD = 0.0
    buy_prices = {}
    buy_price_rate = buy_split[1][-1] if buy_split[1] else 1.0
    for t, qty in buy.items():
        price = KIS.get_US_current_price(t)
        if not isinstance(price, float) or price <= 0:
            TA.send_tele(f"USQT_Hedge: {t} 현재가 조회 실패 - 매수 스킵")
            buy[t] = 0
            continue
        buy_prices[t] = price
        target_USD += price * buy_price_rate * qty
        time_module.sleep(0.15)

    message.append(f"USQT_Hedge 매수가능: ${orderable_USD:,.2f} | 목표매수금: ${target_USD:,.2f}"
                   + (f" | 조정: {orderable_USD/target_USD:.4f}" if target_USD > 0 else ""))

    if target_USD > orderable_USD and target_USD > 0:
        adj = orderable_USD / target_USD
        for t in list(buy.keys()):
            buy[t] = int(buy[t] * adj)
        buy = {t: q for t, q in buy.items() if q > 0}
        message.append(f"USQT_Hedge 매수수량 조정 (adjust={adj:.4f})")

    buy = {t: q for t, q in buy.items() if q > 0}

    # 매수
    if not buy:
        message.append("USQT_Hedge: 매수 종목 없음")
    elif buy_split[0] > 0:
        message.append(f"USQT_Hedge: {ot['round']}회차 - 매수 주문")
        for t, qty in buy.items():
            bc = buy_split[0]
            bp = buy_split[1][:]
            sq = int(qty // bc)
            rm = int(qty - sq * bc)
            if sq < 1:
                if qty < 1:
                    continue
                bc = 1; bp = [1.01]; sq = int(qty); rm = 0
            price = buy_prices.get(t)
            if not isinstance(price, float) or price <= 0:
                message.append(f"USQT_Hedge: {t} 현재가 없음 - 매수 스킵")
                continue
            for i in range(bc):
                tq = sq + (rm if i == bc - 1 else 0)
                if tq < 1:
                    continue
                op = round(price * bp[i], 2)
                oi, om = KIS.order_buy_US(t, tq, op)
                if oi is None:
                    time_module.sleep(2)
                    oi, om = KIS.order_buy_US(t, tq, op)
                if oi is None:
                    message.append(f"USQT_Hedge 매수 오류: {t} {tq}주 ${op:.2f}")
                elif oi.get("success"):
                    message.append(f"매수 {t} {tq}주 ${op:.2f} #{oi.get('order_number','')}")
                else:
                    message.append(f"매수 실패 {t} {tq}주: {oi.get('error_message','')}")
                time_module.sleep(0.2)

    TA.send_tele(message)
    message = []

    # ============================================
    # 24회차: 마무리
    # ============================================
    if ot['round'] == 24:
        time_module.sleep(300)
        cm, _ = cancel_orders()
        message.append(cm)
        message.append(f"USQT_Hedge {ot['date']} 헤지 매매 종료")

        final_stocks = KIS.get_US_stock_balance()
        if isinstance(final_stocks, list):
            tot_eval = sum(s['eval_amt'] for s in final_stocks)
        else:
            tot_eval = 0.0
        time_module.sleep(0.2)
        final_usd = KIS.get_US_order_available() or 0.0

        message.append(f"USQT_Hedge 최종 주식 평가금: ${tot_eval:,.2f}")
        message.append(f"USQT_Hedge 최종 USD 가용: ${final_usd:,.2f}")
        message.append(f"USQT_Hedge 총 자산: ${tot_eval + final_usd:,.2f}")

        # ✅ [신규] active_trading_day 클리어 (다음 매매일까지 idle 상태)
        _st = load_state()
        _st["active_trading_day"] = "1970-01-01"
        save_state(_st)
        message.append("USQT_Hedge: active_trading_day 클리어 → 다음 매매일 대기")

        TA.send_tele(message)


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception as e:
        import traceback
        tb = traceback.format_exc()
        TA.send_tele(f"USQT_Hedge: 예외 발생\n{e}\n{tb[:1500]}")
        sys.exit(1)
