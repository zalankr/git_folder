# USQT 분기 리밸런싱 + 헤지 통합 시스템

USQT(분기별 미국 주식 퀀트 리밸런싱)에 SPY 추세/모멘텀/변동성/RSI 기반 헤지를 결합한 자동매매 시스템.

---

## 📂 파일 구성

### 코드
| 파일 | 경로 | 역할 |
|---|---|---|
| `USQT_TR.py` | `/var/autobot/TR_USQT/` | 분기 리밸 14회차 + 헤지 비중 통합 |
| `USQT_Hedge.py` | `/var/autobot/TR_USQT/` | 헤지 24회차 매매 |
| `USQT_Hedge_signal.py` | `/var/autobot/TR_USQT/` | SPY/IEF 신호 계산 |
| `USQT_Calender.py` | `/var/autobot/TR_USAA/` | 헤지일/리밸일 판정 + 회차 매핑 |
| `gen_hedge_days.py` | `/var/autobot/TR_USQT/` | 헤지일 자동 생성 |

### 설정 / 상태 JSON
| 파일 | 경로 | 용도 | 수정 |
|---|---|---|---|
| `USQT_stock.csv` | `/var/autobot/TR_USQT/` | 분기별 USQT 종목 리스트 | **수동** (분기 리밸 직전) |
| `USQT_day.json` | `/var/autobot/TR_USQT/` | 리밸일 (`rebal_dates`) | **수동** (분기 리밸 직전) |
| `USQT_hedge_day.json` | `/var/autobot/TR_USQT/` | 헤지일 (DST/EST 분리) | **자동** (`gen_hedge_days.py`) |
| `USQT_hedge_state.json` | `/var/autobot/TR_USQT/` | 헤지 상태/현재비중/`active_trading_day` | **자동** (스크립트 갱신) |
| `USQT_target.json` | `/var/autobot/TR_USQT/` | 분기 리밸 target 보관 | **자동** |
| `USQT_hedge_target.json` | `/var/autobot/TR_USQT/` | 헤지 24회차 target 보관 | **자동** |
| `USQT_result.json` | `/var/autobot/TR_USQT/` | 분기 리밸 결과 보고 | **자동** |
| `USQT_rebal.json` | `/var/autobot/TR_USQT/` | 분기 리밸 자산 변동 | **자동** |

---

## ⚙ Crontab 설정

```bash
# ============================================
# USQT 통합 매매 시스템
# 모든 스크립트가 자체 일정 판단 → 크론은 항상 활성
# ============================================

# USQT 헤지 24회차 매매 (DST/EST 모두 커버, 매일 26회 호출 중 24회 실제 동작)
0,30 8-20 * * 1-5  timeout -s 9 28m /usr/bin/python3 /var/autobot/TR_USQT/USQT_Hedge.py

# USQT 분기 리밸 14회차 (DST 7회/EST 7회 × 2일 = 14회)
32 13-20 * * 1-5  timeout -s 9 35m /usr/bin/python3 /var/autobot/TR_USQT/USQT_TR.py

# 헤지일 자동 갱신 (매주 일요일 UTC 12:00 = KST 21:00)
0 12 * * 0  /usr/bin/python3 /var/autobot/TR_USQT/gen_hedge_days.py --quiet
```

### 시간 매핑 (UTC 기준)

#### 헤지 매매 (USQT_Hedge.py)
| 슬롯 | DST 시각 | EST 시각 |
|---|---|---|
| 1회차 | 08:00 | 09:00 |
| 12회차 | 13:30 | 14:30 |
| 24회차 | 19:30 | 20:30 |

#### 분기 리밸 (USQT_TR.py)
| 슬롯 | DST 시각 | EST 시각 |
|---|---|---|
| 1회차 (day1) | 13:32 | 14:32 |
| 7회차 (day1) | 19:32 | 20:32 |
| 8회차 (day2) | 13:32 | 14:32 |
| 14회차 (day2) | 19:32 | 20:32 |

---

## 🔄 운영 흐름

### 자동 동작 (크론에 의한 매일/매주)

```
매일 평일 (월~금)
├─ USQT_Hedge.py (매 30분, 1일 26회 호출)
│   ├─ 비거래일/리밸일/매매시간 아님 → 조용히 종료
│   ├─ 헤지 매매일 1회차 → 신호 계산 + target 산출 + 매매 결정
│   │   ├─ 매매 0건 → "변경 없음" 알림 1회 + active_trading_day=1970-01-01 + 종료
│   │   └─ 매매 1건+ → active_trading_day=오늘 저장 + 매매 진행
│   ├─ 2~23회차 → active_trading_day 일치 시만 매매, 아니면 조용히 종료
│   └─ 24회차 → 최종 보고 + active_trading_day 클리어
│
└─ USQT_TR.py (매 정시 32분, 1일 8회 호출)
    └─ rebal_dates 미등록일 → 조용히 종료

매주 일요일 12:00 UTC
└─ gen_hedge_days.py → USQT_hedge_day.json 1년치 자동 갱신
```

