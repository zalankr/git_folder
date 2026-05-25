# -*- coding: utf-8 -*-
"""
KRFT_close_all.py
=================
국내선물 보유 계약 일괄 청산 스크립트 (시장가 즉시 청산 버전).

용도:
  지정일 15:25 (KST)에 cron으로 실행.
  국내선물 계좌(64753341 / 03)의 모든 보유 포지션을 조회하고
  반대매매(long→환매도, short→환매수)를 시장가로 즉시 청산.
  최종 결과를 텔레그램으로 통지.

cron 예시 (EC2는 UTC+0; 15:25 KST = 06:25 UTC):
  25 6 28 5 *  tendo -m1 -- timeout -s 9 5m /usr/bin/python3 \
       /var/autobot/TR_KRFT/KRFT_close_all.py >> /var/log/krft_close.log 2>&1

설계 원칙:
  - 1차부터 시장가 청산 — 1호가 지정가 미체결 리스크 회피
  - 외부 의존 최소화: KRFT_order만 사용
  - 발주 직후 텔레그램 통지, 잠시 대기 후 잔고 재확인으로 체결 검증

확인된 ORDER.get_futures_balance() 반환 구조:
  bal["positions"] = [
    {"symbol": "A05606", "name": "미니 F 202606",
     "side": "long"|"short", "qty": int,
     "avg_price": float, "eval_pnl": float, ...},
    ...
  ]

확인된 KRFT_order 상수/시그니처:
  SIDE_BUY  = '02', SIDE_SELL = '01'
  CLS_OPEN  = '01', CLS_CLOSE = '02'
  order_futures(kis, shtn_code, qty, price, side, cls, market_order=False)
"""
from __future__ import annotations
import sys
import json
import time
from datetime import datetime
from typing import List, Dict

import pytz

sys.path.insert(0, "/var/autobot")
sys.path.insert(0, "/var/autobot/TR_KRFT")

import telegram_alert as TA
from KIS_KR import KIS_API
import KRFT_order as ORDER

# ------------------------------------------------------------------
# 계좌·경로 상수 (KRFT_TR.py와 동일)
# ------------------------------------------------------------------
FUT_CANO         = "64753341"
FUT_ACNT_PRDT_CD = "03"
FUT_KEY_FILE     = f"/var/autobot/KIS/kis{FUT_CANO}nkr.txt"
FUT_TOKEN_FILE   = f"/var/autobot/KIS/kis{FUT_CANO}_token.json"

KST = pytz.timezone("Asia/Seoul")

# 체결 반영 대기 (시장가 발주 후 잔고 재조회까지)
WAIT_AFTER_ORDER = 8  # 초


# ==================================================================
#  헬퍼
# ==================================================================
def _kst_now() -> datetime:
    return datetime.now(KST)


def _fmt_pos(p: Dict) -> str:
    side_kr = "매수보유(long)" if p["side"] == "long" else "매도보유(short)"
    return (f"  ‐ {p.get('name', p['symbol'])} ({p['symbol']}) "
            f"{side_kr} {p['qty']}계약 @ {p.get('avg_price', 0):.2f} "
            f"(PnL {p.get('eval_pnl', 0):,.0f})")


def _reverse_side(pos_side: str):
    """
    포지션 사이드 → 반대매매 주문 사이드.
      long(매수보유)  → SIDE_SELL ('01') 환매도
      short(매도보유) → SIDE_BUY  ('02') 환매수
    """
    if pos_side == "long":
        return ORDER.SIDE_SELL, "환매도"
    elif pos_side == "short":
        return ORDER.SIDE_BUY, "환매수"
    else:
        return None, f"unknown({pos_side})"


