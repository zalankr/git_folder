"""
JP_Hedge_signal.py
일본 시장 추세 신호 산출 모듈 (200일 이동평균 + 12개월 모멘텀)

기준 시계열: 1306.T (TOPIX ETF)
데이터 소스: KIS API 해외주식 일봉 (HHDFS76240000, EXCD=TSE)

3단계 상태:
- Bull   : MA200✓ AND MOM12✓  → 주식 80% / 금 20% / 채권 0%
- Neutral: MA xor MOM          → 주식 50% / 금 30% / 채권 20%
- Bear   : MA200✗ AND MOM12✗  → 주식 0%  / 금 60% / 채권 40%
"""

import requests
import time
from datetime import datetime, timedelta
from typing import Optional, Dict, List


# ============================================
# 신호 산출 파라미터
# ============================================
TOPIX_TICKER = "1306"
TOPIX_EXCHANGE = "TSE"
MA_WINDOW = 200
MOM_WINDOW = 252

WEIGHT_MATRIX = {
    "Bull":    {"stock": 0.80, "gold": 0.20, "bond": 0.00},
    "Neutral": {"stock": 0.50, "gold": 0.30, "bond": 0.20},
    "Bear":    {"stock": 0.00, "gold": 0.60, "bond": 0.40},
}

HEDGE_GOLD_TICKER = "1328"
HEDGE_BOND_TICKER = "1482"
HEDGE_GOLD_NAME = "Nomura NF Gold"
HEDGE_BOND_NAME = "iShares JGB 7-10Y"


