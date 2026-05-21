# -*- coding: utf-8 -*-
"""
KRFT_TR.py
==========
국내 선물 자동매매 메인 로직.

공개 함수:
  run_signal_entry()  : 월말 신규/조정 진입 (15:25~15:34)
  run_rollover()      : 선물 만기일 롤오버 (15:15~15:20)

흐름 (월말 진입):
  1) 현물평가금 산출 (KRQT+KRTR, daily_snapshot 기반)
  2) 월말 데이터 수집 → krfuture_monthly.json 업데이트
  3) compute_signals() 호출
  4) Hedge3↔Hedge1 충돌 해소 (Hedge1 신호 시 Hedge3 흡수)
  5) 전략별 enabled 플래그 적용
  6) 목표 명목금액 → 종목별 목표 수량 분배 (K200 정규/미니, KQ150)
  7) 현재 보유포지션과 비교 → 신규/추가/청산 액션 분해
  8) 증거금 검증 (TTTO5105R)
  9) 라운드별 주문 실행 (지정가→시장가 단계 승격)
 10) 결과 저장 (KRFT_result.json 업데이트, monthly.json positions 동기화)
"""
from __future__ import annotations
import json
import os
import sys
import time
from datetime import datetime, date, timedelta
from pathlib import Path
from typing import Optional

import pytz

sys.path.insert(0, "/var/autobot")
sys.path.insert(0, "/var/autobot/TR_KRFT")

import telegram_alert as TA
from KIS_KR import KIS_API
import KRFT_order as ORDER
import KRFT_symbol as SYM
import KRFT_data as DATA
import KRFT_signal as SIG

# ------------------------------------------------------------------
# DRY-RUN MODE (환경변수로 제어)
# ------------------------------------------------------------------
# KRFT_DRY_RUN=1 또는 KRFT_DRY_RUN=true 면 실제 주문 차단,
# 시그널 계산/잔고 조회/시간 대기까지는 정상 동작
DRY_RUN = os.getenv("KRFT_DRY_RUN", "0").lower() in ("1", "true", "yes")

if DRY_RUN:
    # ORDER 의 변경 함수만 mock 로 교체. 조회 함수는 그대로 사용.
    _real_order_futures   = ORDER.order_futures
    _real_cancel_order    = ORDER.cancel_order
    _real_cancel_all      = ORDER.cancel_all_unfilled

    def _dry_order_futures(kis, shtn_code, qty, price, side, cls,
                            market_order=False):
        print(f"  [DRY-RUN] order_futures({shtn_code}, qty={qty}, price={price}, "
              f"side={side}, cls={cls}, mkt={market_order})")
        return {"ok": True, "order_no": f"DRY-{shtn_code}-{int(time.time()*1000)%100000}",
                "org_orgno": "DRYORGN", "msg": "dry_run"}

    def _dry_cancel_order(kis, org_orgno, order_no, qty=0):
        print(f"  [DRY-RUN] cancel_order({order_no}, qty={qty})")
        return {"ok": True, "msg": "dry_run"}

    def _dry_cancel_all(kis, log_fn=print):
        print(f"  [DRY-RUN] cancel_all_unfilled")
        return 0

    ORDER.order_futures    = _dry_order_futures
    ORDER.cancel_order     = _dry_cancel_order
    ORDER.cancel_all_unfilled = _dry_cancel_all

    # 카카오는 완전 차단 (토큰 갱신까지도 막음)
    _real_send_tele = TA.send_tele
    def _dry_send_tele(msg):
        print(f"\n  ========== [DRY-RUN TELEGRAM] ==========")
        print(msg)
        print(f"  ========== [END TELEGRAM] ==========\n")
    TA.send_tele = _dry_send_tele

    # KRFT_kakao 모듈 미리 mock 주입 (이후 import 시 실제 모듈 대신 사용됨)
    import types as _types
    _kakao_mock = _types.ModuleType("KRFT_kakao")
    def _dry_send_kakao(msg):
        print(f"  [DRY-RUN kakao] {msg[:200]}{'...' if len(msg)>200 else ''}")
        return True
    _kakao_mock.send_kakao_to_self = _dry_send_kakao
    sys.modules["KRFT_kakao"] = _kakao_mock

    print("⚠️  KRFT_DRY_RUN=1 — 주문/카카오/텔레그램은 실제로 발사되지 않습니다.")

# ------------------------------------------------------------------
# 경로 / 상수
# ------------------------------------------------------------------
TR_DIR              = "/var/autobot/TR_KRFT"
RESULT_PATH         = os.path.join(TR_DIR, "KRFT_result.json")
MONTHLY_PATH        = os.path.join(TR_DIR, "krfuture_monthly.json")

# KIS 선물 계좌 (userMemories: 64753341 / 03)
FUT_CANO            = "64753341"
FUT_ACNT_PRDT_CD    = "03"
FUT_KEY_FILE        = f"/var/autobot/KIS/kis{FUT_CANO}nkr.txt"
FUT_TOKEN_FILE      = f"/var/autobot/KIS/kis{FUT_CANO}_token.json"

# 선물 1계약 승수
K200_REG_MULT       = 250_000     # KOSPI200 정규: 지수 × 250,000원
K200_MINI_MULT      = 50_000      # 미니: 지수 × 50,000원
KQ150_MULT          = 10_000      # KOSDAQ150: 지수 × 10,000원 (참고: 실제로는 10,000)

# 정규 우선배분 임계비율 (지침 15: 90% 이상이면 1계약)
K200_REG_THRESHOLD_RATIO = 0.9

# 라운드 시간표 (KST, HH:MM:SS)
SIGNAL_SCHEDULE = [
    # (목표시각, 동작) — 동작은 _execute_signal_round에서 분기
    ("15:30:00", "round1_open"),     # 기존청산 1호가 + 신규 1호가
    ("15:30:30", "round2_refresh"),  # 호가 갱신
    ("15:31:00", "round3_refresh"),
    ("15:31:30", "round4_refresh"),
    ("15:32:00", "round5_close_mkt"),# 기존청산 미체결 → 시장가, 신규 계속 1호가
    ("15:32:30", "round6_refresh"),
    ("15:33:00", "round7_refresh"),
    ("15:33:30", "round8_refresh"),
    ("15:34:00", "round9_new_mkt"),  # 신규 미체결 → 시장가
]


