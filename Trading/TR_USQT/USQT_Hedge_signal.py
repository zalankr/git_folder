"""
USQT Hedge 신호 계산 모듈
경로: /var/autobot/TR_USQT/USQT_Hedge_signal.py

기능:
- SPY 기준 신호: MA200, 12M MOM(252거래일), 20D VOL(연율화), 14D RSI(Wilder)
- IEF 기준 신호: IEF 종가 > IEF MA200 → bond_ticker = IEF, else SGOV
- 4단계 상태(Bull/Weak_Bull/Weak_Bear/Bear) × 3단계 변동성(Low/Mid/High) = 12 비중 테이블
- RSI 헤지 진입(<28) / 청산(>50) 판단

데이터 소스: KIS API HHDFS76240000 (해외주식 일별시세, 한 번에 100개)
            → BYMD 를 점점 과거로 옮기며 페이지네이션 (300일치 확보)

Wilder RSI 14:
    Up   = max(close - prev_close, 0)
    Down = max(prev_close - close, 0)
    AvgUp_0   = mean(Up[0..13])      (단순평균으로 초기화)
    AvgDown_0 = mean(Down[0..13])
    AvgUp_t   = (AvgUp_{t-1}   * 13 + Up_t)   / 14
    AvgDown_t = (AvgDown_{t-1} * 13 + Down_t) / 14
    RS  = AvgUp / AvgDown
    RSI = 100 - 100 / (1 + RS)

사용법:
    from USQT_Hedge_signal import compute_signals
    signals = compute_signals(KIS_instance)
    # signals = {
    #   'spy_close': float, 'spy_ma200': float, 'ab200': bool,
    #   'mom12': float, 'mom_pos': bool,
    #   'vol20': float, 'vol_band': 'low'|'mid'|'high',
    #   'rsi14': float,
    #   'ief_close': float, 'ief_ma200': float, 'ief_bull': bool,
    #   'bond_ticker': 'IEF'|'SGOV',
    #   'state': 'Bull'|'Weak_Bull'|'Weak_Bear'|'Bear',
    #   'monthly_target': {'USQT': 0.85, 'IAU': 0.15, 'BOND': 0.0, 'bond_ticker': 'IEF'},
    #   'hedge_target':   {'USQT': 0.45, 'IAU': 0.35, 'BOND': 0.20, 'bond_ticker': 'IEF'},
    #   'asof_date': '2026-05-22'
    # }
"""

import requests
import time as time_module
from datetime import datetime, timedelta
import pandas as pd
import numpy as np

try:
    import telegram_alert as TA
except ImportError:
    class _Stub:
        @staticmethod
        def send_tele(msg): print(msg)
    TA = _Stub()


# ============================================
# 파라미터
# ============================================
MA_PERIOD       = 200
MOM_PERIOD      = 252
VOL_PERIOD      = 20
RSI_PERIOD      = 14
VOL_LOW         = 0.15
VOL_HIGH        = 0.28
RSI_LOW         = 28
RSI_RECOVER     = 50

SIGNAL_TICKER   = "SPY"
GOLD_TICKER     = "IAU"
BOND_NORMAL     = "IEF"
BOND_DEFENSIVE  = "SGOV"

DAYS_FETCH      = 320         # 12M MOM 252 + 여유 70 (휴장일 흡수)
PAGE_SIZE       = 100         # KIS API HHDFS76240000 한번 최대 100개


# ============================================
# 비중 테이블 (Bull/Weak_Bull/Weak_Bear/Bear × low/mid/high)
# (USQT_weight, IAU_weight, BOND_weight)
# ============================================
WEIGHT_TABLE = {
    "Bull":      {"low": (0.85, 0.15, 0.00),
                  "mid": (0.75, 0.15, 0.10),
                  "high":(0.55, 0.30, 0.15)},
    "Weak_Bull": {"low": (0.75, 0.25, 0.00),
                  "mid": (0.65, 0.22, 0.13),
                  "high":(0.45, 0.35, 0.20)},
    "Weak_Bear": {"low": (0.40, 0.30, 0.30),
                  "mid": (0.35, 0.35, 0.30),
                  "high":(0.25, 0.40, 0.35)},
    "Bear":      {"low": (0.00, 0.50, 0.50),
                  "mid": (0.00, 0.50, 0.50),
                  "high":(0.00, 0.30, 0.70)},
}