def fetch_JP_daily_history(kis_api, ticker: str, n_days: int = 300) -> List[Dict]:
    """
    KIS API로 일본 ETF 일봉 히스토리 조회 (HHDFS76240000)

    Returns:
        List[Dict]: [{'date': 'YYYYMMDD', 'close': float}, ...] 오래된 순 정렬
                    실패 시 []
    """
    headers = {
        "Content-Type": "application/json",
        "authorization": f"Bearer {kis_api.access_token}",
        "appKey": kis_api.app_key,
        "appSecret": kis_api.app_secret,
        "tr_id": "HHDFS76240000"
    }

    closes = []
    current_date = datetime.now()
    max_pages = max(1, (n_days // 100) + 2)
    seen_dates = set()

    for _ in range(max_pages):
        params = {
            "AUTH": "",
            "EXCD": TOPIX_EXCHANGE,
            "SYMB": ticker,
            "GUBN": "0",
            "BYMD": current_date.strftime("%Y%m%d"),
            "MODP": "1"
        }
        url = f"{kis_api.url_base}/uapi/overseas-price/v1/quotations/dailyprice"
        try:
            res = requests.get(url, headers=headers, params=params, timeout=10)
            res.raise_for_status()
            data = res.json()
            if data.get("rt_cd") != "0":
                break
            output2 = data.get("output2", [])
            if not output2:
                break

            oldest_date_in_page = None
            for row in output2:
                date_str = row.get("xymd", "").strip()
                close_str = row.get("clos", "").strip()
                if not date_str or not close_str or close_str == "0":
                    continue
                if date_str in seen_dates:
                    continue
                try:
                    close = float(close_str)
                    if close <= 0:
                        continue
                except ValueError:
                    continue
                closes.append({"date": date_str, "close": close})
                seen_dates.add(date_str)
                if oldest_date_in_page is None or date_str < oldest_date_in_page:
                    oldest_date_in_page = date_str

            if len(closes) >= n_days:
                break
            if oldest_date_in_page is None:
                break
            current_date = datetime.strptime(oldest_date_in_page, "%Y%m%d") - timedelta(days=1)
            time.sleep(0.15)
        except Exception:
            break

    closes.sort(key=lambda x: x["date"])
    return closes


def compute_signal(kis_api, ticker: str = TOPIX_TICKER) -> Optional[Dict]:
    """
    1306.T 일봉 데이터로 200MA + 12M 모멘텀 신호 산출

    Returns:
        Dict | None : {date, close, ma200, mom12, signal_ma, signal_mom, state, weights, n_data}
    """
    needed = max(MA_WINDOW, MOM_WINDOW) + 30
    history = fetch_JP_daily_history(kis_api, ticker, n_days=needed)

    if len(history) < max(MA_WINDOW, MOM_WINDOW + 1):
        return None

    closes = [row["close"] for row in history]
    last_date = history[-1]["date"]

    ma200 = sum(closes[-MA_WINDOW:]) / MA_WINDOW
    if len(closes) < MOM_WINDOW + 1:
        return None
    mom12 = closes[-1] / closes[-(MOM_WINDOW + 1)] - 1.0

    current_close = closes[-1]
    signal_ma = current_close > ma200
    signal_mom = mom12 > 0

    if signal_ma and signal_mom:
        state = "Bull"
    elif signal_ma or signal_mom:
        state = "Neutral"
    else:
        state = "Bear"

    weights = WEIGHT_MATRIX[state]
    try:
        date_fmt = datetime.strptime(last_date, "%Y%m%d").strftime("%Y-%m-%d")
    except ValueError:
        date_fmt = last_date

    return {
        "date":       date_fmt,
        "close":      float(current_close),
        "ma200":      float(ma200),
        "mom12":      float(mom12),
        "signal_ma":  bool(signal_ma),
        "signal_mom": bool(signal_mom),
        "state":      state,
        "weights":    dict(weights),
        "n_data":     len(closes)
    }


def get_hedge_targets_qty(state: str, total_asset_jpy: float,
                          gold_price: float, bond_price: float) -> Dict:
    """
    헷지 ETF 목표 수량 산출 (1주 단위)
    """
    if state not in WEIGHT_MATRIX:
        raise ValueError(f"잘못된 state: {state}")

    weights = WEIGHT_MATRIX[state]
    gold_invest = total_asset_jpy * weights["gold"]
    bond_invest = total_asset_jpy * weights["bond"]
    gold_qty = int(gold_invest / gold_price) if gold_price > 0 else 0
    bond_qty = int(bond_invest / bond_price) if bond_price > 0 else 0

    return {
        HEDGE_GOLD_TICKER: {
            "name":          HEDGE_GOLD_NAME,
            "weight":        weights["gold"],
            "current_price": float(gold_price),
            "target_invest": float(gold_invest),
            "target_qty":    int(gold_qty),
            "categories":    ["hedge_gold"]
        },
        HEDGE_BOND_TICKER: {
            "name":          HEDGE_BOND_NAME,
            "weight":        weights["bond"],
            "current_price": float(bond_price),
            "target_invest": float(bond_invest),
            "target_qty":    int(bond_qty),
            "categories":    ["hedge_bond"]
        }
    }


def format_signal_message(signal: Dict, prev_state: Optional[str] = None) -> str:
    """Telegram 알림용 신호 요약"""
    if signal is None:
        return "신호 산출 실패"

    state_change = ""
    if prev_state and prev_state != signal["state"]:
        state_change = f" (이전: {prev_state} → 변경)"
    elif prev_state:
        state_change = f" (이전: {prev_state}, 유지)"

    ma_ok = "✓" if signal["signal_ma"] else "✗"
    mom_ok = "✓" if signal["signal_mom"] else "✗"

    return (
        f"[JP_HEDGE 신호] 기준일: {signal['date']}\n"
        f"상태: {signal['state']}{state_change}\n"
        f"종가: ¥{signal['close']:,.1f} / MA200: ¥{signal['ma200']:,.1f} [{ma_ok}]\n"
        f"12M모멘텀: {signal['mom12']*100:+.2f}% [{mom_ok}]\n"
        f"목표비중: 주식 {signal['weights']['stock']*100:.0f}% / "
        f"금 {signal['weights']['gold']*100:.0f}% / "
        f"채권 {signal['weights']['bond']*100:.0f}%\n"
        f"(데이터 {signal['n_data']}건)"
    )
