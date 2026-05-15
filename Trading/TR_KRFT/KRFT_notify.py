# -*- coding: utf-8 -*-
"""
KRFT_notify.py
==============
KRFT 텔레그램 알림 빌더.

알림 분기 (요구사항):
  - 거래일(월말/만기/Hedge3 매매 발생일):
      거래 시작 + 거래 결과 메시지 (이건 KRFT_TR.py에서 직접 송신)

  - 평일 일반 (거래 없음):
      · Hedge3 ON  → daily 메시지 (PBR, 지수, 포지션, 보유, 일별 변동, 누적 손익)
      · Hedge3 OFF → 메시지 송신 안 함 ("매매일 아님"은 cron 로그에만)

알림 본문 형식:
  [KRFT YYYY-MM-DD]
  📊 시장: KOSPI=XXXX KOSDAQ=XXX PBR=X.XX VKOSPI=XX
  🎯 전략: Boost=ON Hedge1=ON Hedge2=OFF Hedge3=ON
  📈 포지션:
     · Boost   stage=0  ratio=0%
     · Hedge1  inactive
     · Hedge3  active 30%  peak=2.55  entry=2.50
  💼 보유:
     · K200정규 long 5계약 avg=400.5
     · KQ150    short 21계약 avg=1200
  💰 손익:
     · 평가금액: 123,456,789원
     · 평가손익: +5,678,000원
     · 일별변동: +1,234,000원  (Hedge3 ON일 때)
     · 월별변동: +12,345,000원  (Hedge3 OFF일 때)
"""
from __future__ import annotations
from datetime import datetime
from typing import Optional


def _fmt_krw(v: float) -> str:
    if v == 0:
        return "0원"
    sign = "+" if v > 0 else "-"
    return f"{sign}{abs(int(v)):,}원"


def _fmt_pct(v: float) -> str:
    sign = "+" if v >= 0 else ""
    return f"{sign}{v*100:.0f}%"


def _strategy_line(enabled: dict) -> str:
    def f(k): return "ON" if enabled.get(k, False) else "OFF"
    return (f"Boost={f('boost')} Hedge1={f('hedge1')} "
            f"Hedge2={f('hedge2')} Hedge3={f('hedge3')}")


def _positions_lines(positions: dict) -> list[str]:
    out = []
    b = positions.get("boost", {})
    if b.get("stage", 0) > 0 or b.get("ratio", 0) > 0:
        out.append(f"  · Boost  stage={b.get('stage',0)} ratio={_fmt_pct(b.get('ratio',0))} "
                   f"expire={b.get('expire_month','-')}")
    else:
        out.append("  · Boost  inactive")

    h1 = positions.get("hedge1", {})
    if h1.get("active"):
        out.append(f"  · Hedge1 active ratio={_fmt_pct(h1.get('ratio',0))} "
                   f"exit={h1.get('exit_month','-')}")
    else:
        out.append("  · Hedge1 inactive")

    h2 = positions.get("hedge2", {})
    if h2.get("active"):
        out.append(f"  · Hedge2 active ratio={_fmt_pct(h2.get('ratio',0))}")
    else:
        out.append("  · Hedge2 inactive")

    h3 = positions.get("hedge3", {})
    if h3.get("active"):
        out.append(f"  · Hedge3 active ratio={_fmt_pct(h3.get('ratio',0))} "
                   f"peak={h3.get('peak_pbr',0):.4f} entry={h3.get('entry_pbr',0):.4f}")
    else:
        out.append("  · Hedge3 inactive")
    return out


def _holdings_lines(holdings: dict) -> list[str]:
    out = []
    for key in ("K200_regular", "K200_mini", "KQ150"):
        h = holdings.get(key, {}) or {}
        qty = int(h.get("qty", 0) or 0)
        if qty == 0:
            continue
        side = h.get("side") or "?"
        avg  = float(h.get("avg_price", 0) or 0)
        out.append(f"  · {key:13s} {side:5s} {qty}계약 avg={avg:.2f} "
                   f"({h.get('symbol','-')})")
    if not out:
        out.append("  · 보유 선물 없음")
    return out


