#!/usr/bin/env python3
"""
월간 비교 분석 리포트 생성기

매월 1일 KST 09:00 실행:
  - 지난 1개월 일치도 추이
  - 전략별 클론 vs 사이트 성과 비교
  - 빈번한 미스매치 종목 TOP-20 → 파라미터 튜닝 단서
  - Markdown 리포트 + Telegram 요약

출력: /var/autobot/Reports/comparison_YYYYMM.md
"""
import os
import sys
from datetime import datetime, timedelta

sys.path.insert(0, "/var/autobot")
try:
    import telegram_alert as TA
except ImportError:
    class _DummyTA:
        @staticmethod
        def send_tele(msg): print(f"[TELE] {msg}")
    TA = _DummyTA()

from comparison_db import ComparisonDB

REPORT_DIR = "/var/autobot/Reports"
STRATEGIES = ["PEAK", "MOMENTUM", "VALUE"]


def generate_monthly_report():
    os.makedirs(REPORT_DIR, exist_ok=True)
    today = datetime.now()
    last_month_label = (today - timedelta(days=15)).strftime("%Y-%m")
    report_path = f"{REPORT_DIR}/comparison_{last_month_label.replace('-', '')}.md"

    db = ComparisonDB()
    lines = [f"# StockEasy 비교 리포트 — {last_month_label}\n",
             f"_생성: {today.strftime('%Y-%m-%d %H:%M')}_\n\n"]

    # ---------- 1. 전략별 일치도 추이 ----------
    lines.append("## 1. 일치도 (Jaccard) 추이 — 최근 30일\n\n")
    lines.append("| 전략 | 평균 Jaccard | 최저 | 최고 | 평균 Precision | 평균 Recall | 평균 교집합 |\n")
    lines.append("|---|---:|---:|---:|---:|---:|---:|\n")
    for strategy in STRATEGIES:
        hist = db.get_jaccard_history(strategy, days=30)
        if hist.empty:
            lines.append(f"| {strategy} | — | — | — | — | — | — |\n")
            continue
        lines.append(
            f"| {strategy} "
            f"| {hist['jaccard'].mean():.3f} "
            f"| {hist['jaccard'].min():.3f} "
            f"| {hist['jaccard'].max():.3f} "
            f"| {hist['precision_val'].mean():.3f} "
            f"| {hist['recall_val'].mean():.3f} "
            f"| {hist['intersect_n'].mean():.1f} |\n"
        )

    # ---------- 2. 성과 비교 ----------
    lines.append("\n## 2. 성과 비교 — 최근 60일 픽 기준\n\n")
    perf = db.get_performance_summary(days=60)
    if perf.empty:
        lines.append("_성과 데이터 부족 (최소 20거래일 필요)_\n")
    else:
        lines.append("| 전략 | 출처 | N | 평균 1d | 5d | 20d | 최고20d | MDD20d | 승률(20d) |\n")
        lines.append("|---|---|---:|---:|---:|---:|---:|---:|---:|\n")
        for _, r in perf.iterrows():
            lines.append(
                f"| {r['strategy']} | {r['source']} "
                f"| {int(r['picks'])} "
                f"| {r['avg_1d_pct']:+.2f}% "
                f"| {r['avg_5d_pct']:+.2f}% "
                f"| {r['avg_20d_pct']:+.2f}% "
                f"| {r['avg_max20_pct']:+.2f}% "
                f"| {r['avg_mdd20_pct']:+.2f}% "
                f"| {r['win_rate_20d']:.1%} |\n"
            )

    # ---------- 3. 미스매치 분석 ----------
    lines.append("\n## 3. 빈번한 미스매치 — 최근 30일\n\n")
    lines.append("**튜닝 단서**: 사이트가 자주 픽하는데 클론이 놓치는 종목은 "
                 "클론의 필터가 너무 엄격하거나 누락된 시그널이 있다는 신호. "
                 "반대로 클론만 픽하는 종목이 많으면 클론이 과대포착 중.\n\n")
    for strategy in STRATEGIES:
        miss = db.get_frequent_mismatches(strategy, days=30, top_n=10)
        lines.append(f"### {strategy}\n\n")
        lines.append("**StockEasy만 픽 (클론이 놓침)** — 클론 필터를 완화해야 할 후보:\n")
        if miss["stockeasy_only_top"]:
            for code, cnt in miss["stockeasy_only_top"]:
                lines.append(f"- `{code}` × {cnt}회\n")
        else:
            lines.append("- 없음 (모두 포착)\n")
        lines.append("\n**클론만 픽 (사이트엔 없음)** — 클론 필터를 강화해야 할 후보:\n")
        if miss["clone_only_top"]:
            for code, cnt in miss["clone_only_top"]:
                lines.append(f"- `{code}` × {cnt}회\n")
        else:
            lines.append("- 없음\n")
        lines.append("\n")

    # ---------- 4. 결론·조치 사항 ----------
    lines.append("## 4. 자동 진단\n\n")
    suggestions = diagnose(db)
    for s in suggestions:
        lines.append(f"- {s}\n")

    db.close()

    # 파일 저장
    with open(report_path, "w", encoding="utf-8") as f:
        f.writelines(lines)
    print(f"리포트 저장: {report_path}")

    # Telegram 요약 (전체 본문은 길어서 핵심만)
    summary = build_telegram_summary(report_path)
    TA.send_tele(summary)
    return report_path