### 수동 작업 (분기 리밸 직전, 분기 1회)

```bash
# 1. 신규 USQT 종목 리스트 업데이트
nano /var/autobot/TR_USQT/USQT_stock.csv

# 2. 리밸 일자 등록 (2일치)
nano /var/autobot/TR_USQT/USQT_day.json
# {
#     "day": 1,
#     "rebal_dates": ["2026-06-29", "2026-06-30"]
# }
```

리밸 일자 양일에 USQT_TR.py가 14회차 자동 동작합니다.

---

## 📨 텔레그램 알림 시나리오

### A. 평일 평상시 (헤지일/리밸일 아님)
**알림 없음.** (크론은 매일 30분마다 실행되지만 스크립트가 즉시 조용히 종료)

### B. 헤지일 - 신호 변경 없음 (가장 흔한 경우)
**1회차에 알림 1회만:**
```
USQT_Hedge: 2026-06-08 1/24회차 시작 (season=USQT_hedge_summer)
USQT_Hedge: 0/0 주문 취소
USQT 신호 [2026-06-05]: SPY=621.45 MA200=580.12 ab200=True MOM12=+12.3% VOL20=14.2%(low) RSI14=45.0 ...
USQT 결정: RSI 신호 변경 없음: RSI14=45.0 (진입조건 28 미달)
USQT_Hedge 적용 비중 [no_change]: USQT=85.00%, IAU=15.00%, BOND(IEF)=0.00%
USQT_Hedge 총자산: $15,230.45 (주식:$12,940.20 + 현금:$2,290.25)
USQT_Hedge: 헤지 비중 변경 없음 → 매매 종목 0건. 오늘 24회차 매매 모두 스킵하고 종료.
```
2~24회차는 active_trading_day 미일치로 조용히 종료.

### C. 헤지일 - RSI 진입 (USQT 85% → 45%)
**1회차 알림:**
```
USQT_Hedge: 2026-06-08 1/24회차 시작
USQT 신호 [2026-06-05]: SPY=590.20 MA200=595.00 ab200=False MOM12=-3.2% VOL20=22.5%(mid) RSI14=25.0 ...
USQT 결정: RSI 헤지 진입: RSI14=25.00 < 28 → hedge_target={...}
USQT_Hedge 적용 비중 [rsi_enter]: USQT=45.00%, IAU=35.00%, BOND(SGOV)=20.00%
USQT_Hedge 총자산: $15,230.45
[target 저장 완료]
USQT_Hedge: 매매 진행 결정 → 매도 30종목, 매수 2종목, 오늘 24회차 매매 활성화
USQT_Hedge: 1회차 - 매도 주문
매도 AMC 152주 $1.52 #0001234
... (30종목)
USQT_Hedge 매수가능: $X | 목표매수금: $Y | 조정: 0.43
USQT_Hedge 매수수량 조정 (adjust=0.43)
USQT_Hedge: 1회차 - 매수 주문
매수 IAU 95주 $52.10 #...
매수 SGOV 30주 $100.25 #...
```

**2~23회차 알림** (각 회차마다 매도/매수 진행):
```
USQT_Hedge: 2026-06-08 2/24회차 시작
USQT_Hedge: N/N 주문 취소
USQT_Hedge: 2회차 - 매도 주문 ...
USQT_Hedge: 2회차 - 매수 주문 ...
```

**24회차 마무리 알림:**
```
USQT_Hedge: N/N 주문 취소
USQT_Hedge 2026-06-08 헤지 매매 종료
USQT_Hedge 최종 주식 평가금: $14,820.30
USQT_Hedge 최종 USD 가용: $410.15
USQT_Hedge 총 자산: $15,230.45
USQT_Hedge: active_trading_day 클리어 → 다음 매매일 대기
```

### D. 분기 리밸일 (헤지 통합)
**1회차/8회차 (각 day의 첫 회차)**:
```
USQT: 1일차 1/14회차 매매 시작 (헤지 통합)
USQT 신호 [2026-06-26]: ... (월말 정기 신호일이면 신호 재계산)
USQT 결정: 월말 정기 신호 적용 ...
USQT 적용비중[monthly]: USQT=85.00%, IAU=15.00%, BOND(IEF)=0.00%
USQT 총자산: $...
[종목별 매도/매수 알림]
```

**2~13회차 알림** (매 회차 매매 진행)

**14회차 마무리** (분기 리밸 최종 결과 보고)