def build_daily_message(ctx: dict, mode: str = "hedge3_active") -> str:
    """
    Daily 알림 본문 생성.

    Args:
      ctx: get_daily_context_only() 또는 run_hedge3_daily() 의 반환 통합 형식
        {
          "today": str, "kospi": float, "kosdaq": float, "pbr": float, "vkospi": float,
          "pnl": float, "eval_amt": float,
          "holdings": dict, "positions": dict, "enabled": dict,
          "snapshots": dict,
        }
      mode: "hedge3_active" 면 일별변동, "month_only" 면 월별변동만 표시

    Returns: 텔레그램 메시지 문자열
    """
    today = ctx.get("today", datetime.now().strftime("%Y-%m-%d"))

    lines = []
    lines.append(f"[KRFT {today}]")
    lines.append(f"📊 시장: KOSPI={ctx['kospi']:.2f} KOSDAQ={ctx['kosdaq']:.2f} "
                 f"PBR={ctx['pbr']:.4f} VKOSPI={ctx['vkospi']:.2f}")
    lines.append(f"🎯 전략: {_strategy_line(ctx.get('enabled', {}))}")

    lines.append("📈 포지션:")
    lines.extend(_positions_lines(ctx.get("positions", {})))

    lines.append("💼 보유:")
    lines.extend(_holdings_lines(ctx.get("holdings", {})))

    lines.append("💰 손익:")
    lines.append(f"  · 평가금액: {int(ctx.get('eval_amt',0)):,}원")
    lines.append(f"  · 평가손익: {_fmt_krw(ctx.get('pnl',0))}")

    snap = ctx.get("snapshots", {}) or {}
    if mode == "hedge3_active":
        prev = snap.get("prev_day", {}) or {}
        prev_pnl = float(prev.get("evlu_pfls", 0) or 0)
        prev_date = prev.get("date")
        if prev_date and prev_date != today:
            delta = ctx.get("pnl", 0) - prev_pnl
            lines.append(f"  · 일별변동: {_fmt_krw(delta)}  (전일 {prev_date} 기준)")
    else:
        prev = snap.get("prev_month_end", {}) or {}
        prev_pnl = float(prev.get("evlu_pfls", 0) or 0)
        prev_date = prev.get("date")
        if prev_date and prev_date != today:
            delta = ctx.get("pnl", 0) - prev_pnl
            lines.append(f"  · 월별변동: {_fmt_krw(delta)}  (전월말 {prev_date} 기준)")

    return "\n".join(lines)


def build_trade_start_message(today: str, trade_type: str, ctx: dict) -> str:
    """
    매매 시작 메시지.

    trade_type: 'signal_entry' / 'rollover' / 'hedge3_daily'
    """
    label = {
        "signal_entry": "월말 시그널 진입",
        "rollover":     "선물 만기 롤오버",
        "hedge3_daily": "Hedge3 daily 매매",
    }.get(trade_type, trade_type)

    lines = [f"[KRFT {today}] 🚀 {label} 시작"]
    if "pbr" in ctx:
        lines.append(f"  PBR={ctx['pbr']:.4f} KOSPI={ctx['kospi']:.2f}")
    if "enabled" in ctx:
        lines.append(f"  전략: {_strategy_line(ctx['enabled'])}")
    return "\n".join(lines)


def build_trade_end_message(today: str, trade_type: str,
                            executed: bool, ctx: dict) -> str:
    """매매 종료 메시지"""
    label = {
        "signal_entry": "월말 시그널",
        "rollover":     "롤오버",
        "hedge3_daily": "Hedge3 daily",
    }.get(trade_type, trade_type)

    icon = "✅" if executed else "ℹ️"
    status = "체결" if executed else "매매 없음"
    lines = [f"[KRFT {today}] {icon} {label} 종료 — {status}"]

    if "pnl" in ctx:
        lines.append(f"  현재 평가손익: {_fmt_krw(ctx['pnl'])}")
    if "eval_amt" in ctx:
        lines.append(f"  평가금액: {int(ctx['eval_amt']):,}원")

    lines.append("📈 포지션:")
    lines.extend(_positions_lines(ctx.get("positions", {})))

    return "\n".join(lines)