# ==================================================================
#  KRFT_result.json 입출력
# ==================================================================
def load_result() -> dict:
    with open(RESULT_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def save_result(obj: dict) -> None:
    tmp = RESULT_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
    os.replace(tmp, RESULT_PATH)


# ==================================================================
#  현물 평가금 산출 (daily_snapshot 위임)
# ==================================================================
def calc_spot_eval_krw(result_cfg: dict) -> dict:
    """
    KRQT 100% + KRTR 90% 의 합산 (manual_config.spot_basis 가중치 반영).
    override 우선.

    Returns:
      {"krw": float, "source": "auto|manual",
       "krqt": float, "krtr": float}
    """
    cfg = result_cfg.get("manual_config", {})
    override = cfg.get("spot_eval_override")
    if override is not None and float(override) > 0:
        return {"krw": float(override), "source": "manual",
                "krqt": 0.0, "krtr": 0.0}

    krqt_w = float(cfg.get("spot_basis", {}).get("krqt_weight", 1.00))
    krtr_w = float(cfg.get("spot_basis", {}).get("krtr_weight", 0.90))

    # daily_snapshot 모듈 import (동일 EC2에서 작동 중)
    sys.path.insert(0, "/var/autobot/Balance")
    try:
        import daily_snapshot as DS
    except Exception as e:
        TA.send_tele(f"[KRFT] daily_snapshot import 실패: {e}")
        return {"krw": 0.0, "source": "error", "krqt": 0.0, "krtr": 0.0}

    krqt_total = 0.0
    krtr_total = 0.0
    for (market, strategy, sub, cano, acnt, handler_name, kwargs) in DS.ACCOUNTS:
        if market != "KR Market" or strategy not in ("KRQT", "KRTR"):
            continue
        handler = DS.HANDLERS.get(handler_name)
        if not handler:
            continue
        try:
            data = handler(cano, acnt, kwargs)
        except Exception as e:
            print(f"  [WARN] {strategy}/{sub} 조회 실패: {e}")
            continue
        tk = float(data.get("total_krw", 0) or 0)
        if strategy == "KRQT":
            krqt_total += tk
        else:
            krtr_total += tk

    spot = krqt_total * krqt_w + krtr_total * krtr_w
    return {
        "krw":   spot,
        "source": "auto",
        "krqt":  krqt_total,
        "krtr":  krtr_total,
    }


# ==================================================================
#  Hedge3 ↔ Hedge1 충돌 해소
# ==================================================================
def resolve_hedge_conflict(signals: dict, positions: dict) -> dict:
    """
    Hedge1 신호가 발생했고 Hedge3가 active 면, Hedge3를 흡수 종료.
    반환: signals 에 'hedge3_absorb' 키가 붙은 dict.
    """
    h1 = signals.get("hedge1", {})
    h3_pos = positions.get("hedge3", {})

    if h1.get("action") == "open" and h3_pos.get("active"):
        # Hedge3 매도 포지션이 이미 있음 → Hedge1 100%에서 흡수
        signals["hedge3_absorb"] = {
            "absorbed_ratio": h3_pos.get("ratio", 0.0),
            "msg": f"Hedge1 진입 → Hedge3({h3_pos.get('ratio')*100:.0f}%) 흡수 종료",
        }
    return signals


# ==================================================================
#  Hedge3 신호 산출 — daily 모드
# ==================================================================
def compute_hedge3_daily_signal(pbr: float, positions: dict) -> dict:
    """
    Hedge3 daily 신호 (요구사항 변경 후 신 버전):
      - 진입: PBR ≥ 2.4 즉시 30%, PBR ≥ 2.8 즉시 60%
      - 청산: 진입 후 갱신한 peak_pbr 의 2/3 이하로 떨어지면 즉시 (peak는 일별 갱신)
      - 흡수: Hedge1 진입 시 별도 처리 (run_signal_entry에서)

    Args:
      pbr:        오늘(또는 15:25 시점) KIS 환산 PBR
      positions:  result["positions"] (hedge3 현재 상태)

    Returns:
      {
        "action":   "open"|"scale_up"|"hold"|"close"|"none",
        "ratio":    float,           # 목표 비중 (close 시 0)
        "active":   bool,            # 목표 상태
        "peak_pbr": float,           # 갱신할 peak
        "reason":   str,
      }
    """
    pos = positions.get("hedge3", {}) or {}
    active = bool(pos.get("active", False))
    cur_ratio = float(pos.get("ratio", 0.0) or 0.0)
    cur_peak = float(pos.get("peak_pbr", 0.0) or 0.0)
    # 새 peak = max(기존 peak, 오늘 pbr)
    new_peak = max(cur_peak, pbr) if active or pbr >= 2.4 else cur_peak

    # 1) 청산 조건 (active 일 때만)
    if active and new_peak > 0 and pbr <= new_peak * (2.0 / 3.0):
        return {
            "action":   "close",
            "ratio":    0.0,
            "active":   False,
            "peak_pbr": 0.0,
            "reason":   f"Hedge3 청산: PBR {pbr:.4f} ≤ peak {new_peak:.4f}×2/3 "
                        f"= {new_peak*2/3:.4f}",
        }

    # 2) 목표 비중 결정 (단조 비감소)
    if pbr >= 2.8:
        target_ratio = 0.6
    elif pbr >= 2.4:
        target_ratio = 0.3
    else:
        target_ratio = 0.0

    # 3) 진입 / 증액 / 유지 / 미발동
    if not active and target_ratio > 0:
        return {
            "action":   "open",
            "ratio":    target_ratio,
            "active":   True,
            "peak_pbr": pbr,
            "reason":   f"Hedge3 진입: PBR {pbr:.4f} → {target_ratio*100:.0f}%",
        }

    if active and target_ratio > cur_ratio:
        return {
            "action":   "scale_up",
            "ratio":    target_ratio,
            "active":   True,
            "peak_pbr": new_peak,
            "reason":   f"Hedge3 증액: PBR {pbr:.4f}, "
                        f"{cur_ratio*100:.0f}% → {target_ratio*100:.0f}%",
        }

    if active:
        return {
            "action":   "hold",
            "ratio":    cur_ratio,
            "active":   True,
            "peak_pbr": new_peak,
            "reason":   f"Hedge3 유지 (PBR {pbr:.4f}, peak {new_peak:.4f}, "
                        f"비중 {cur_ratio*100:.0f}%)",
        }

    return {
        "action":   "none",
        "ratio":    0.0,
        "active":   False,
        "peak_pbr": cur_peak,
        "reason":   f"Hedge3 미발동 (PBR {pbr:.4f} < 2.4)",
    }


# ──────────────────────────────────────────────────────────
# 기존 월말 진입 시 사용되는 헬퍼 (signal 결과 dict 형식 변환)
# ──────────────────────────────────────────────────────────
def compute_hedge3_signal(monthly_data: dict, positions: dict,
                          current_ym: str) -> dict:
    """월말 진입 흐름에서 사용하는 wrapper (KRFT_TR.run_signal_entry 호출)"""
    rec = monthly_data.get(current_ym) or {}
    pbr = rec.get("kospi_pbr")
    if pbr is None:
        return {"action": "none", "reason": "PBR 데이터 없음",
                "ratio": 0.0, "active": False, "peak_pbr": 0.0}
    return compute_hedge3_daily_signal(float(pbr), positions)


# ==================================================================
#  목표 포지션 산출 (명목금액 → 계약수)
# ==================================================================
def split_k200_qty(target_notional: float, k200_idx: float) -> tuple[int, int]:
    """
    KOSPI200 명목금액을 정규/미니 계약수로 분배.

    Args:
      target_notional: 목표 K200측 명목금액 (원)
      k200_idx:        KOSPI200 지수 (현재가)

    Returns:
      (regular_qty, mini_qty)  부호는 호출자가 결정
    """
    if target_notional == 0 or k200_idx <= 0:
        return 0, 0

    reg_unit  = k200_idx * K200_REG_MULT     # 정규 1계약 명목금액
    mini_unit = k200_idx * K200_MINI_MULT    # 미니 1계약 명목금액

    abs_notional = abs(target_notional)
    sign = 1 if target_notional > 0 else -1

    # 1) 정규: 1계약 명목 × 0.9 이상이면 우선 배정
    if abs_notional >= reg_unit * K200_REG_THRESHOLD_RATIO:
        reg_qty = int(abs_notional // reg_unit)
    else:
        reg_qty = 0

    # 2) 잔여 → 미니로 반올림
    remain = abs_notional - reg_qty * reg_unit
    mini_qty = int(round(remain / mini_unit)) if mini_unit > 0 else 0

    return sign * reg_qty, sign * mini_qty


def calc_target_positions(signals: dict, spot_krw: float,
                          enabled: dict,
                          prices: dict) -> dict:
    """
    각 전략의 신호 + 비중 → 종목별 부호 있는 목표 계약수 계산.

    부호 규칙:
      - Boost 매수    : K200측 +
      - Hedge1 매도   : K200측 -, KQ150 -
      - Hedge2 매도   : KQ150 -
      - Hedge3 매도   : K200측 -, KQ150 -

    Args:
      prices: {"k200": float, "kq150": float}

    Returns:
      {
        "k200_regular": int,
        "k200_mini":    int,
        "kq150":        int,
        "breakdown":    {...}    # 전략별 기여도 (로깅용)
      }
    """
    k200_idx  = prices["k200"]
    kq150_idx = prices["kq150"]

    reg_total  = 0
    mini_total = 0
    kq_total   = 0
    breakdown  = {}

    # ── Boost ────────────────────────────────────────
    if enabled.get("boost", True):
        b = signals.get("boost", {})
        new_stage = b.get("new_stage", 0) or 0
        # 보유 중에는 "유지"라도 명목금액은 가지고 있음 → 현재 ratio 사용
        cur_ratio = b.get("new_ratio") if b.get("action") in ("open", "scale_up") \
                    else (b.get("hold_ratio") or 0)
        # KRFT_signal은 hold 시 ratio 안 줘서 result.json의 직전 ratio 사용 필요
        if b.get("action") in ("open", "scale_up"):
            target_ratio = b.get("new_ratio", 0.0)
        elif b.get("action") == "hold":
            target_ratio = b.get("_cur_ratio", 0.0)   # caller가 채움
        else:
            target_ratio = 0.0

        if target_ratio > 0:
            boost_notional = spot_krw * target_ratio
            r, m = split_k200_qty(+boost_notional, k200_idx)
            reg_total  += r
            mini_total += m
            breakdown["boost"] = {"ratio": target_ratio,
                                  "notional": boost_notional,
                                  "k200_reg": r, "k200_mini": m}

    # ── Hedge1 ──────────────────────────────────────
    if enabled.get("hedge1", True):
        h1 = signals.get("hedge1", {})
        if h1.get("action") in ("open", "hold") and h1.get("active"):
            ratio = h1.get("ratio", SIG.HEDGE1_NOTIONAL_RATIO)
            total_short = spot_krw * ratio
            k200_short = total_short / 2.0   # K200측 50%
            kq_short   = total_short / 2.0   # KQ150측 50%

            r, m = split_k200_qty(-k200_short, k200_idx)
            reg_total  += r
            mini_total += m

            kq_unit = kq150_idx * KQ150_MULT
            kq_qty = -int(round(kq_short / kq_unit)) if kq_unit > 0 else 0
            kq_total += kq_qty

            breakdown["hedge1"] = {"ratio": ratio, "notional": total_short,
                                   "k200_reg": r, "k200_mini": m, "kq150": kq_qty}

    # ── Hedge2 ──────────────────────────────────────
    if enabled.get("hedge2", False):
        h2 = signals.get("hedge2", {})
        if h2.get("action") in ("open", "hold") and h2.get("active"):
            ratio = h2.get("ratio", 0.0)
            kq_short = spot_krw * ratio
            kq_unit = kq150_idx * KQ150_MULT
            kq_qty = -int(round(kq_short / kq_unit)) if kq_unit > 0 else 0
            kq_total += kq_qty
            breakdown["hedge2"] = {"ratio": ratio, "notional": kq_short,
                                   "kq150": kq_qty}

    # ── Hedge3 ──────────────────────────────────────
    # (Hedge1과 동시 active 면 시그널 단계에서 흡수되어 hedge3.action='close'로 설정됨)
    if enabled.get("hedge3", True):
        h3 = signals.get("hedge3", {})
        if h3.get("action") in ("open", "hold", "scale_up") and h3.get("active"):
            ratio = h3.get("ratio", 0.0)
            total_short = spot_krw * ratio
            k200_short = total_short / 2.0
            kq_short   = total_short / 2.0

            r, m = split_k200_qty(-k200_short, k200_idx)
            reg_total  += r
            mini_total += m

            kq_unit = kq150_idx * KQ150_MULT
            kq_qty = -int(round(kq_short / kq_unit)) if kq_unit > 0 else 0
            kq_total += kq_qty

            breakdown["hedge3"] = {"ratio": ratio, "notional": total_short,
                                   "k200_reg": r, "k200_mini": m, "kq150": kq_qty}

    return {
        "k200_regular": reg_total,
        "k200_mini":    mini_total,
        "kq150":        kq_total,
        "breakdown":    breakdown,
    }


# ==================================================================
#  현재 보유 → 액션 분해 (close / open / hold)
# ==================================================================
def diff_positions(current: dict, target: dict, symbols: dict) -> list:
    """
    각 종목군별로 (current_signed_qty → target_signed_qty) 차이를 액션 리스트로 변환.

    signed: 매수 +, 매도 -

    return: [
      {"kind": "close|open", "symbol": str, "side": "BUY|SELL",
       "qty": int, "group": "k200_regular|k200_mini|kq150"}
    ]
    """
    actions = []
    for group in ("k200_regular", "k200_mini", "kq150"):
        cur = int(current.get(group, 0))
        tgt = int(target.get(group, 0))
        symbol = symbols.get(group)
        if not symbol or cur == tgt:
            continue

        # 부호가 같으면 단순 증감, 다르면 (전량청산 + 신규반대) 2 액션
        if cur * tgt >= 0:
            diff = tgt - cur
            if diff == 0:
                continue
            side = "BUY" if diff > 0 else "SELL"
            # 청산 vs 신규 구분: |tgt| < |cur| 면 청산, 그 외 신규
            if abs(tgt) < abs(cur):
                kind = "close"
            else:
                kind = "open"
            actions.append({
                "kind":   kind,
                "symbol": symbol,
                "side":   side,
                "qty":    abs(diff),
                "group":  group,
            })
        else:
            # 부호 반전 → 1) 현 포지션 전량 청산  2) 반대방향 신규
            close_side = "SELL" if cur > 0 else "BUY"
            actions.append({
                "kind":   "close",
                "symbol": symbol,
                "side":   close_side,
                "qty":    abs(cur),
                "group":  group,
            })
            new_side = "BUY" if tgt > 0 else "SELL"
            actions.append({
                "kind":   "open",
                "symbol": symbol,
                "side":   new_side,
                "qty":    abs(tgt),
                "group":  group,
            })
    return actions


# ==================================================================
#  증거금 체크
# ==================================================================
def check_margin(kis, actions: list, prices: dict) -> dict:
    """
    각 신규(open) 액션의 ord_psbl_qty 합산으로 증거금 충분성 검증.
    부족 시 부족 명목금액(원)을 환산해 반환.

    Args:
      actions: diff_positions 출력
      prices : {"k200": float, "kq150": float}

    Returns:
      {"ok": bool, "shortage_krw": float, "details": [...]}
    """
    details = []
    shortage = 0.0
    # 신규(open) 액션만 증거금 영향 (청산은 증거금 해제)
    for a in actions:
        if a["kind"] != "open" or a["qty"] <= 0:
            continue
        symbol = a["symbol"]
        # 호가에서 매수/매도 1호가 가격을 가져와 주문가 추정
        ob = ORDER.get_futures_orderbook(kis, symbol)
        if not ob:
            details.append(f"{symbol} 호가조회실패 → 증거금 검증 보류")
            continue
        price = ob["ask1"] if a["side"] == "BUY" else ob["bid1"]
        if price <= 0:
            cur = ORDER.get_futures_price(kis, symbol)
            price = cur["price"] if cur else 0
        if price <= 0:
            details.append(f"{symbol} 가격조회실패")
            continue

        side_code = ORDER.SIDE_BUY if a["side"] == "BUY" else ORDER.SIDE_SELL
        orderable = ORDER.get_futures_orderable(kis, symbol, price,
                                                side=side_code, cls=ORDER.CLS_OPEN)
        if not orderable:
            details.append(f"{symbol} 주문가능조회실패")
            continue

        psbl = orderable["ord_psbl_qty"]
        need = a["qty"]
        details.append(f"{symbol} {a['side']} {a['kind']}: 필요 {need} / 가능 {psbl}")

        if psbl < need:
            short_qty = need - psbl
            # 명목금액 환산: K200 정규 = price*250000 / 미니 = price*50000 / KQ150 = price*250000
            if a["group"] == "k200_regular":
                mult = K200_REG_MULT
            elif a["group"] == "k200_mini":
                mult = K200_MINI_MULT
            else:
                mult = KQ150_MULT
            shortage += short_qty * price * mult

    return {
        "ok":           shortage <= 0,
        "shortage_krw": shortage,
        "details":      details,
    }


# ==================================================================
#  주문 실행 (라운드별)
# ==================================================================
def _kst_now() -> datetime:
    return datetime.now(pytz.timezone("Asia/Seoul"))


def _sleep_until(hhmmss: str) -> None:
    """KST 기준 목표 시각까지 sleep (DRY_RUN 일 때는 즉시 통과)"""
    if DRY_RUN:
        print(f"  [DRY-RUN] _sleep_until({hhmmss}) → skip")
        return
    now = _kst_now()
    h, m, s = [int(x) for x in hhmmss.split(":")]
    tgt = now.replace(hour=h, minute=m, second=s, microsecond=0)
    if tgt < now:
        return
    delta = (tgt - now).total_seconds()
    if delta > 0:
        time.sleep(delta)


def _place_orders_with_first_quote(kis, actions: list, log: list) -> list:
    """
    각 액션마다 1호가 지정가로 주문.
    1호가가 0이거나 비어있으면 2호가, 3호가까지 fallback.
    Returns: 주문 결과 리스트 [{"action": a, "order_no": str, "org_orgno": str, "price": float}]
    """
    placed = []
    for a in actions:
        if a["qty"] <= 0:
            continue
        ob = ORDER.get_futures_orderbook(kis, a["symbol"])
        if not ob:
            log.append(f"  [SKIP] {a['symbol']} 호가조회실패")
            continue
        # BUY → 매도호가(ask), SELL → 매수호가(bid)
        price = ob["ask1"] if a["side"] == "BUY" else ob["bid1"]

        # 1호가가 0이면 5단 호가 조회 후 fallback
        if price <= 0:
            ob5 = ORDER.get_futures_orderbook_full(kis, a["symbol"])
            if ob5:
                target = ob5["asks"] if a["side"] == "BUY" else ob5["bids"]
                for p, q in target:
                    if p > 0:
                        price = p
                        log.append(f"  [QUOTE-FB] {a['symbol']} 1호가 0 → 다음 호가 {p}")
                        break
            # 그래도 0이면 현재가
            if price <= 0:
                cur = ORDER.get_futures_price(kis, a["symbol"])
                if cur and cur["price"] > 0:
                    price = cur["price"]
                    log.append(f"  [QUOTE-FB] {a['symbol']} 호가전체 0 → 현재가 {price}")

        if price <= 0:
            log.append(f"  [SKIP] {a['symbol']} 가격 0 (호가/현재가 모두 부재)")
            continue

        side = ORDER.SIDE_BUY if a["side"] == "BUY" else ORDER.SIDE_SELL
        cls  = ORDER.CLS_OPEN if a["kind"] == "open" else ORDER.CLS_CLOSE
        r = ORDER.order_futures(kis, a["symbol"], a["qty"], price,
                                side=side, cls=cls, market_order=False)
        if r and r.get("ok"):
            log.append(f"  [ORD] {a['symbol']} {a['side']} {a['kind']} "
                       f"{a['qty']}계약 @ {price} → {r['order_no']}")
            placed.append({"action": a, "order_no": r["order_no"],
                           "org_orgno": r["org_orgno"], "price": price})
        else:
            msg = r.get("msg") if r else "no-response"
            log.append(f"  [ERR] {a['symbol']} 주문실패: {msg}")
        time.sleep(0.2)
    return placed


def _refresh_unfilled_to_first_quote(kis, log: list) -> None:
    """미체결을 취소 → 현 1호가로 재주문"""
    unfilled = ORDER.get_unfilled(kis)
    if not unfilled:
        return
    for u in unfilled:
        # 우선 취소
        c = ORDER.cancel_order(kis, u["org_orgno"], u["order_no"], qty=0)
        if not (c and c.get("ok")):
            log.append(f"  [REFRESH-FAIL] 취소실패 {u['order_no']}: "
                       f"{c.get('msg') if c else 'no-response'}")
            continue
        time.sleep(0.3)
        # 현 1호가 재조회
        ob = ORDER.get_futures_orderbook(kis, u["symbol"])
        if not ob:
            log.append(f"  [REFRESH-FAIL] {u['symbol']} 호가조회실패")
            continue
        side_code = u["side"]   # '01' or '02'
        price = ob["ask1"] if side_code == ORDER.SIDE_BUY else ob["bid1"]
        if price <= 0:
            continue
        # 신규/청산 구분은 원주문에서 알 수 없으니 보수적으로 청산 우선 → 실패 시 신규
        # (실무적으로 1라운드 발주 후 동일 액션이 미체결 상태이므로 같은 cls로 가정)
        r = ORDER.order_futures(kis, u["symbol"], u["rem_qty"], price,
                                side=side_code, cls=ORDER.CLS_CLOSE,
                                market_order=False)
        if not (r and r.get("ok")):
            r = ORDER.order_futures(kis, u["symbol"], u["rem_qty"], price,
                                    side=side_code, cls=ORDER.CLS_OPEN,
                                    market_order=False)
        log.append(f"  [REFRESH] {u['symbol']} 잔량 {u['rem_qty']} @ {price} "
                   f"→ {r.get('order_no','-') if r else 'fail'}")
        time.sleep(0.2)


def _market_order_unfilled(kis, only_kind: str, log: list) -> None:
    """
    미체결을 시장가로 전환.
    only_kind: 'close' 면 청산 미체결만, 'open' 이면 신규 미체결만, None이면 전부
    (현재 KIS 미체결 조회로는 신규/청산 구분 필드 없음 → 전부 시장가 처리)
    """
    unfilled = ORDER.get_unfilled(kis)
    if not unfilled:
        return
    for u in unfilled:
        c = ORDER.cancel_order(kis, u["org_orgno"], u["order_no"], qty=0)
        if not (c and c.get("ok")):
            log.append(f"  [MKT-FAIL] 취소실패 {u['order_no']}")
            continue
        time.sleep(0.3)
        # 시장가 — 청산/신규 모두 시도 (KIS는 cls 구분 없이 잔고 기준 자동처리)
        r = ORDER.order_futures(kis, u["symbol"], u["rem_qty"], 0,
                                side=u["side"], cls=ORDER.CLS_CLOSE,
                                market_order=True)
        if not (r and r.get("ok")):
            r = ORDER.order_futures(kis, u["symbol"], u["rem_qty"], 0,
                                    side=u["side"], cls=ORDER.CLS_OPEN,
                                    market_order=True)
        log.append(f"  [MKT] {u['symbol']} 시장가 {u['rem_qty']}계약 "
                   f"→ {r.get('order_no','-') if r else 'fail'}")
        time.sleep(0.2)


# ==================================================================
#  보유 포지션 동기화 (실제 KIS 잔고 → result.json holdings)
# ==================================================================
def _sync_holdings_from_balance(result: dict, balance: dict,
                                symbols: dict) -> None:
    """KIS 잔고로 result['holdings'] 갱신"""
    pos_map = {p["symbol"]: p for p in balance.get("positions", [])}

    for group in ("k200_regular", "k200_mini", "kq150"):
        sym = symbols.get(group)
        p = pos_map.get(sym, {})
        result["holdings"][group] = {
            "symbol":    sym,
            "qty":       int(p.get("qty", 0)),
            "side":      p.get("side"),
            "avg_price": float(p.get("avg_price", 0) or 0),
        }


def _signed_current_from_holdings(result: dict) -> dict:
    """holdings 의 (symbol, qty, side) → 부호 있는 정수로 변환"""
    out = {}
    for group in ("k200_regular", "k200_mini", "kq150"):
        h = result["holdings"].get(group, {}) or {}
        qty = int(h.get("qty", 0) or 0)
        side = h.get("side")
        out[group] = -qty if side == "short" else qty
    return out


# ==================================================================
#  메인: 월말 진입 (run_signal_entry)
# ==================================================================
def run_signal_entry() -> None:
    """매월 말 거래일 15:25부터 실행되는 메인 함수."""
    log = []
    today = _kst_now().date()
    log.append(f"=== KRFT 월말 진입 시작: {today} ===")

    # 1) KIS 초기화
    try:
        kis = KIS_API(FUT_KEY_FILE, FUT_TOKEN_FILE, FUT_CANO, FUT_ACNT_PRDT_CD)
    except SystemExit:
        TA.send_tele("[KRFT] KIS 초기화 실패 — 종료")
        return
    except Exception as e:
        TA.send_tele(f"[KRFT] KIS 초기화 예외: {e}")
        return

    # 2) result.json 로드
    result = load_result()
    cfg = result.get("manual_config", {})
    enabled = cfg.get("strategy_enabled", {})

    # 3) 현물 평가금
    spot = calc_spot_eval_krw(result)
    spot_krw = spot["krw"]
    log.append(f"현물평가금: {spot_krw:,.0f}원 (KRQT {spot['krqt']:,.0f} + "
               f"KRTR {spot['krtr']:,.0f} × 가중) [{spot['source']}]")
    if spot_krw <= 0:
        TA.send_tele("[KRFT] 현물평가금 0 — 종료")
        return

    result["spot_eval_krw"]   = spot_krw
    result["spot_eval_source"] = spot["source"]
    result["spot_eval_breakdown"] = {
        "spot_eval_krw":  spot_krw,
        "krqt_total_krw": spot["krqt"],
        "krtr_total_krw": spot["krtr"],
        "source":         spot["source"],
        "computed_at":    datetime.now().isoformat(timespec="seconds"),
    }

    # 4) 월말 데이터 수집 (monthly.json 업데이트)
    data_res = DATA.update_monthly_data(
        kis, today,
        pbr_override=cfg.get("pbr_override"),
        vkospi_override=cfg.get("vkospi_override"),
    )
    log.extend("  [DATA] " + m for m in data_res.get("messages", []))
    if not data_res["ok"]:
        TA.send_tele("[KRFT] 데이터 수집 실패:\n" +
                     "\n".join(data_res["messages"]))
        return
    log.append(f"  KOSPI={data_res['kospi']:.2f} KOSDAQ={data_res['kosdaq']:.2f} "
               f"PBR={data_res['kospi_pbr']:.3f} VKOSPI={data_res['vkospi']:.2f}")

    # 5) 시그널 계산 (KRFT_signal.py)
    # KRFT_signal.py 는 monthly.json 의 positions 를 보므로 result.json positions 와 동기화
    monthly = DATA.load_monthly()
    monthly["positions"] = {
        "boost":  result["positions"]["boost"],
        "hedge1": result["positions"]["hedge1"],
        "hedge2": result["positions"]["hedge2"],
    }
    DATA.save_monthly(monthly)

    signals = SIG.compute_signals(MONTHLY_PATH, target_ym=today.strftime("%Y-%m"))

    # 5-1) Hedge3 자체 신호 (signal 모듈에 없으므로 별도 계산)
    h3_sig = compute_hedge3_signal(monthly["data"], result["positions"],
                                    today.strftime("%Y-%m"))
    signals["hedge3"] = h3_sig

    # 5-2) Hedge3 ↔ Hedge1 충돌 해소: Hedge1 open 시 Hedge3 강제 close
    if signals["hedge1"].get("action") == "open" and \
       result["positions"]["hedge3"].get("active"):
        h3_sig["action"] = "close"
        h3_sig["active"] = False
        h3_sig["reason"] = "Hedge1 진입 흡수로 Hedge3 종료"

    # 5-3) Boost hold 시 현재 ratio 채워주기 (목표수량 산출용)
    if signals["boost"].get("action") == "hold":
        signals["boost"]["_cur_ratio"] = result["positions"]["boost"].get("ratio", 0)

    for name in ("boost", "hedge1", "hedge2", "hedge3"):
        s = signals.get(name, {})
        en = "ON " if enabled.get(name, True) else "OFF"
        log.append(f"  [SIG-{en}] {name:6s} action={s.get('action'):8s} | {s.get('reason')}")

    # 6) 현재가 조회 (목표수량 산출용)
    symbols = SYM.get_current_symbols(today)
    cur_k200 = ORDER.get_futures_price(kis, symbols["k200_regular"])
    cur_kq   = ORDER.get_futures_price(kis, symbols["kq150"])
    if not cur_k200 or not cur_kq:
        TA.send_tele("[KRFT] 선물 현재가 조회 실패 — 종료")
        return
    prices = {"k200": cur_k200["price"], "kq150": cur_kq["price"]}
    log.append(f"  선물지수: K200={prices['k200']:.2f} KQ150={prices['kq150']:.2f}")

    # 7) 목표 포지션 계산
    target = calc_target_positions(signals, spot_krw, enabled, prices)
    log.append(f"  [TARGET] K200정규={target['k200_regular']} "
               f"미니={target['k200_mini']} KQ150={target['kq150']}")
    for strat, br in target["breakdown"].items():
        log.append(f"    · {strat}: {br}")

    # 8) 현재 보유 동기화
    bal = ORDER.get_futures_balance(kis)
    if not bal:
        TA.send_tele("[KRFT] 선물 잔고 조회 실패 — 종료")
        return
    _sync_holdings_from_balance(result, bal, symbols)
    current = _signed_current_from_holdings(result)
    log.append(f"  [현재보유] K200정규={current['k200_regular']} "
               f"미니={current['k200_mini']} KQ150={current['kq150']}")
    log.append(f"  예수금 dnca_cash={bal['dnca_cash']:,.0f}원 / "
               f"추정예탁={bal['prsm_dpast_amt']:,.0f}원 / "
               f"증거금={bal['mgna_tota']:,.0f}원")

    # 9) 액션 분해
    actions = diff_positions(current, target, symbols)
    if not actions:
        log.append("  변동 없음 — 매매 미실행")
        result["last_run"] = {
            "date": today.isoformat(), "type": "signal_entry",
            "signals": signals, "orders": [], "status": "no_change",
        }
        save_result(result)
        TA.send_tele("[KRFT] " + "\n".join(log))
        return

    for a in actions:
        log.append(f"  [ACTION] {a['kind']:5s} {a['side']} "
                   f"{a['symbol']} ({a['group']}) {a['qty']}계약")

    # 10) 증거금 체크
    margin = check_margin(kis, actions, prices)
    log.append(f"  [MARGIN] ok={margin['ok']} 부족={margin['shortage_krw']:,.0f}원")
    for d in margin["details"]:
        log.append(f"    · {d}")
    if not margin["ok"]:
        msg = (f"⚠️ 증거금 {margin['shortage_krw']:,.0f}원 부족 "
               f"(현물의 {margin['shortage_krw']/spot_krw*100:.1f}%) "
               f"및 내일 다시 매매")
        log.append(msg)
        TA.send_tele("[KRFT] " + "\n".join(log))
        # 카카오 — 증거금 부족 시에만
        if cfg.get("kakao_alert_enabled", True):
            try:
                import KRFT_kakao
                KRFT_kakao.send_kakao_to_self("[KRFT 증거금 부족]\n" + msg)
            except Exception as e:
                TA.send_tele(f"[KRFT] 카카오 전송 실패: {e}")
        result["last_run"] = {
            "date": today.isoformat(), "type": "signal_entry",
            "signals": signals, "orders": [],
            "status": f"margin_short_{int(margin['shortage_krw'])}",
        }
        save_result(result)
        return

    # 11) 라운드별 주문 실행
    close_actions = [a for a in actions if a["kind"] == "close"]
    open_actions  = [a for a in actions if a["kind"] == "open"]
    log.append(f"\n=== 라운드 실행 시작 (청산 {len(close_actions)}건 + "
               f"신규 {len(open_actions)}건) ===")

    placed_records = []

    # R1: 15:30:00 — 청산 1호가 + 신규 1호가 동시 발주
    _sleep_until("15:30:00")
    log.append(f"\n[{_kst_now().strftime('%H:%M:%S')}] R1 청산/신규 1호가 발주")
    if close_actions:
        placed_records += _place_orders_with_first_quote(kis, close_actions, log)
    if open_actions:
        placed_records += _place_orders_with_first_quote(kis, open_actions, log)

    # R2~R4: 15:30:30 / 15:31:00 / 15:31:30 — 호가 갱신
    for hhmmss in ("15:30:30", "15:31:00", "15:31:30"):
        _sleep_until(hhmmss)
        log.append(f"\n[{_kst_now().strftime('%H:%M:%S')}] 호가갱신")
        _refresh_unfilled_to_first_quote(kis, log)

    # R5: 15:32:00 — 청산 미체결만 시장가 (신규는 1호가 유지)
    _sleep_until("15:32:00")
    log.append(f"\n[{_kst_now().strftime('%H:%M:%S')}] R5 청산 시장가 전환")
    # close 액션의 symbol/side 만 시장가 전환
    close_keys = {(a["symbol"], a["side"]) for a in close_actions}
    unfilled_now = ORDER.get_unfilled(kis)
    for u in unfilled_now:
        u_side_str = "BUY" if u["side"] == ORDER.SIDE_BUY else "SELL"
        if (u["symbol"], u_side_str) not in close_keys:
            continue
        c = ORDER.cancel_order(kis, u["org_orgno"], u["order_no"], qty=0)
        if not (c and c.get("ok")):
            continue
        time.sleep(0.3)
        r = ORDER.order_futures(kis, u["symbol"], u["rem_qty"], 0,
                                side=u["side"], cls=ORDER.CLS_CLOSE,
                                market_order=True)
        log.append(f"  [MKT-CLOSE] {u['symbol']} {u['rem_qty']}계약 "
                   f"→ {r.get('order_no','-') if r else 'fail'}")
        time.sleep(0.2)

    # R6~R8: 15:32:30 / 15:33:00 / 15:33:30 — 신규 미체결 호가 갱신
    for hhmmss in ("15:32:30", "15:33:00", "15:33:30"):
        _sleep_until(hhmmss)
        log.append(f"\n[{_kst_now().strftime('%H:%M:%S')}] 신규 호가갱신")
        _refresh_unfilled_to_first_quote(kis, log)

    # R9: 15:34:00 — 신규 미체결 시장가
    _sleep_until("15:34:00")
    log.append(f"\n[{_kst_now().strftime('%H:%M:%S')}] R9 신규 시장가 전환")
    open_keys = {(a["symbol"], a["side"]) for a in open_actions}
    unfilled_now = ORDER.get_unfilled(kis)
    for u in unfilled_now:
        u_side_str = "BUY" if u["side"] == ORDER.SIDE_BUY else "SELL"
        if (u["symbol"], u_side_str) not in open_keys:
            continue
        c = ORDER.cancel_order(kis, u["org_orgno"], u["order_no"], qty=0)
        if not (c and c.get("ok")):
            continue
        time.sleep(0.3)
        r = ORDER.order_futures(kis, u["symbol"], u["rem_qty"], 0,
                                side=u["side"], cls=ORDER.CLS_OPEN,
                                market_order=True)
        log.append(f"  [MKT-OPEN] {u['symbol']} {u['rem_qty']}계약 "
                   f"→ {r.get('order_no','-') if r else 'fail'}")
        time.sleep(0.2)

    # 12) 잔고 재조회 → 포지션 동기화 → result.json 저장
    time.sleep(3)
    bal2 = ORDER.get_futures_balance(kis)
    if bal2:
        _sync_holdings_from_balance(result, bal2, symbols)

    # positions 갱신 — KRFT_signal.update_positions 사용
    SIG.update_positions(MONTHLY_PATH, signals)
    monthly2 = DATA.load_monthly()
    result["positions"]["boost"]  = monthly2["positions"]["boost"]
    result["positions"]["hedge1"] = monthly2["positions"]["hedge1"]
    result["positions"]["hedge2"] = monthly2["positions"]["hedge2"]

    # Hedge3 별도 갱신
    h3 = signals["hedge3"]
    today_iso = today.isoformat()
    if h3["action"] in ("open", "scale_up"):
        result["positions"]["hedge3"] = {
            "active":     True,
            "entry_date": today_iso if h3["action"] == "open"
                          else result["positions"]["hedge3"].get("entry_date", today_iso),
            "ratio":      h3["ratio"],
            "peak_pbr":   h3.get("peak_pbr", data_res["kospi_pbr"]),
            "entry_pbr":  result["positions"]["hedge3"].get("entry_pbr", data_res["kospi_pbr"])
                          if h3["action"] == "scale_up" else data_res["kospi_pbr"],
            "_note":      "Hedge3 종료: peak_pbr×2/3 이하 즉시 OR Hedge1 진입 시 자동 흡수",
        }
    elif h3["action"] == "close":
        result["positions"]["hedge3"] = {
            "active": False, "entry_date": None, "ratio": 0.0,
            "peak_pbr": 0.0, "entry_pbr": 0.0,
            "_note": "Hedge3 종료: peak_pbr×2/3 이하 즉시 OR Hedge1 진입 시 자동 흡수",
        }
    elif h3["action"] == "hold":
        # peak 갱신만
        result["positions"]["hedge3"]["peak_pbr"] = h3.get("peak_pbr",
            result["positions"]["hedge3"].get("peak_pbr", 0))

    result["last_run"] = {
        "date":    today.isoformat(),
        "type":    "signal_entry",
        "signals": signals,
        "orders":  [{"action": p["action"], "order_no": p["order_no"],
                     "price": p["price"]} for p in placed_records],
        "status":  "completed",
    }
    result["trade_history"].append({
        "date":   today.isoformat(),
        "type":   "signal_entry",
        "actions": actions,
        "spot_krw": spot_krw,
    })
    # 최근 200건만 보관
    result["trade_history"] = result["trade_history"][-200:]
    save_result(result)

    log.append(f"\n=== 완료: {_kst_now().strftime('%H:%M:%S')} ===")
    TA.send_tele("[KRFT 월말진입]\n" + "\n".join(log))


# ==================================================================
#  메인: 롤오버 (run_rollover)
# ==================================================================
def run_rollover() -> None:
    """선물 만기일 15:15부터 롤오버 실행."""
    log = []
    today = _kst_now().date()
    log.append(f"=== KRFT 롤오버 시작: {today} ===")

    targets = SYM.get_rollover_targets(today)
    active_targets = {k: v for k, v in targets.items() if v}
    if not active_targets:
        log.append("롤오버 대상 없음 — 종료")
        TA.send_tele("\n".join(log))
        return

    for k, v in active_targets.items():
        log.append(f"  대상 {k}: {v['from']} → {v['to']}")

    try:
        kis = KIS_API(FUT_KEY_FILE, FUT_TOKEN_FILE, FUT_CANO, FUT_ACNT_PRDT_CD)
    except Exception as e:
        TA.send_tele(f"[KRFT 롤오버] KIS 초기화 실패: {e}")
        return

    # 1) 현재 잔고에서 청산해야 할 from 종목 수량 파악
    bal = ORDER.get_futures_balance(kis)
    if not bal:
        TA.send_tele("[KRFT 롤오버] 잔고 조회 실패")
        return

    pos_map = {p["symbol"]: p for p in bal["positions"]}
    rollover_actions = []
    for group, t in active_targets.items():
        p = pos_map.get(t["from"])
        if not p or p["qty"] == 0:
            log.append(f"  {group} {t['from']} 보유 없음 — 스킵")
            continue
        # 현재 from을 반대매매로 청산 + to를 동일방향으로 신규
        close_side = "SELL" if p["side"] == "long" else "BUY"
        open_side  = "BUY"  if p["side"] == "long" else "SELL"
        rollover_actions.append({
            "kind": "close", "symbol": t["from"], "side": close_side,
            "qty": p["qty"], "group": group,
        })
        rollover_actions.append({
            "kind": "open",  "symbol": t["to"],   "side": open_side,
            "qty": p["qty"], "group": group,
        })
        log.append(f"  {group}: {p['side']} {p['qty']}계약 "
                   f"{t['from']}({close_side}청산) → {t['to']}({open_side}신규)")

    if not rollover_actions:
        log.append("실행할 롤오버 액션 없음")
        TA.send_tele("[KRFT 롤오버]\n" + "\n".join(log))
        return

    # 2) 15:15:30 — 첫 호가 발주
    _sleep_until("15:15:30")
    log.append(f"\n[{_kst_now().strftime('%H:%M:%S')}] 1호가 발주")
    _place_orders_with_first_quote(kis, rollover_actions, log)

    # 3) 30초 후 — 미체결 시장가 전환
    _sleep_until("15:16:00")
    log.append(f"\n[{_kst_now().strftime('%H:%M:%S')}] 미체결 시장가 전환")
    _market_order_unfilled(kis, only_kind=None, log=log)

    # 4) 결과 저장
    time.sleep(3)
    bal2 = ORDER.get_futures_balance(kis)
    result = load_result()
    if bal2:
        # 롤오버 후 종목코드가 to로 바뀌므로 symbols도 갱신
        symbols_new = SYM.get_current_symbols(today + timedelta(days=1))
        _sync_holdings_from_balance(result, bal2, symbols_new)

    result["last_run"] = {
        "date":    today.isoformat(),
        "type":    "rollover",
        "signals": None,
        "orders":  [{"from": v["from"], "to": v["to"]} for v in active_targets.values()],
        "status":  "completed",
    }
    result["trade_history"].append({
        "date":    today.isoformat(),
        "type":    "rollover",
        "actions": rollover_actions,
    })
    result["trade_history"] = result["trade_history"][-200:]
    save_result(result)

    log.append(f"\n=== 롤오버 완료: {_kst_now().strftime('%H:%M:%S')} ===")
    TA.send_tele("[KRFT 롤오버]\n" + "\n".join(log))


# ==================================================================
#  메인: Hedge3 daily 모드 (run_hedge3_daily)
# ==================================================================
def run_hedge3_daily() -> dict:
    """
    Hedge3 ON 상태에서 평일 15:25 ~ 15:34 동안 실행되는 일별 매매.

    동작:
      1) 15:25 데이터 수집 (KIS KOSPI/KOSDAQ/VKOSPI + KRX PBR 환산)
      2) compute_hedge3_daily_signal() → action 결정
      3) action 별 처리:
         - open/scale_up: 신규 매도 진입 (현물의 30% 또는 50%)
         - close: 보유 Hedge3 환매수 청산
         - hold/none: 매매 없음, peak_pbr만 갱신
      4) daily_pbr 기록
      5) snapshots.prev_day 갱신

    Returns:
      {
        "ok": bool,
        "executed": bool,           # 실제 매매가 발생했는지
        "action": str,
        "pbr": float,
        "pnl": float,               # 현재 평가손익
        "context": dict,            # KRFT_notify가 사용할 컨텍스트
      }
    """
    log = []
    today = _kst_now().date()
    log.append(f"=== Hedge3 daily: {today} ===")

    # 1) KIS 초기화
    try:
        kis = KIS_API(FUT_KEY_FILE, FUT_TOKEN_FILE, FUT_CANO, FUT_ACNT_PRDT_CD)
    except Exception as e:
        return {"ok": False, "executed": False,
                "error": f"KIS init: {e}"}

    # 2) result.json 로드
    result = load_result()
    cfg = result.get("manual_config", {})

    # 3) 15:25 시점 데이터 수집
    ctx = DATA.get_daily_market_context(
        kis,
        pbr_override=cfg.get("pbr_override"),
    )
    if not ctx["ok"]:
        log.extend("  " + m for m in ctx["messages"])
        return {"ok": False, "executed": False,
                "error": "data context fail", "log": log}

    pbr   = ctx["kospi_pbr"]
    kospi = ctx["kospi"]
    log.append(f"  PBR={pbr:.4f} KOSPI={kospi:.2f} KOSDAQ={ctx['kosdaq']:.2f} "
               f"VKOSPI={ctx['vkospi']:.2f}")

    # 4) PBR 일별 기록 (active 시에만 — 미발동 상태일 땐 노이즈)
    if result["positions"]["hedge3"].get("active") or pbr >= 2.4:
        DATA.append_daily_pbr_to_result(result, today, pbr, kospi)

    # 5) 시그널 계산
    sig = compute_hedge3_daily_signal(pbr, result["positions"])
    log.append(f"  [SIG] action={sig['action']} | {sig['reason']}")

    # 6) 보유 잔고 조회 (PNL/포지션)
    bal = ORDER.get_futures_balance(kis)
    if not bal:
        log.append("  [WARN] 잔고 조회 실패")

    # 7) action 분기
    executed = False
    orders_placed = []

    symbols = SYM.get_current_symbols(today)

    if sig["action"] in ("open", "scale_up", "close"):
        spot = calc_spot_eval_krw(result)
        spot_krw = spot["krw"]
        log.append(f"  현물평가금: {spot_krw:,.0f}원 "
                   f"(KRQT {spot['krqt']:,.0f} + KRTR {spot['krtr']:,.0f} × 가중) "
                   f"[{spot['source']}]")
        if spot_krw <= 0:
            log.append("  [ERR] 현물평가금 0 — 매매 보류")
            return {"ok": False, "executed": False, "log": log,
                    "context": ctx}

        # ── [SAFETY] 직전 spot_krw 대비 급변 감지 (리밸런싱 직후 데이터 누락 대비) ──
        prev_bd = result.get("spot_eval_breakdown", {})
        prev_spot = float(prev_bd.get("spot_eval_krw", 0) or 0)
        if prev_spot > 0:
            change_pct = (spot_krw - prev_spot) / prev_spot * 100
            if abs(change_pct) >= 30.0:
                msg = (
                    f"⚠️ spot_krw 급변 {change_pct:+.1f}% — Hedge3 매매 보류\n"
                    f"  직전: {prev_spot:,.0f} (@ {prev_bd.get('computed_at','?')})\n"
                    f"  현재: {spot_krw:,.0f}\n"
                    f"  KRQT: {spot['krqt']:,.0f} / KRTR: {spot['krtr']:,.0f}\n"
                    f"  리밸런싱 직후 daily_snapshot 매핑 누락 가능성 확인 필요"
                )
                log.append("  [SAFETY] " + msg.replace("\n", "\n  "))
                TA.send_tele("[KRFT Hedge3 SAFETY]\n" + msg)
                return {"ok": False, "executed": False, "log": log,
                        "context": ctx, "safety_block": True}

        # ── spot_eval_breakdown 갱신 (daily 모드에서도 디버깅 가능하도록) ──
        result["spot_eval_breakdown"] = {
            "spot_eval_krw":  spot_krw,
            "krqt_total_krw": spot["krqt"],
            "krtr_total_krw": spot["krtr"],
            "source":         spot["source"],
            "computed_at":    datetime.now().isoformat(timespec="seconds"),
        }
        result["spot_eval_krw"]    = spot_krw
        result["spot_eval_source"] = spot["source"]

        # 현재가 조회
        cur_k200 = ORDER.get_futures_price(kis, symbols["k200_regular"])
        cur_kq   = ORDER.get_futures_price(kis, symbols["kq150"])
        if not cur_k200 or not cur_kq:
            log.append("  [ERR] 선물가격 조회 실패")
            return {"ok": False, "executed": False, "log": log,
                    "context": ctx}
        prices = {"k200": cur_k200["price"], "kq150": cur_kq["price"]}

        # 보유 동기화
        if bal:
            _sync_holdings_from_balance(result, bal, symbols)
        current = _signed_current_from_holdings(result)

        # 목표 포지션: Hedge3 단독 계산 (다른 전략은 daily에서 건드리지 않음)
        # target = current + (Hedge3 의도 변화)
        h3_pos = result["positions"]["hedge3"]
        cur_h3_ratio = float(h3_pos.get("ratio", 0))
        new_h3_ratio = sig["ratio"]
        delta_ratio = new_h3_ratio - cur_h3_ratio
        log.append(f"  Hedge3 비중: {cur_h3_ratio:.2f} → {new_h3_ratio:.2f} "
                   f"(Δ {delta_ratio:+.2f})")

        if abs(delta_ratio) >= 0.0001:
            # K200측 (50%) + KQ150측 (50%) 분배
            delta_notional = spot_krw * delta_ratio  # 양수면 매도 증가(+short), 음수면 감소
            k200_delta = delta_notional / 2.0
            kq_delta   = delta_notional / 2.0

            # 매도 = - 부호, 매수 = + 부호. delta>0 이면 추가 매도 필요 → split 입력은 -k200_delta
            r, m = split_k200_qty(-k200_delta, prices["k200"])
            kq_unit = prices["kq150"] * KQ150_MULT
            kq_qty = -int(round(kq_delta / kq_unit)) if kq_unit > 0 else 0

            target = {
                "k200_regular": current["k200_regular"] + r,
                "k200_mini":    current["k200_mini"]    + m,
                "kq150":        current["kq150"]        + kq_qty,
            }
            log.append(f"  목표 보유: {target}")
            actions = diff_positions(current, target, symbols)
            for a in actions:
                log.append(f"    [ACT] {a['kind']:5s} {a['side']} "
                           f"{a['symbol']} {a['qty']}계약")

            if actions:
                # 증거금 체크
                margin = check_margin(kis, actions, prices)
                if not margin["ok"]:
                    shortage = margin["shortage_krw"]
                    msg = (f"⚠️ Hedge3 daily 증거금 {shortage:,.0f}원 부족 "
                           f"(현물의 {shortage/spot_krw*100:.1f}%) 및 내일 다시 매매")
                    log.append(msg)
                    if cfg.get("kakao_alert_enabled", True):
                        try:
                            import KRFT_kakao
                            KRFT_kakao.send_kakao_to_self(
                                "[KRFT Hedge3 증거금 부족]\n" + msg)
                        except Exception as e:
                            log.append(f"  카카오 실패: {e}")
                    TA.send_tele("[KRFT Hedge3]\n" + "\n".join(log))
                    return {"ok": False, "executed": False,
                            "error": f"margin short {int(shortage)}",
                            "log": log, "context": ctx}

                # 라운드별 실행 (월말 진입과 동일 스케줄)
                executed = _execute_daily_orders(kis, actions, log)
                orders_placed = actions

    # 8) 포지션 상태 업데이트
    today_iso = today.isoformat()
    if sig["action"] == "open":
        result["positions"]["hedge3"] = {
            "active":     True,
            "entry_date": today_iso,
            "ratio":      sig["ratio"],
            "peak_pbr":   sig["peak_pbr"],
            "entry_pbr":  pbr,
            "_note":      "Hedge3 종료: peak_pbr×2/3 이하 즉시 OR Hedge1 진입 시 자동 흡수",
        }
    elif sig["action"] == "scale_up":
        result["positions"]["hedge3"]["ratio"]    = sig["ratio"]
        result["positions"]["hedge3"]["peak_pbr"] = sig["peak_pbr"]
    elif sig["action"] == "close":
        result["positions"]["hedge3"] = {
            "active": False, "entry_date": None, "ratio": 0.0,
            "peak_pbr": 0.0, "entry_pbr": 0.0,
            "_note": "Hedge3 종료: peak_pbr×2/3 이하 즉시 OR Hedge1 진입 시 자동 흡수",
        }
    elif sig["action"] == "hold":
        result["positions"]["hedge3"]["peak_pbr"] = sig["peak_pbr"]

    # 9) 잔고 재조회 + 동기화 + PNL
    if executed:
        time.sleep(3)
        bal2 = ORDER.get_futures_balance(kis)
        if bal2:
            _sync_holdings_from_balance(result, bal2, symbols)
            bal = bal2

    pnl = float(bal["evlu_pfls_smtl"]) if bal else 0.0
    eval_amt = float(bal["evlu_amt_smtl"]) if bal else 0.0

    # 10) snapshots.prev_day 갱신은 알림 송신 후 (scheduler 가 마지막에 처리)
    # 여기서는 비교용으로 result["snapshots"]["prev_day"] 를 변경하지 않음.
    # _pending_prev_day_update 에 새 값만 저장.
    result["_pending_prev_day_update"] = {
        "date":      today_iso,
        "evlu_pfls": pnl,
        "evlu_amt":  eval_amt,
    }

    # 11) trade_history
    if executed:
        result["trade_history"].append({
            "date":     today_iso,
            "type":     "hedge3_daily",
            "action":   sig["action"],
            "pbr":      pbr,
            "actions":  orders_placed,
        })
        result["trade_history"] = result["trade_history"][-200:]

    # 12) last_run
    result["last_run"] = {
        "date":    today_iso,
        "type":    "hedge3_daily",
        "signals": {"hedge3": sig},
        "orders":  [],
        "status":  "executed" if executed else "no_trade",
    }
    save_result(result)

    return {
        "ok":       True,
        "executed": executed,
        "action":   sig["action"],
        "pbr":      pbr,
        "kospi":    kospi,
        "kosdaq":   ctx["kosdaq"],
        "vkospi":   ctx["vkospi"],
        "pnl":      pnl,
        "eval_amt": eval_amt,
        "log":      log,
        "context":  ctx,
        "sig":      sig,
    }


def _execute_daily_orders(kis, actions: list, log: list) -> bool:
    """
    Hedge3 daily 매매 — 월말 진입과 동일한 시간표:
      R1 15:30 첫호가 / R2~4 호가갱신 /
      R5 15:32 청산미체결 시장가 /
      R6~8 신규호가갱신 /
      R9 15:34 신규미체결 시장가.

    Returns: 매매 발생 여부
    """
    close_actions = [a for a in actions if a["kind"] == "close"]
    open_actions  = [a for a in actions if a["kind"] == "open"]
    log.append(f"  === 라운드 (청산 {len(close_actions)} + "
               f"신규 {len(open_actions)}) ===")

    # R1
    _sleep_until("15:30:00")
    log.append(f"  [{_kst_now().strftime('%H:%M:%S')}] R1 1호가 발주")
    if close_actions:
        _place_orders_with_first_quote(kis, close_actions, log)
    if open_actions:
        _place_orders_with_first_quote(kis, open_actions, log)

    # R2~R4
    for hhmmss in ("15:30:30", "15:31:00", "15:31:30"):
        _sleep_until(hhmmss)
        _refresh_unfilled_to_first_quote(kis, log)

    # R5: 청산 시장가
    _sleep_until("15:32:00")
    close_keys = {(a["symbol"], a["side"]) for a in close_actions}
    for u in ORDER.get_unfilled(kis):
        u_side_str = "BUY" if u["side"] == ORDER.SIDE_BUY else "SELL"
        if (u["symbol"], u_side_str) not in close_keys:
            continue
        c = ORDER.cancel_order(kis, u["org_orgno"], u["order_no"], qty=0)
        if c and c.get("ok"):
            time.sleep(0.3)
            ORDER.order_futures(kis, u["symbol"], u["rem_qty"], 0,
                                side=u["side"], cls=ORDER.CLS_CLOSE,
                                market_order=True)

    # R6~R8
    for hhmmss in ("15:32:30", "15:33:00", "15:33:30"):
        _sleep_until(hhmmss)
        _refresh_unfilled_to_first_quote(kis, log)

    # R9: 신규 시장가
    _sleep_until("15:34:00")
    open_keys = {(a["symbol"], a["side"]) for a in open_actions}
    for u in ORDER.get_unfilled(kis):
        u_side_str = "BUY" if u["side"] == ORDER.SIDE_BUY else "SELL"
        if (u["symbol"], u_side_str) not in open_keys:
            continue
        c = ORDER.cancel_order(kis, u["org_orgno"], u["order_no"], qty=0)
        if c and c.get("ok"):
            time.sleep(0.3)
            ORDER.order_futures(kis, u["symbol"], u["rem_qty"], 0,
                                side=u["side"], cls=ORDER.CLS_OPEN,
                                market_order=True)

    return True


# ==================================================================
#  Daily 데이터 컨텍스트 조회 (매매 없이도 알림용 데이터만)
# ==================================================================
def get_daily_context_only() -> dict:
    """
    매매 없이 평일 알림 송신용으로 시장 데이터 + 보유 상태 조회.
    Hedge3 OFF 인 평일에 호출 (월말/만기일 아닌 날).

    Returns:
      {
        "ok": bool,
        "kospi": float, "kosdaq": float, "pbr": float, "vkospi": float,
        "pnl": float, "eval_amt": float,
        "holdings": dict,
        "enabled": dict,
      }
    """
    try:
        kis = KIS_API(FUT_KEY_FILE, FUT_TOKEN_FILE, FUT_CANO, FUT_ACNT_PRDT_CD)
    except Exception:
        return {"ok": False, "error": "KIS init"}

    result = load_result()
    cfg = result.get("manual_config", {})
    today = _kst_now().date()

    # 데이터
    ctx = DATA.get_daily_market_context(
        kis, pbr_override=cfg.get("pbr_override"))
    if not ctx["ok"]:
        return {"ok": False, "error": "data context"}

    # 잔고
    bal = ORDER.get_futures_balance(kis)
    holdings = {}
    pnl = 0.0
    eval_amt = 0.0
    if bal:
        symbols = SYM.get_current_symbols(today)
        _sync_holdings_from_balance(result, bal, symbols)
        holdings = result["holdings"]
        pnl = float(bal["evlu_pfls_smtl"])
        eval_amt = float(bal["evlu_amt_smtl"])

    return {
        "ok":         True,
        "today":      today.isoformat(),
        "kospi":      ctx["kospi"],
        "kosdaq":     ctx["kosdaq"],
        "pbr":        ctx["kospi_pbr"],
        "vkospi":     ctx["vkospi"],
        "pnl":        pnl,
        "eval_amt":   eval_amt,
        "holdings":   holdings,
        "positions":  result["positions"],
        "enabled":    cfg.get("strategy_enabled", {}),
        "snapshots":  result.get("snapshots", {}),
    }


# ==================================================================
#  CLI
# ==================================================================
if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "signal"
    if mode == "signal":
        run_signal_entry()
    elif mode == "rollover":
        run_rollover()
    elif mode == "hedge3_daily":
        result = run_hedge3_daily()
        print(f"\nexecuted={result.get('executed')} action={result.get('action')}")
        # log 전체 출력
        for line in result.get("log", []):
            print(line)
        # 알림 빌드 시뮬레이션 (scheduler가 실제 송신)
        try:
            import json as _j
            with open(RESULT_PATH, "r", encoding="utf-8") as f:
                rj = _j.load(f)
            import KRFT_notify as _NF
            msg_ctx = {
                "today":     result.get("log",[""])[0].split(": ")[-1].strip() if result.get("log") else "",
                "kospi":     result.get("kospi", 0),
                "kosdaq":    result.get("kosdaq", 0),
                "pbr":       result.get("pbr", 0),
                "vkospi":    result.get("vkospi", 0),
                "pnl":       result.get("pnl", 0),
                "eval_amt":  result.get("eval_amt", 0),
                "enabled":   rj["manual_config"]["strategy_enabled"],
                "positions": rj["positions"],
                "holdings":  rj["holdings"],
                "snapshots": rj.get("snapshots", {}),
            }
            if result.get("executed"):
                msg = _NF.build_trade_end_message(
                    msg_ctx["today"], "hedge3_daily", True, msg_ctx)
            else:
                msg = _NF.build_daily_message(msg_ctx, mode="hedge3_active")
            TA.send_tele(msg)
        except Exception as e:
            print(f"  알림 빌드 실패: {e}")
    elif mode == "daily_context":
        ctx = get_daily_context_only()
        import json as _j
        print(_j.dumps(ctx, ensure_ascii=False, indent=2, default=str))
    else:
        print(f"Unknown mode: {mode}")
        sys.exit(2)