# RSI 헤지 진입시 고정 비중 (변동성 무관)
RSI_HEDGE_TARGET = (0.45, 0.35, 0.20)


# ============================================
# KIS API 일봉 페이지네이션 fetch
# ============================================
def _fetch_daily_kis(KIS, ticker, n_days=DAYS_FETCH):
    """KIS API 로 ticker 의 일별 종가를 n_days 이상 확보.
    HHDFS76240000 은 한번에 100개 → BYMD 를 점점 과거로 옮겨 페이지네이션.
    Returns: pd.Series (date index, close value, 오름차순) | None
    """
    exchange = KIS.get_exchange_by_ticker(ticker)
    if not isinstance(exchange, str) or exchange.startswith("error"):
        TA.send_tele(f"USQT 신호: {ticker} 거래소 조회 실패")
        return None

    # HHDFS76240000 은 EXCD = NAS/NYS/AMS 형식
    excd_map = {"NASD": "NAS", "NYSE": "NYS", "AMEX": "AMS"}
    exchange = excd_map.get(exchange, exchange)

    url = f"{KIS.url_base}/uapi/overseas-price/v1/quotations/dailyprice"
    headers = {
        "Content-Type":  "application/json",
        "authorization": f"Bearer {KIS.access_token}",
        "appKey":        KIS.app_key,
        "appSecret":     KIS.app_secret,
        "tr_id":         "HHDFS76240000"
    }

    all_rows = []
    bymd = datetime.utcnow().strftime("%Y%m%d")
    pages = 0
    MAX_PAGE = 6                          # 100 × 6 = 600일 충분

    while pages < MAX_PAGE:
        params = {
            "AUTH": "",
            "EXCD": exchange,
            "SYMB": ticker,
            "GUBN": "0",                  # 일봉
            "BYMD": bymd,
            "MODP": "1"                   # 수정주가
        }

        try:
            resp = requests.get(url, headers=headers, params=params, timeout=10)
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            TA.send_tele(f"USQT 신호: {ticker} 일봉 조회 오류 (page {pages+1}): {e}")
            break

        if data.get("rt_cd") != "0":
            TA.send_tele(f"USQT 신호: {ticker} 일봉 API 오류: {data.get('msg1')}")
            break

        output2 = data.get("output2", [])
        if not output2:
            break

        # 응답은 내림차순(최신부터) → 그대로 누적
        for row in output2:
            xymd = row.get("xymd", "")
            clos = row.get("clos", "")
            if xymd and clos and clos != "0":
                try:
                    all_rows.append((xymd, float(clos)))
                except:
                    continue

        pages += 1
        if len(all_rows) >= n_days:
            break

        # 다음 페이지 BYMD = 마지막 행 날짜 -1일
        last_xymd = output2[-1].get("xymd", "")
        if not last_xymd:
            break
        try:
            last_dt = datetime.strptime(last_xymd, "%Y%m%d")
            bymd = (last_dt - timedelta(days=1)).strftime("%Y%m%d")
        except:
            break

        time_module.sleep(0.15)

    if not all_rows:
        return None

    # DataFrame → Series (date 오름차순, 중복 제거)
    df = pd.DataFrame(all_rows, columns=["xymd", "close"])
    df["date"] = pd.to_datetime(df["xymd"], format="%Y%m%d")
    df = df.drop_duplicates(subset="date").sort_values("date")
    s = df.set_index("date")["close"].astype(float)
    return s


# ============================================
# 신호 계산 헬퍼
# ============================================
def _calc_ma(s, period):
    if len(s) < period:
        return None
    return float(s.iloc[-period:].mean())


def _calc_mom(s, period):
    """단순 가격비 수익률: (last / s[-period-1]) - 1"""
    if len(s) < period + 1:
        return None
    return float(s.iloc[-1] / s.iloc[-period - 1] - 1.0)


def _calc_vol(s, period):
    """일간 수익률 stdev × sqrt(252)"""
    if len(s) < period + 1:
        return None
    ret = s.pct_change().dropna()
    if len(ret) < period:
        return None
    return float(ret.iloc[-period:].std(ddof=1) * np.sqrt(252))


