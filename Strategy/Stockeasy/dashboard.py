#!/usr/bin/env python3
"""
대시보드 HTML 생성기 (Plotly.js, 정적 HTML)

매주 일요일 KST 09:00 실행 또는 수동 실행:
  python3 dashboard.py

출력: /var/autobot/Reports/dashboard.html
  → S3나 GitHub Pages에 올려서 모바일에서도 열람 가능
  → 또는 EC2 nginx로 서빙

차트:
  1. 전략별 Jaccard/Precision/Recall 추이 (시계열)
  2. 종목 수 추이 (StockEasy vs Clone)
  3. 60일 누적 성과 비교 (전략 × source)
"""
import os
import json
import duckdb
import pandas as pd
from datetime import datetime

DB_PATH = "/var/autobot/DB/comparison.duckdb"
OUTPUT  = "/var/autobot/Reports/dashboard.html"

HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<title>StockEasy 비교 대시보드</title>
<script src="https://cdn.plot.ly/plotly-2.30.0.min.js"></script>
<style>
  body { font-family: -apple-system, "Apple SD Gothic Neo", sans-serif; margin: 20px; background: #fafafa; }
  h1 { color: #1a1a1a; }
  h2 { color: #444; border-bottom: 2px solid #e0e0e0; padding-bottom: 6px; margin-top: 32px; }
  .meta { color: #888; font-size: 13px; margin-bottom: 24px; }
  .chart { background: white; padding: 16px; border-radius: 8px;
           box-shadow: 0 1px 3px rgba(0,0,0,0.06); margin-bottom: 16px; }
  table { border-collapse: collapse; margin: 16px 0; background: white; }
  th, td { border: 1px solid #e0e0e0; padding: 8px 12px; text-align: right; }
  th { background: #f5f5f5; }
  td:first-child, th:first-child { text-align: left; }
</style>
</head>
<body>
<h1>📊 StockEasy 비교 대시보드</h1>
<p class="meta">생성: __TIMESTAMP__ | DB: comparison.duckdb</p>

<h2>1. 일치도 추이 (Jaccard)</h2>
<div id="chart_jaccard" class="chart"></div>

<h2>2. Precision & Recall</h2>
<div id="chart_pr" class="chart"></div>

<h2>3. 종목 수 추이</h2>
<div id="chart_counts" class="chart"></div>

<h2>4. 60일 성과 비교</h2>
<div id="chart_perf" class="chart"></div>

<h2>5. 최근 30일 요약 테이블</h2>
__SUMMARY_TABLE__

<script>
const dataJaccard = __DATA_JACCARD__;
const dataPR = __DATA_PR__;
const dataCounts = __DATA_COUNTS__;
const dataPerf = __DATA_PERF__;

Plotly.newPlot('chart_jaccard', dataJaccard, {
  title: 'Jaccard 일치도', yaxis: {range:[0,1], title:'Jaccard'},
  hovermode:'x unified', height: 400
}, {responsive:true});

Plotly.newPlot('chart_pr', dataPR, {
  title: 'Precision (클론 정확도) & Recall (사이트 커버리지)',
  yaxis: {range:[0,1]}, hovermode:'x unified', height: 400
}, {responsive:true});

Plotly.newPlot('chart_counts', dataCounts, {
  title: '일별 종목 수', hovermode:'x unified', height: 400
}, {responsive:true});

Plotly.newPlot('chart_perf', dataPerf, {
  title: '평균 20일 수익률 (%) — StockEasy vs Clone',
  barmode: 'group', height: 400
}, {responsive:true});
</script>
</body>
</html>
"""


def build_dashboard():
    if not os.path.exists(DB_PATH):
        print(f"DB 없음: {DB_PATH}")
        return

    conn = duckdb.connect(DB_PATH, read_only=True)

    # 1. Jaccard 시계열
    jac_df = conn.execute("""
        SELECT date, strategy, jaccard, precision_val, recall_val,
               stockeasy_n, clone_n
          FROM comparison_daily
         WHERE date >= CURRENT_DATE - 180
         ORDER BY date
    """).df()

    data_jaccard, data_pr, data_counts = [], [], []
    for strategy in ("PEAK", "MOMENTUM", "VALUE"):
        sub = jac_df[jac_df["strategy"] == strategy]
        if sub.empty:
            continue
        x = sub["date"].astype(str).tolist()
        data_jaccard.append({
            "x": x, "y": sub["jaccard"].tolist(),
            "name": strategy, "type": "scatter", "mode": "lines+markers"
        })
        data_pr.append({
            "x": x, "y": sub["precision_val"].tolist(),
            "name": f"{strategy} Precision", "type": "scatter",
            "mode": "lines", "line": {"dash": "solid"}
        })
        data_pr.append({
            "x": x, "y": sub["recall_val"].tolist(),
            "name": f"{strategy} Recall", "type": "scatter",
            "mode": "lines", "line": {"dash": "dot"}
        })
        data_counts.append({
            "x": x, "y": sub["stockeasy_n"].tolist(),
            "name": f"{strategy} SE", "type": "scatter", "mode": "lines"
        })
        data_counts.append({
            "x": x, "y": sub["clone_n"].tolist(),
            "name": f"{strategy} Clone", "type": "scatter",
            "mode": "lines", "line": {"dash": "dash"}
        })

    # 2. 성과 비교 (막대)
    perf_df = conn.execute("""
        SELECT strategy, source,
               AVG(ret_20d) * 100 AS avg_20d
          FROM performance_daily
         WHERE pick_date >= CURRENT_DATE - 60
           AND ret_20d IS NOT NULL
         GROUP BY strategy, source
         ORDER BY strategy, source
    """).df()

    data_perf = []
    if not perf_df.empty:
        for src in ("stockeasy", "clone"):
            sub = perf_df[perf_df["source"] == src]
            data_perf.append({
                "x": sub["strategy"].tolist(),
                "y": sub["avg_20d"].round(2).tolist(),
                "name": src.capitalize(),
                "type": "bar"
            })

    # 3. 요약 테이블 (HTML)
    table_html = "<table>\n<tr><th>전략</th><th>평균 Jaccard</th><th>평균 Precision</th>"
    table_html += "<th>평균 Recall</th><th>평균 SE n</th><th>평균 Clone n</th></tr>\n"
    for strategy in ("PEAK", "MOMENTUM", "VALUE"):
        sub = jac_df[(jac_df["strategy"] == strategy) &
                     (jac_df["date"] >= (datetime.now().date() - pd.Timedelta(days=30)))]
        if sub.empty:
            table_html += f"<tr><td>{strategy}</td><td colspan='5'>—</td></tr>\n"
        else:
            table_html += (f"<tr><td>{strategy}</td>"
                           f"<td>{sub['jaccard'].mean():.3f}</td>"
                           f"<td>{sub['precision_val'].mean():.3f}</td>"
                           f"<td>{sub['recall_val'].mean():.3f}</td>"
                           f"<td>{sub['stockeasy_n'].mean():.1f}</td>"
                           f"<td>{sub['clone_n'].mean():.1f}</td></tr>\n")
    table_html += "</table>"

    conn.close()

    html = (HTML_TEMPLATE
            .replace("__TIMESTAMP__", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
            .replace("__DATA_JACCARD__", json.dumps(data_jaccard, default=str))
            .replace("__DATA_PR__",      json.dumps(data_pr, default=str))
            .replace("__DATA_COUNTS__",  json.dumps(data_counts, default=str))
            .replace("__DATA_PERF__",    json.dumps(data_perf, default=str))
            .replace("__SUMMARY_TABLE__", table_html))

    os.makedirs(os.path.dirname(OUTPUT), exist_ok=True)
    with open(OUTPUT, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"대시보드 생성: {OUTPUT}")


if __name__ == "__main__":
    build_dashboard()
