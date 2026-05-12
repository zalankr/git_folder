"""
KRFUTURE_monthly.csv → krfuture_monthly.json 변환 (일회성)

CSV 컬럼: 월, KOSPI, KOSDAQ, KOSPI PBR, VKOSPI
- 날짜 라벨은 "해당 월 월말 종가" → JSON 키는 YYYY-MM (월만)
- 정렬: 오래된 순(asc) 으로 저장

생성 JSON 구조:
{
  "data": {
    "1999-01": {"kospi":571.00, "kosdaq":761.60, "kospi_pbr":0.95, "vkospi":20.0},
    ...
    "2026-04": {"kospi":6598.87, "kosdaq":1192.35, "kospi_pbr":2.11, "vkospi":59.64}
  },
  "positions": {
    "boost":  {"stage":0, "entry_month":null, "expire_month":null, "ratio":0.0},
    "hedge1": {"active":false, "entry_month":null, "signal_end_month":null,
               "exit_month":null, "ratio":0.0},
    "hedge2": {"active":false, "entry_month":null, "expire_month":null, "ratio":0.0}
  },
  "signals": {}
}
"""

import csv
import json
from pathlib import Path

SRC = "/mnt/user-data/uploads/KRFUTURE_monthly.csv"
DST = "/home/claude/krfuture_monthly.json"


def parse_row(row):
    """CSV 한 행 → (yyyy_mm, dict) 또는 None"""
    date_str = row["월"].strip()
    yyyy_mm = date_str[:7]  # "2026-04-01" → "2026-04"

    def f(key):
        v = row[key].strip().replace(",", "")
        return float(v) if v else None

    return yyyy_mm, {
        "kospi":     f("KOSPI"),
        "kosdaq":    f("KOSDAQ"),
        "kospi_pbr": f("KOSPI PBR"),
        "vkospi":    f("VKOSPI"),
    }


def main():
    data = {}
    with open(SRC, encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            ym, vals = parse_row(row)
            data[ym] = vals

    # 오래된 순으로 정렬
    sorted_data = dict(sorted(data.items()))

    out = {
        "data": sorted_data,
        "positions": {
            "boost":  {"stage": 0, "entry_month": None, "expire_month": None, "ratio": 0.0},
            "hedge1": {"active": False, "entry_month": None, "signal_end_month": None,
                       "exit_month": None, "ratio": 0.0},
            "hedge2": {"active": False, "entry_month": None, "expire_month": None, "ratio": 0.0},
        },
        "signals": {},
    }

    Path(DST).write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"saved: {DST}")
    print(f"rows : {len(sorted_data)}  ({list(sorted_data.keys())[0]} ~ {list(sorted_data.keys())[-1]})")
    print("\nlatest 3 rows:")
    for k in list(sorted_data.keys())[-3:]:
        print(f"  {k}: {sorted_data[k]}")


if __name__ == "__main__":
    main()