def diagnose(db: ComparisonDB) -> list:
    """자동 진단 — Jaccard·Precision·Recall 패턴으로 튜닝 방향 제안"""
    suggestions = []
    for strategy in STRATEGIES:
        hist = db.get_jaccard_history(strategy, days=30)
        if hist.empty or len(hist) < 5:
            continue
        avg_jac  = hist["jaccard"].mean()
        avg_prec = hist["precision_val"].mean()
        avg_rec  = hist["recall_val"].mean()

        # 진단 룰
        if avg_jac < 0.3:
            suggestions.append(
                f"🔴 **{strategy}**: Jaccard {avg_jac:.2f} 매우 낮음. "
                "전략 로직 재검토 필요 (스코어 함수 또는 필터 임계치).")
        elif avg_jac < 0.5:
            suggestions.append(
                f"🟡 **{strategy}**: Jaccard {avg_jac:.2f}. 개선 여지 있음.")
        else:
            suggestions.append(
                f"🟢 **{strategy}**: Jaccard {avg_jac:.2f} 양호.")

        # Precision < Recall: 클론이 너무 많이 픽함 → 필터 강화
        if avg_prec < avg_rec - 0.1:
            suggestions.append(
                f"   ↳ {strategy}: Precision({avg_prec:.2f}) < Recall({avg_rec:.2f}). "
                "클론 종목 수를 줄이거나 스코어 컷오프를 높이세요.")
        # Recall < Precision: 클론이 너무 적게 픽함 → 필터 완화
        elif avg_rec < avg_prec - 0.1:
            suggestions.append(
                f"   ↳ {strategy}: Recall({avg_rec:.2f}) < Precision({avg_prec:.2f}). "
                "필터 임계치를 완화하거나 top_n을 늘리세요.")

    # 성과 비교 진단
    perf = db.get_performance_summary(days=60)
    if not perf.empty:
        for strategy in STRATEGIES:
            sub = perf[perf["strategy"] == strategy]
            if len(sub) < 2:
                continue
            se = sub[sub["source"] == "stockeasy"]
            cl = sub[sub["source"] == "clone"]
            if se.empty or cl.empty:
                continue
            se_20d = se["avg_20d_pct"].iloc[0]
            cl_20d = cl["avg_20d_pct"].iloc[0]
            if cl_20d > se_20d + 1.0:
                suggestions.append(
                    f"   ↳ {strategy}: 클론 성과({cl_20d:+.1f}%)가 "
                    f"사이트({se_20d:+.1f}%)보다 우수. 클론 로직 유지.")
            elif se_20d > cl_20d + 1.0:
                suggestions.append(
                    f"   ↳ {strategy}: 사이트({se_20d:+.1f}%)가 "
                    f"클론({cl_20d:+.1f}%)보다 우수. 미스매치 종목 분석 필요.")
    return suggestions


def build_telegram_summary(report_path: str) -> str:
    """리포트의 핵심 요약 부분만 추출 (4000자 이내)"""
    with open(report_path, "r", encoding="utf-8") as f:
        content = f.read()
    # 1, 2, 4번 섹션만 (3번은 너무 김)
    sections = content.split("\n## ")
    selected = [sections[0]]   # 제목
    for s in sections[1:]:
        if s.startswith("3."):
            continue
        selected.append("## " + s)
    summary = "\n".join(selected)
    # Telegram HTML 안전화
    summary = summary.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    if len(summary) > 3800:
        summary = summary[:3800] + "...\n\n_전체는 리포트 파일 참조_"
    return f"📋 <b>월간 비교 리포트</b>\n\n<pre>{summary}</pre>"


if __name__ == "__main__":
    generate_monthly_report()