---

## 🛡 안전장치 요약

1. **`tendo` 싱글톤** — 두 스크립트 동시 실행 방지
2. **`active_trading_day` 플래그** — 1회차에 매매 결정 시만 다음 회차들 활성화
3. **`ord_psbl_qty` 캡핑** — T+1 미결제 매도 방어
4. **8회차 `target_qty` floor** — day2 시작 시 현재 보유보다 낮춰 매도하지 않음
5. **신호 계산 실패 → 직전 비중 유지** — API 장애 시에도 비매매 안전 종료
6. **`MAX_PAGE=30` 페이지네이션 상한** — 잔고 조회 무한 루프 방지
7. **TTTS3007R로 주문가능금액 조회** — MTS 화면과 동일한 실제 가용 USD
8. **`ccld_qty_smtl1` 사용** — 라운드 간 정확한 보유 수량 (T+1 무관)
9. **분기 리밸일/헤지일 자동 분리** — 분기 리밸일엔 USQT_Hedge.py가 즉시 종료, USQT_TR.py가 통합 처리
10. **크론 항상 활성** — 일정 등록만 하면 자동 동작 (휴가 중에도 안전)

---

## 🚀 초기 배포 체크리스트

```bash
# 1. 폴더 생성 + 파일 배치
mkdir -p /var/autobot/TR_USQT
cp USQT_TR.py USQT_Hedge.py USQT_Hedge_signal.py gen_hedge_days.py /var/autobot/TR_USQT/
cp USQT_Calender.py /var/autobot/TR_USAA/

# 2. 초기 JSON 배치
cp USQT_hedge_state.json /var/autobot/TR_USQT/
cp USQT_hedge_day.json   /var/autobot/TR_USQT/
cp USQT_day.json         /var/autobot/TR_USQT/
# USQT_stock.csv 는 별도 준비

# 3. 권장 의존성 설치
pip install exchange_calendars holidays pytz pandas numpy tendo --break-system-packages

# 4. 헤지일 자동 생성 (1년치 초기 등록)
python3 /var/autobot/TR_USQT/gen_hedge_days.py

# 5. 크론 등록
crontab -e
# 위 Crontab 설정 섹션 내용 붙여넣기

# 6. 첫 배포 시 안전을 위해 dry-run 확인 권장
#    - USQT_Hedge.py 를 헤지일에 수동 실행해서 신호 산출만 확인
#    - 운영자 판단으로 active_trading_day=1970-01-01 유지하여 매매 차단 가능
```

---

## 📋 운영 중 자주 쓰는 명령

```bash
# 헤지 상태 확인
cat /var/autobot/TR_USQT/USQT_hedge_state.json

# 헤지일 갱신 (드라이런)
python3 /var/autobot/TR_USQT/gen_hedge_days.py --dry-run

# 헤지일 1년 강제 재생성 (수동 등록 모두 삭제)
python3 /var/autobot/TR_USQT/gen_hedge_days.py --overwrite

# 분기 리밸 일자 등록
nano /var/autobot/TR_USQT/USQT_day.json

# 신호 계산만 수동 확인 (REPL)
python3 -c "
import sys; sys.path.insert(0, '/var/autobot/TR_USQT')
import KIS_US, USQT_Hedge_signal as Sig
K = KIS_US.KIS_API('/var/autobot/KIS/kis63692011nkr.txt',
                   '/var/autobot/KIS/kis63692011_token.json',
                   '63692011', '01')
s = Sig.compute_signals(K)
print(s)
"
```

---

## 🔧 트러블슈팅

### Q. 매매가 시작되지 않음 (1회차에서 종료)
→ `USQT_hedge_state.json` 의 `current_target` 과 실제 보유가 일치한 경우 정상. 매매 0건이면 자동 종료됨.

### Q. 2회차 이후가 실행되지 않음
→ `active_trading_day` 가 오늘 날짜와 일치해야 함. 1회차 알림에서 "매매 진행 결정" 메시지가 있었는지 확인.

### Q. 신호 계산이 자꾸 실패함
→ KIS API HHDFS76240000 응답 확인. SPY/IEF 300일치 데이터 fetch 가 느릴 수 있으므로 1회차 타임아웃이 충분한지 점검 (`timeout -s 9 28m` 권장).

### Q. 분기 리밸 + 헤지일이 겹친 날
→ USQT_TR.py 가 통합 처리. USQT_Hedge.py 는 분기 리밸일 감지 시 즉시 종료. 텔레그램 알림은 USQT_TR.py 에서만 발송됨.

### Q. DST/EST 전환 직후 누락
→ 크론이 항상 활성이라 자동 처리됨. `is_us_dst()` 가 매번 실시간 판단.