# ==================================================================
#  메인 — 일괄 청산 (시장가 즉시)
# ==================================================================
def run_close_all() -> dict:
    """
    국내선물 전 포지션 시장가 일괄 청산.

    Returns:
      {"ok": bool, "ordered": int, "remain": int, "details": [...]}
    """
    ts = _kst_now().strftime("%Y-%m-%d %H:%M:%S")
    log: List[str] = [f"🔻 <b>국내선물 일괄청산(시장가)</b> {ts} KST"]

    # 1) KIS 초기화
    try:
        kis = KIS_API(FUT_KEY_FILE, FUT_TOKEN_FILE, FUT_CANO, FUT_ACNT_PRDT_CD)
    except Exception as e:
        TA.send_tele(f"[KRFT청산] KIS 초기화 실패: {e}")
        return {"ok": False, "ordered": 0, "remain": 0, "details": []}

    # 2) 잔고 조회
    bal = ORDER.get_futures_balance(kis)
    positions = bal.get("positions", []) if bal else []
    if not positions:
        log.append("• 보유 포지션 없음 — 청산할 계약 없습니다.")
        if bal:
            log.append(f"• 평가금 {bal.get('evlu_amt_smtl', 0):,.0f} / "
                       f"PnL {bal.get('evlu_pfls_smtl', 0):,.0f} / "
                       f"증거금 {bal.get('mgna_tota', 0):,.0f}")
        TA.send_tele("\n".join(log))
        return {"ok": True, "ordered": 0, "remain": 0, "details": []}

    log.append(f"• 보유 포지션: {len(positions)}건")
    log.extend(_fmt_pos(p) for p in positions)
    log.append(f"• 사전 평가금 {bal.get('evlu_amt_smtl', 0):,.0f} / "
               f"PnL {bal.get('evlu_pfls_smtl', 0):,.0f}")

    # 3) 시장가 일괄 발주
    log.append("\n• 시장가 청산 발주:")
    details: List[Dict] = []
    success = 0
    fail = 0
    for p in positions:
        rev_side, rev_kr = _reverse_side(p["side"])
        if rev_side is None:
            fail += 1
            log.append(f"  ❌ {p['symbol']}: {rev_kr}")
            details.append({"symbol": p["symbol"], "ok": False,
                            "msg": f"unknown side {p['side']}"})
            continue

        r = ORDER.order_futures(
            kis,
            p["symbol"],
            p["qty"],
            0.0,                       # 시장가는 price=0
            side=rev_side,
            cls=ORDER.CLS_CLOSE,       # '02' 청산
            market_order=True,         # ✅ 시장가
        )
        ok = bool(r and r.get("ok"))
        odno = r.get("order_no", "") if r else ""
        msg = r.get("msg", "") if r else "no response"
        if ok:
            success += 1
            log.append(f"  ✅ {p.get('name', p['symbol'])} "
                       f"{rev_kr} {p['qty']}계약 → 주문번호 {odno}")
        else:
            fail += 1
            log.append(f"  ❌ {p.get('name', p['symbol'])} "
                       f"{rev_kr} {p['qty']}계약 → 실패: {msg}")
        details.append({
            "symbol":   p["symbol"],
            "name":     p.get("name", ""),
            "qty":      p["qty"],
            "pos_side": p["side"],
            "rev_side": rev_side,
            "order_no": odno,
            "ok":       ok,
            "msg":      msg,
        })
        time.sleep(0.3)   # rate-limit 여유

    # 4) 체결 반영 대기 후 잔고 재확인
    time.sleep(WAIT_AFTER_ORDER)
    bal2 = ORDER.get_futures_balance(kis)
    remain = bal2.get("positions", []) if bal2 else []
    log.append(f"\n• 청산 후 잔고: {len(remain)}건 보유")
    if remain:
        log.extend("  ⚠ 미청산 " + _fmt_pos(p).strip() for p in remain)
    if bal2:
        log.append(f"• 사후 평가금 {bal2.get('evlu_amt_smtl', 0):,.0f} / "
                   f"PnL {bal2.get('evlu_pfls_smtl', 0):,.0f} / "
                   f"예수금 {bal2.get('dnca_cash', 0):,.0f}")

    log.append(
        f"\n📊 요약: 발주성공 {success} / 실패 {fail} / 미청산 {len(remain)}"
    )
    TA.send_tele("\n".join(log))

    return {
        "ok":      fail == 0 and len(remain) == 0,
        "ordered": success,
        "failed":  fail,
        "remain":  len(remain),
        "details": details,
    }


# ==================================================================
#  CLI
# ==================================================================
if __name__ == "__main__":
    result = run_close_all()
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    sys.exit(0 if result.get("ok") else 1)