def _calc_rsi_wilder(s, period=14):
    """Wilder RSI."""
    if len(s) < period + 1:
        return None
    diff = s.diff().dropna()
    up   = diff.clip(lower=0.0)
    down = (-diff).clip(lower=0.0)

    if len(up) < period:
        return None

    # 초기: SMA
    avg_up   = up.iloc[:period].mean()
    avg_down = down.iloc[:period].mean()

    # Wilder smoothing
    for i in range(period, len(up)):
        avg_up   = (avg_up   * (period - 1) + up.iloc[i])   / period
        avg_down = (avg_down * (period - 1) + down.iloc[i]) / period

    if avg_down == 0:
        return 100.0
    rs = avg_up / avg_down
    return float(100.0 - 100.0 / (1.0 + rs))


def _vol_band(vol):
    if vol is None: return "mid"
    if vol < VOL_LOW:  return "low"
    if vol > VOL_HIGH: return "high"
    return "mid"


def _state(ab200, mom_pos):
    if ab200 and mom_pos:           return "Bull"
    if ab200 and not mom_pos:       return "Weak_Bull"
    if (not ab200) and mom_pos:     return "Weak_Bear"
    return "Bear"


# ============================================
# 메인: 신호 일괄 계산
# ============================================
def compute_signals(KIS):
    """SPY/IEF 데이터 fetch → 모든 신호 + 비중 산출.
    Returns dict | None (실패 시).
    """
    # 1) SPY 데이터
    spy = _fetch_daily_kis(KIS, SIGNAL_TICKER, DAYS_FETCH)
    if spy is None or len(spy) < MA_PERIOD + 5:
        TA.send_tele(f"USQT 신호: SPY 데이터 부족 ({0 if spy is None else len(spy)}일)")
        return None

    # 2) IEF 데이터
    time_module.sleep(0.3)
    ief = _fetch_daily_kis(KIS, BOND_NORMAL, DAYS_FETCH)
    if ief is None or len(ief) < MA_PERIOD + 5:
        TA.send_tele(f"USQT 신호: IEF 데이터 부족 ({0 if ief is None else len(ief)}일)")
        return None

    # 3) SPY 지표
    spy_close = float(spy.iloc[-1])
    spy_ma200 = _calc_ma(spy, MA_PERIOD)
    mom12     = _calc_mom(spy, MOM_PERIOD)
    vol20     = _calc_vol(spy, VOL_PERIOD)
    rsi14     = _calc_rsi_wilder(spy, RSI_PERIOD)

    if None in (spy_ma200, mom12, vol20, rsi14):
        TA.send_tele("USQT 신호: SPY 지표 계산 실패")
        return None

    ab200   = spy_close > spy_ma200
    mom_pos = mom12 > 0

    # 4) IEF 지표
    ief_close = float(ief.iloc[-1])
    ief_ma200 = _calc_ma(ief, MA_PERIOD)
    if ief_ma200 is None:
        TA.send_tele("USQT 신호: IEF MA200 계산 실패")
        return None
    ief_bull    = ief_close > ief_ma200
    bond_ticker = BOND_NORMAL if ief_bull else BOND_DEFENSIVE

    # 5) 상태/비중
    state    = _state(ab200, mom_pos)
    vol_band = _vol_band(vol20)
    w_usqt, w_iau, w_bond = WEIGHT_TABLE[state][vol_band]
    monthly_target = {
        "USQT": float(w_usqt),
        "IAU":  float(w_iau),
        "BOND": float(w_bond),
        "bond_ticker": bond_ticker
    }

    rh_usqt, rh_iau, rh_bond = RSI_HEDGE_TARGET
    hedge_target = {
        "USQT": float(rh_usqt),
        "IAU":  float(rh_iau),
        "BOND": float(rh_bond),
        "bond_ticker": bond_ticker
    }

    asof = spy.index[-1].strftime("%Y-%m-%d")

    return {
        "spy_close": spy_close,
        "spy_ma200": float(spy_ma200),
        "ab200":     bool(ab200),
        "mom12":     float(mom12),
        "mom_pos":   bool(mom_pos),
        "vol20":     float(vol20),
        "vol_band":  vol_band,
        "rsi14":     float(rsi14),
        "ief_close": ief_close,
        "ief_ma200": float(ief_ma200),
        "ief_bull":  bool(ief_bull),
        "bond_ticker":    bond_ticker,
        "state":          state,
        "monthly_target": monthly_target,
        "hedge_target":   hedge_target,
        "asof_date":      asof
    }


