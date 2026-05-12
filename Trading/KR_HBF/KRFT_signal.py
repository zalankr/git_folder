"""
KRFT_signal.py
==============
국내 선물 자동매매 시그널 계산 모듈 (Boost / Hedge1 / Hedge2)

운용 흐름
---------
1) 매월말 15:25  : 다른 코드가 KOSPI/KOSDAQ/KOSPI PBR/VKOSPI 월말 종가를
                  krfuture_monthly.json["data"][YYYY-MM] 에 기록
2) 매월말 15:25~ : 본 모듈의 compute_signals(json_path) 호출
3) 매월말 15:35  : 거래 모듈이 반환된 시그널에 따라 KIS API 주문 실행
                  후 update_positions(...) 로 포지션 기록

전략 요약
---------
[Boost]  KOSPI PBR / 전고점PBR 비율로 KOSPI200 선물 매수 (10개월 보유)
  - 1단계: 비율 ≤ 8.9/19  → 현물평가금×100%  매수
  - 2단계: 비율 ≤ 8.6/19  → 현물평가금×200%  매수
  - 보유중 동일/하위 단계 신호: 무시
  - 1단계 보유중 2단계 신호: 200% 로 증액 + 만기 리셋
  - 미보유 + 1·2단계 동시 만족: 2단계로 진입

[Hedge1] KOSPI 2개월 연속 하락 & VKOSPI ≤ 14
         → (KOSPI200 + KOSDAQ150) 1:1 비중으로 현물평가금×100% 매도
         - 매월 시그널 재확인:
             · 유지 → 보유 지속
             · 소멸 → 그 시점 기준 +1개월 더 보유 후 환매수

[Hedge2] 매년 4월말 단발성. KOSDAQ 11월말→4월말 수익률로 판정
         - 수익률 ≥ -5% : 현물평가금×30%   KOSDAQ150 선물 매도
         - 수익률 <  -5% : 현물평가금×70%
         - 10월말 환매수 청산 (6개월 보유)

공개 API
--------
compute_signals(json_path)   → dict
update_positions(json_path, executed_signals)
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Optional

# ------------------------------------------------------------------
# 전략 파라미터 (수정 시 한 곳만 변경)
# ------------------------------------------------------------------

# Boost
BOOST1_RATIO_THRESHOLD = 8.9 / 19   # ≈ 0.4684
BOOST2_RATIO_THRESHOLD = 8.6 / 19   # ≈ 0.4526
BOOST1_NOTIONAL_RATIO  = 1.0        # 현물평가금 대비 100%
BOOST2_NOTIONAL_RATIO  = 2.0        # 현물평가금 대비 200%
BOOST_HOLD_MONTHS      = 10

# Hedge1
HEDGE1_VKOSPI_THRESHOLD = 14.0
HEDGE1_NOTIONAL_RATIO   = 1.0       # 합계 100% (K200 50% + KQ150 50%)
HEDGE1_EXTRA_HOLD_MONTHS = 1        # 신호 소멸 시 추가 보유 개월수

# Hedge2
HEDGE2_RETURN_THRESHOLD  = -0.05    # KOSDAQ 11월→4월 수익률 컷
HEDGE2_NOTIONAL_HIGH     = 0.3      # 수익률 ≥ -5% : 30%
HEDGE2_NOTIONAL_LOW      = 0.7      # 수익률 <  -5% : 70%
HEDGE2_ENTRY_MONTH       = 4        # 4월말 진입
HEDGE2_EXIT_MONTH        = 10       # 10월말 청산


# ------------------------------------------------------------------
# 월(month) 산술 헬퍼
# ------------------------------------------------------------------

def _ym_to_int(ym: str) -> int:
    """'2026-04' → 2026*12+4 = 24316"""
    y, m = ym.split("-")
    return int(y) * 12 + int(m)


def _int_to_ym(n: int) -> str:
    """24316 → '2026-04'"""
    y, m = divmod(n - 1, 12)
    return f"{y:04d}-{m+1:02d}"


def add_months(ym: str, n: int) -> str:
    return _int_to_ym(_ym_to_int(ym) + n)


def months_between(ym_start: str, ym_end: str) -> int:
    """end - start (월 단위)"""
    return _ym_to_int(ym_end) - _ym_to_int(ym_start)


def prev_month(ym: str, n: int = 1) -> str:
    return add_months(ym, -n)


# ------------------------------------------------------------------
# 데이터 조회 헬퍼
# ------------------------------------------------------------------

def _latest_month(data: dict) -> str:
    """data dict 의 가장 최근 월 키 반환"""
    return max(data.keys())


def _get(data: dict, ym: str, field: str) -> Optional[float]:
    rec = data.get(ym)
    if rec is None:
        return None
    return rec.get(field)


# ------------------------------------------------------------------
# 시그널 계산: Boost
# ------------------------------------------------------------------

def _compute_boost(data: dict, position: dict, current_ym: str) -> dict:
    """
    Boost 시그널 산출.
    
    반환:
      {
        "action":     "open" | "scale_up" | "close" | "hold" | "none",
        "new_stage":  0 | 1 | 2,
        "new_ratio":  float,
        "new_expire": str | None,
        "trigger_qty_notional": float,  # 신규 체결 필요 명목 비율 (현물평가금 대비)
        "reason":     str,
      }
    """
    pbr = _get(data, current_ym, "kospi_pbr")
    if pbr is None:
        return {"action": "none", "reason": f"PBR 데이터 없음 ({current_ym})"}

    # 전고점 PBR: 시작점(1999)부터 current_ym 까지의 최대값
    peak_pbr = max(
        v["kospi_pbr"] for k, v in data.items()
        if k <= current_ym and v.get("kospi_pbr") is not None
    )
    ratio = pbr / peak_pbr

    in_stage1 = (ratio <= BOOST1_RATIO_THRESHOLD)
    in_stage2 = (ratio <= BOOST2_RATIO_THRESHOLD)

    cur_stage  = position.get("stage", 0)
    cur_expire = position.get("expire_month")

    # ----- 1) 만기 청산 체크 (시그널 판정보다 먼저) -----
    if cur_stage > 0 and cur_expire is not None and current_ym >= cur_expire:
        return {
            "action": "close",
            "new_stage": 0,
            "new_ratio": 0.0,
            "new_expire": None,
            "trigger_qty_notional": 0.0,
            "reason": f"Boost{cur_stage}단계 만기 도래 ({cur_expire})",
        }

    # ----- 2) 신호 판정 -----
    # 미보유 상태
    if cur_stage == 0:
        if in_stage2:  # 1·2단계 동시 만족이면 자동으로 여기에 잡힘
            return {
                "action": "open",
                "new_stage": 2,
                "new_ratio": BOOST2_NOTIONAL_RATIO,
                "new_expire": add_months(current_ym, BOOST_HOLD_MONTHS),
                "trigger_qty_notional": BOOST2_NOTIONAL_RATIO,
                "reason": f"Boost2 진입: PBR {pbr:.2f}/peak {peak_pbr:.2f} = {ratio:.4f} ≤ {BOOST2_RATIO_THRESHOLD:.4f}",
            }
        if in_stage1:
            return {
                "action": "open",
                "new_stage": 1,
                "new_ratio": BOOST1_NOTIONAL_RATIO,
                "new_expire": add_months(current_ym, BOOST_HOLD_MONTHS),
                "trigger_qty_notional": BOOST1_NOTIONAL_RATIO,
                "reason": f"Boost1 진입: PBR {pbr:.2f}/peak {peak_pbr:.2f} = {ratio:.4f} ≤ {BOOST1_RATIO_THRESHOLD:.4f}",
            }
        return {
            "action": "none",
            "reason": f"신호 없음: 비율 {ratio:.4f} > {BOOST1_RATIO_THRESHOLD:.4f}",
        }

    # 1단계 보유 중
    if cur_stage == 1:
        if in_stage2:
            return {
                "action": "scale_up",
                "new_stage": 2,
                "new_ratio": BOOST2_NOTIONAL_RATIO,
                "new_expire": add_months(current_ym, BOOST_HOLD_MONTHS),
                "trigger_qty_notional": BOOST2_NOTIONAL_RATIO - BOOST1_NOTIONAL_RATIO,
                "reason": f"Boost1→2 증액: 비율 {ratio:.4f} ≤ {BOOST2_RATIO_THRESHOLD:.4f}, 만기 리셋",
            }
        return {"action": "hold", "reason": f"Boost1 유지 (만기 {cur_expire})"}

    # 2단계 보유 중 → 모든 신호 무시
    return {"action": "hold", "reason": f"Boost2 유지 (만기 {cur_expire})"}


# ------------------------------------------------------------------
# 시그널 계산: Hedge1
# ------------------------------------------------------------------

def _is_hedge1_signal(data: dict, ym: str) -> Optional[bool]:
    """
    해당 월 ym 에 Hedge1 신호가 살아있는지 판정.
    조건: KOSPI[ym] < KOSPI[ym-1] AND KOSPI[ym] < KOSPI[ym-2] AND VKOSPI[ym] ≤ 14
    데이터 부족 시 None.
    """
    k0 = _get(data, ym, "kospi")
    k1 = _get(data, prev_month(ym, 1), "kospi")
    k2 = _get(data, prev_month(ym, 2), "kospi")
    v0 = _get(data, ym, "vkospi")
    if None in (k0, k1, k2, v0):
        return None
    return (k0 < k1) and (k0 < k2) and (v0 <= HEDGE1_VKOSPI_THRESHOLD)


def _compute_hedge1(data: dict, position: dict, current_ym: str) -> dict:
    """
    Hedge1 시그널 산출.
    
    반환:
      {
        "action":     "open" | "close" | "hold" | "none",
        "active":     bool,
        "ratio":      float,
        "signal_end_month": str | None,
        "exit_month": str | None,
        "reason":     str,
      }
    """
    signal_now = _is_hedge1_signal(data, current_ym)
    active     = position.get("active", False)
    sig_end    = position.get("signal_end_month")
    exit_month = position.get("exit_month")

    if signal_now is None:
        return {"action": "none", "reason": f"Hedge1 데이터 부족 ({current_ym})"}

    # ----- 보유 중 -----
    if active:
        if signal_now:
            # 신호 유지 → 보유 지속, signal_end / exit 모두 갱신 안 함
            # (단, 만약 직전에 소멸로 exit_month 가 설정돼 있었으면 부활)
            return {
                "action": "hold",
                "active": True,
                "ratio":  position.get("ratio", HEDGE1_NOTIONAL_RATIO),
                "signal_end_month": None,    # 신호 살아있으니 종료시점 미정
                "exit_month": None,
                "reason": "Hedge1 신호 유지 → 보유 지속",
            }
        else:
            # 신호 소멸
            if sig_end is None:
                # 이번 달에 첫 소멸 → 그 시점에 +1개월 더 보유 후 청산
                new_exit = add_months(current_ym, HEDGE1_EXTRA_HOLD_MONTHS)
                return {
                    "action": "hold",
                    "active": True,
                    "ratio":  position.get("ratio", HEDGE1_NOTIONAL_RATIO),
                    "signal_end_month": current_ym,
                    "exit_month": new_exit,
                    "reason": f"Hedge1 신호 소멸 → {new_exit} 청산 예정",
                }
            else:
                # 이미 소멸 처리됨 → exit_month 도달 시 청산
                if current_ym >= exit_month:
                    return {
                        "action": "close",
                        "active": False,
                        "ratio":  0.0,
                        "signal_end_month": None,
                        "exit_month": None,
                        "reason": f"Hedge1 청산 (신호 종료 {sig_end} + {HEDGE1_EXTRA_HOLD_MONTHS}개월)",
                    }
                return {
                    "action": "hold",
                    "active": True,
                    "ratio":  position.get("ratio", HEDGE1_NOTIONAL_RATIO),
                    "signal_end_month": sig_end,
                    "exit_month": exit_month,
                    "reason": f"Hedge1 청산 대기 ({exit_month})",
                }

    # ----- 미보유 -----
    if signal_now:
        return {
            "action": "open",
            "active": True,
            "ratio":  HEDGE1_NOTIONAL_RATIO,
            "signal_end_month": None,
            "exit_month": None,
            "reason": f"Hedge1 진입: KOSPI 2개월 연속 하락 & VKOSPI ≤ {HEDGE1_VKOSPI_THRESHOLD}",
        }
    return {"action": "none", "reason": "Hedge1 신호 없음"}


# ------------------------------------------------------------------
# 시그널 계산: Hedge2
# ------------------------------------------------------------------

def _compute_hedge2(data: dict, position: dict, current_ym: str) -> dict:
    """
    Hedge2 시그널 산출. 4월말 진입 / 10월말 청산만 동작.
    
    반환:
      {
        "action":     "open" | "close" | "hold" | "none",
        "active":     bool,
        "ratio":      float,
        "expire_month": str | None,
        "reason":     str,
      }
    """
    month = int(current_ym.split("-")[1])
    active = position.get("active", False)
    expire = position.get("expire_month")

    # ----- 청산 (10월말) -----
    if active and expire is not None and current_ym >= expire:
        return {
            "action": "close",
            "active": False,
            "ratio":  0.0,
            "expire_month": None,
            "reason": f"Hedge2 청산 (만기 {expire})",
        }

    # ----- 진입 (4월말) -----
    if month == HEDGE2_ENTRY_MONTH and not active:
        prev_oct = f"{int(current_ym[:4]) - 1:04d}-10"
        kq_prev = _get(data, prev_oct, "kosdaq")
        kq_cur  = _get(data, current_ym, "kosdaq")
        if kq_prev is None or kq_cur is None:
            return {"action": "none", "reason": f"Hedge2 데이터 부족 ({prev_oct} or {current_ym})"}

        ret = kq_cur / kq_prev - 1.0
        ratio = HEDGE2_NOTIONAL_HIGH if ret >= HEDGE2_RETURN_THRESHOLD else HEDGE2_NOTIONAL_LOW
        new_expire = f"{current_ym[:4]}-{HEDGE2_EXIT_MONTH:02d}"
        return {
            "action": "open",
            "active": True,
            "ratio":  ratio,
            "expire_month": new_expire,
            "reason": f"Hedge2 진입: KOSDAQ {ret*100:+.2f}% ({prev_oct}→{current_ym}) → 비중 {ratio*100:.0f}%",
        }

    if active:
        return {"action": "hold", "reason": f"Hedge2 유지 (만기 {expire})"}
    return {"action": "none", "reason": "Hedge2 대상 월 아님"}


# ------------------------------------------------------------------
# 공개 API
# ------------------------------------------------------------------

def compute_signals(json_path: str, target_ym: str | None = None) -> dict:
    """
    JSON 파일을 읽어 시그널 dict 반환. 파일 수정 없음.
    
    target_ym: 'YYYY-MM' 형식. 미지정 시 data 의 최신 월 사용.
    
    반환:
    {
      "target_month": "2026-04",
      "boost":  {...},
      "hedge1": {...},
      "hedge2": {...},
    }
    """
    obj = json.loads(Path(json_path).read_text(encoding="utf-8"))
    data = obj["data"]
    positions = obj["positions"]

    current_ym = target_ym or _latest_month(data)
    if current_ym not in data:
        raise ValueError(f"대상 월({current_ym}) 데이터가 없습니다. 먼저 data 를 업데이트하세요.")

    boost_sig  = _compute_boost(data,  positions["boost"],  current_ym)
    hedge1_sig = _compute_hedge1(data, positions["hedge1"], current_ym)
    hedge2_sig = _compute_hedge2(data, positions["hedge2"], current_ym)

    return {
        "target_month": current_ym,
        "boost":  boost_sig,
        "hedge1": hedge1_sig,
        "hedge2": hedge2_sig,
    }


def update_positions(json_path: str, signals: dict) -> None:
    """
    거래 실행 완료 후 호출. signals 결과대로 positions 및 signals 이력 갱신.
    호출 시점: 매매 체결 확정 후 (체결 실패 시 호출 금지).
    """
    obj = json.loads(Path(json_path).read_text(encoding="utf-8"))
    current_ym = signals["target_month"]

    # ----- Boost -----
    b = signals["boost"]
    if b["action"] in ("open", "scale_up"):
        obj["positions"]["boost"] = {
            "stage":        b["new_stage"],
            "entry_month":  current_ym,
            "expire_month": b["new_expire"],
            "ratio":        b["new_ratio"],
        }
    elif b["action"] == "close":
        obj["positions"]["boost"] = {
            "stage": 0, "entry_month": None, "expire_month": None, "ratio": 0.0
        }
    # hold / none: 변경 없음

    # ----- Hedge1 -----
    h1 = signals["hedge1"]
    if h1["action"] == "open":
        obj["positions"]["hedge1"] = {
            "active": True,
            "entry_month": current_ym,
            "signal_end_month": None,
            "exit_month": None,
            "ratio": h1["ratio"],
        }
    elif h1["action"] == "hold" and h1.get("active"):
        # 신호 소멸로 exit_month 가 새로 설정된 경우 반영
        obj["positions"]["hedge1"]["signal_end_month"] = h1.get("signal_end_month")
        obj["positions"]["hedge1"]["exit_month"]      = h1.get("exit_month")
    elif h1["action"] == "close":
        obj["positions"]["hedge1"] = {
            "active": False, "entry_month": None, "signal_end_month": None,
            "exit_month": None, "ratio": 0.0
        }

    # ----- Hedge2 -----
    h2 = signals["hedge2"]
    if h2["action"] == "open":
        obj["positions"]["hedge2"] = {
            "active": True,
            "entry_month": current_ym,
            "expire_month": h2["expire_month"],
            "ratio": h2["ratio"],
        }
    elif h2["action"] == "close":
        obj["positions"]["hedge2"] = {
            "active": False, "entry_month": None, "expire_month": None, "ratio": 0.0
        }

    # ----- signals 이력 -----
    obj["signals"][current_ym] = {
        "boost":  {"action": b["action"],  "reason": b["reason"]},
        "hedge1": {"action": h1["action"], "reason": h1["reason"]},
        "hedge2": {"action": h2["action"], "reason": h2["reason"]},
        "computed_at": datetime.now().isoformat(timespec="seconds"),
    }

    Path(json_path).write_text(
        json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8"
    )


# ------------------------------------------------------------------
# CLI 테스트
# ------------------------------------------------------------------

if __name__ == "__main__":
    import sys
    path = sys.argv[1] if len(sys.argv) > 1 else "krfuture_monthly.json"
    target = sys.argv[2] if len(sys.argv) > 2 else None

    sigs = compute_signals(path, target)
    print(f"[{sigs['target_month']}] 시그널")
    print("-" * 60)
    for name in ("boost", "hedge1", "hedge2"):
        s = sigs[name]
        print(f"{name:7s} | action={s['action']:9s} | {s['reason']}")