# ============================================
# 신호 → 적용 비중 결정
# (월말 신호 / 주간 RSI 신호 / 상태 파일과 결합)
# ============================================
def decide_target(signals, state_file, is_month_end, is_friday):
    """현재 신호와 직전 상태를 결합해 '이번 매매에서 적용할' 비중 결정.

    Parameters:
        signals      : compute_signals() 결과 dict
        state_file   : 직전 상태 dict (USQT_hedge_state.json 내용)
        is_month_end : 오늘 신호 계산이 월말 정기 신호인지 (True/False)
        is_friday    : 오늘 신호 계산이 주간 RSI 신호인지 (True/False)

    Returns:
        (applied_target dict, mode str, log list)
        mode: "monthly" | "rsi_enter" | "rsi_exit" | "rsi_hold" | "no_change"
    """
    log = []
    in_rsi_hedge = bool(state_file.get("in_rsi_hedge", False))
    last_monthly = state_file.get("last_monthly_target",
                                  {"USQT": 1.0, "IAU": 0.0, "BOND": 0.0,
                                   "bond_ticker": "IEF"})
    rsi = signals["rsi14"]

    # ✅ [PATCH] last_monthly 의 bond_ticker 는 직전 월말 시점 값.
    #   현재 신호 기준 IEF/SGOV 판단이 바뀌었으면 갱신해서 사용한다.
    #   비중(USQT/IAU/BOND) 은 last_monthly 그대로 유지 → 다른 영향 없음.
    cur_bond_ticker = signals.get("bond_ticker", last_monthly.get("bond_ticker", "IEF"))
    def _last_monthly_with_cur_bond():
        out = dict(last_monthly)
        out["bond_ticker"] = cur_bond_ticker
        return out

    # === 1) 월말 정기 신호 우선 ===
    if is_month_end:
        # 사양 §4: 월말과 RSI 신호 동시 → 월말 우선
        # RSI 헤지 중에 월말이 와도 → 사양 §4: "월말 신호 무시, RSI 헤지 유지"
        # 단 in_rsi_hedge=False 면 월말 신호 적용
        if in_rsi_hedge:
            log.append(f"월말 신호 발생했으나 RSI 헤지 진행 중 → 월말 신호 무시, RSI 헤지 비중 유지")
            return signals["hedge_target"], "rsi_hold", log
        else:
            log.append(f"월말 정기 신호 적용: state={signals['state']}, "
                       f"vol_band={signals['vol_band']}, "
                       f"target={signals['monthly_target']}")
            return signals["monthly_target"], "monthly", log

    # === 2) 주간 RSI 신호 ===
    if is_friday:
        if (not in_rsi_hedge) and rsi < RSI_LOW:
            log.append(f"RSI 헤지 진입: RSI14={rsi:.2f} < {RSI_LOW} → "
                       f"hedge_target={signals['hedge_target']}")
            return signals["hedge_target"], "rsi_enter", log

        if in_rsi_hedge and rsi > RSI_RECOVER:
            exit_target = _last_monthly_with_cur_bond()
            log.append(f"RSI 헤지 청산: RSI14={rsi:.2f} > {RSI_RECOVER} → "
                       f"직전 월말 비중 복귀 (bond={cur_bond_ticker} 갱신) "
                       f"last_monthly={exit_target}")
            return exit_target, "rsi_exit", log

        # 헤지 유지 또는 진입조건 미충족
        if in_rsi_hedge:
            log.append(f"RSI 헤지 유지: RSI14={rsi:.2f} (청산조건 {RSI_RECOVER} 미달)")
            return signals["hedge_target"], "rsi_hold", log
        else:
            no_change_target = _last_monthly_with_cur_bond()
            log.append(f"RSI 신호 변경 없음: RSI14={rsi:.2f} (진입조건 {RSI_LOW} 미달)")
            return no_change_target, "no_change", log

    # === 3) 이도 저도 아니면(수동/임시 실행) 현재 상태 유지 ===
    if in_rsi_hedge:
        log.append("수동 실행/예외: RSI 헤지 유지")
        return signals["hedge_target"], "rsi_hold", log
    log.append("수동 실행/예외: 직전 월말 비중 유지")
    return _last_monthly_with_cur_bond(), "no_change", log
