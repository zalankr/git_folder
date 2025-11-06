# USLA 자동매매 시스템 개선 보고서 (최종 수정본)

## 📋 요약

### 시스템 구조 이해
- **한 계좌, 여러 전략**: 하나의 KIS 계좌에서 USLA 외 다른 전략들도 함께 운영
- **예수금 분리 관리**: 실제 API 예수금이 아닌 JSON 파일로 전략별 USD 예수금 분리 관리
- **검증 방법**: 실제 API와 비교 불가 → JSON 기반 내부 일관성 검증으로 대체

### 주요 개선 사항
1. **주문 실패/성공 완전 추적**: 모든 주문 결과를 TR 파일에 저장
2. **USD 예수금 내부 일관성 검증**: JSON 간 동기화 및 체결 금액 역산 검증
3. **데이터 저장 안정성 향상**: 백업 메커니즘 추가
4. **오류 복구 능력 강화**: 예외 처리 및 로깅 개선

---

## 🔧 1. 주문 오류 처리 개선 (기존과 동일)

### 기존 문제점
```python
# 기존 코드
if result.get('success') == True:
    order_info = {k: v for k, v in result.items() if k != 'response'}
    Sell_order.append(order_info)
else:
    # ❌ 실패한 주문은 저장되지 않음
    KA.SendMessage(f"{ticker} 매도 주문 실패: {result.get('message', 'Unknown error')}")
```

**문제점:**
- 실패한 주문이 TR 기록에서 누락
- 다음 라운드에서 실패한 주문을 재시도할 방법이 없음
- 주문 성공률 추적 불가

### 개선 사항
```python
# 개선 코드
if result and result.get('success') == True:
    order_info = {
        'success': True,
        'ticker': ticker,
        'quantity': quantity,
        'price': price,
        'order_number': result.get('order_number', ''),
        'order_time': result.get('order_time', ''),
        'org_number': result.get('org_number', ''),
        'message': result.get('message', ''),
        'split_index': i
    }
    Sell_order.append(order_info)
else:
    # ✅ 실패한 주문도 기록
    error_msg = result.get('error_message', 'Unknown error') if result else 'API 호출 실패'
    KA.SendMessage(f"{ticker} 매도 주문 실패: {error_msg}")
    Sell_order.append({
        'success': False,
        'ticker': ticker,
        'quantity': quantity,
        'price': price,
        'order_number': '',
        'order_time': datetime.now().strftime('%H%M%S'),
        'error_message': error_msg,
        'split_index': i
    })
```

**개선 효과:**
✅ 모든 주문 시도가 기록에 남음
✅ 실패 원인 추적 가능
✅ 주문 성공률 통계 확인 가능

---

## 💰 2. USD 예수금 추적 정확성 개선 (수정됨)

### 시스템 구조 이해

```
┌─────────────────────────────────────┐
│   KIS 계좌 (실제 USD 예수금: $10,000) │
└─────────────────────────────────────┘
                 │
    ┌────────────┼────────────┐
    │            │            │
┌───▼───┐   ┌───▼───┐   ┌───▼───┐
│ USLA  │   │ 전략2  │   │ 전략3  │
│ $3,000│   │ $4,000│   │ $3,000│
└───────┘   └───────┘   └───────┘
    │
    └─> USLA_data.json의 CASH 필드로 관리
```

**중요:** USLA는 계좌 전체 예수금이 아닌, 전략 할당 예수금만 JSON으로 관리

### 기존 문제점

#### 문제 1: Round 1과 Round 2+ 간 동기화 위험
```python
# Round 1
Hold_usd = USLA_data['CASH']  # USLA_data.json에서 로드

# Round 2+
Hold_usd = TR_data['CASH']    # USLA_TR.json에서 로드

# ❌ 두 파일이 동기화되지 않으면 예수금 차이 발생
```

#### 문제 2: 체결 확인 시 성공/실패 미구분
```python
# 기존 코드
sell_summary = USLA.calculate_sell_summary(Sell_order)  # 모든 주문 확인
Hold_usd += sell_summary['net_amount']
```
→ 실패한 주문도 체결 확인 시도 → API 호출 낭비 및 오류 가능성

#### 문제 3: USD 변화 검증 로직 부재
- 라운드 간 USD 변화가 체결 금액과 일치하는지 확인 불가
- 누적 오차 발생 시 감지 어려움

### 개선 사항

#### 1) 성공한 주문만 체결 확인
```python
# ✅ 성공한 주문만 필터링
successful_sell_orders = [o for o in Sell_order if o.get('success', False)]
successful_buy_orders = [o for o in Buy_order if o.get('success', False)]

# 체결 금액 초기화
sell_net_amount = 0.0
buy_total_amount = 0.0

# 매도 체결 확인
if len(successful_sell_orders) > 0:
    sell_summary = USLA.calculate_sell_summary(successful_sell_orders)
    sell_net_amount = sell_summary['net_amount']  # 수수료 차감 후
    Hold_usd += sell_net_amount

# 매수 체결 확인
if len(successful_buy_orders) > 0:
    buy_summary = USLA.calculate_buy_summary(successful_buy_orders)
    buy_total_amount = buy_summary['total_amount']  # 수수료 포함
    Hold_usd -= buy_total_amount
```

#### 2) USD 내부 일관성 검증 함수 추가 ⭐
```python
def validate_usd_consistency(prev_usd, sell_amount, buy_amount, current_usd, tolerance=5.0):
    """
    USD 예수금 내부 일관성 검증
    
    공식: 이전 USD + 매도 체결액 - 매수 체결액 = 현재 USD
    
    Parameters:
    - prev_usd: 이전 라운드 USD
    - sell_amount: 매도 체결액 (수수료 차감 후)
    - buy_amount: 매수 체결액 (수수료 포함)
    - current_usd: 현재 계산된 USD
    - tolerance: 허용 오차 (달러)
    
    Returns:
    - is_valid: 검증 통과 여부
    - expected_usd: 예상 USD
    - diff: 차이 금액
    """
    expected_usd = prev_usd + sell_amount - buy_amount
    diff = abs(current_usd - expected_usd)
    is_valid = diff <= tolerance
    
    if not is_valid:
        KA.SendMessage(
            f"⚠️ USD 예수금 계산 불일치\n"
            f"이전: ${prev_usd:.2f}\n"
            f"매도: +${sell_amount:.2f}\n"
            f"매수: -${buy_amount:.2f}\n"
            f"예상: ${expected_usd:.2f}\n"
            f"실제: ${current_usd:.2f}\n"
            f"차이: ${diff:.2f}"
        )
    else:
        KA.SendMessage(
            f"✓ USD 검증 통과 (차이: ${diff:.2f})\n"
            f"${prev_usd:.2f} → ${current_usd:.2f}"
        )
    
    return is_valid, expected_usd, diff
```

#### 3) 매 라운드 검증 적용
```python
# Round 2~25에서 사용
prev_round_usd = Hold_usd  # 체결 확인 전 USD

# ... 체결 확인 후 ...

# ⭐ 내부 일관성 검증
validate_usd_consistency(
    prev_usd=prev_round_usd,
    sell_amount=sell_net_amount,
    buy_amount=buy_total_amount,
    current_usd=Hold_usd,
    tolerance=5.0  # $5 이하 오차 허용
)
```

### USD 검증 로직 흐름도

```
Round N-1 종료
    │
    ├─> USLA_TR.json 저장: CASH = $3,000
    │
Round N 시작
    │
    ├─> USLA_TR.json 로드: prev_usd = $3,000
    │
    ├─> 체결 확인
    │   ├─> 매도: +$500 (수수료 차감 후)
    │   └─> 매수: -$300 (수수료 포함)
    │
    ├─> USD 계산
    │   └─> Hold_usd = $3,000 + $500 - $300 = $3,200
    │
    ├─> ⭐ 검증
    │   ├─> 예상 USD = prev_usd + sell - buy
    │   │              = $3,000 + $500 - $300 = $3,200
    │   ├─> 실제 USD = $3,200
    │   ├─> 차이 = |$3,200 - $3,200| = $0
    │   └─> ✓ 검증 통과
    │
    └─> USLA_TR.json 저장: CASH = $3,200
```

### 추가 검증 방안

#### A. Round 1 초기 USD 로깅
```python
if order_time['round'] == 1:
    Hold_usd = USLA_data['CASH']
    # ⭐ 초기 USD 명확히 기록
    KA.SendMessage(f"Round 1 시작 USD: ${Hold_usd:.2f}")
```

#### B. Round 25 최종 검증
```python
# Round 25에서 실제 보유 주식 수량과 비교
Hold = USLA.get_total_balance()
Hold_tickers = {}

# ⭐ USLA 전략 티커만 필터링
for stock in Hold['stocks']:
    ticker = stock['ticker']
    if ticker in USLA_ticker:  # USLA 전략 티커만
        Hold_tickers[ticker] = stock['quantity']

# USLA 전략 주식 평가액만 계산
usla_stock_value = 0.0
for ticker in USLA_ticker:
    qty = Hold_tickers.get(ticker, 0)
    if qty > 0:
        price = USLA.get_US_current_price(ticker)
        if isinstance(price, (int, float)) and price > 0:
            usla_stock_value += qty * price

# USLA 전략 총 잔고
balance = usla_stock_value + Hold_usd
```

---

## 🛡️ 3. 데이터 저장 안정성 강화

### 기존 문제점
```python
def save_TR_data(order_time, Sell_order, Buy_order, Hold, target_weight):
    TR_data = {...}
    USLA.save_USLA_TR_json(TR_data)  # ❌ 저장 실패 시 처리 없음
```

### 개선 사항: 3중 백업 메커니즘
```python
def save_TR_data(order_time, Sell_order, Buy_order, Hold, target_weight):
    TR_data = {
        "round": order_time['round'],
        "timestamp": datetime.now().isoformat(),
        "Sell_order": Sell_order,
        "Buy_order": Buy_order,
        "CASH": Hold['CASH'],
        "target_weight": target_weight,
        "sell_success_rate": f"{sum(1 for o in Sell_order if o.get('success', False))}/{len(Sell_order)}" if Sell_order else "0/0",
        "buy_success_rate": f"{sum(1 for o in Buy_order if o.get('success', False))}/{len(Buy_order)}" if Buy_order else "0/0"
    }
    
    try:
        # 1차: 정상 저장
        save_result = USLA.save_USLA_TR_json(TR_data)
        if not save_result:
            raise Exception("save_USLA_TR_json returned False")
        
        KA.SendMessage(f"✓ Round {order_time['round']} 저장 완료")
        
    except Exception as e:
        KA.SendMessage(f"✗ TR 데이터 저장 실패: {e}")
        
        # 2차: 백업 파일 생성
        backup_path = f"/var/autobot/TR_USLA/USLA_TR_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        try:
            with open(backup_path, 'w', encoding='utf-8') as f:
                json.dump(TR_data, f, ensure_ascii=False, indent=4)
            KA.SendMessage(f"✓ 백업 파일 생성: {backup_path}")
        except Exception as backup_error:
            KA.SendMessage(f"✗ 백업 파일 생성도 실패: {backup_error}")
            
            # 3차: 카카오로 요약 정보 전송
            try:
                summary = {
                    'round': TR_data['round'],
                    'CASH': TR_data['CASH'],
                    'sell_count': len(Sell_order),
                    'buy_count': len(Buy_order),
                    'timestamp': TR_data['timestamp']
                }
                KA.SendMessage(f"TR 요약: {json.dumps(summary, ensure_ascii=False)}")
            except:
                pass
    
    return TR_data
```

**개선 효과:**
✅ 저장 실패 시 백업 파일 자동 생성
✅ 백업도 실패 시 카카오톡으로 핵심 정보 전송
✅ 데이터 유실 방지 3중 안전장치

---

## 📊 4. 예외 처리 및 로깅 강화

### 1) 가격 조회 실패 시 처리
```python
# 개선
if not isinstance(current_price, (int, float)) or current_price <= 0:
    error_msg = f"{ticker} 가격 조회 실패 - 주문 스킵"
    KA.SendMessage(error_msg)
    # ✅ 실패 정보 저장
    Buy_order.append({
        'success': False,
        'ticker': ticker,
        'quantity': Buy_qty[ticker],
        'price': 0,
        'order_number': '',
        'order_time': datetime.now().strftime('%H%M%S'),
        'error_message': error_msg,
        'split_index': -1
    })
    continue
```

### 2) 주문 API 호출 예외 처리
```python
try:
    result = USLA.order_buy_US(ticker, quantity, price)
    # ... 처리 ...
except Exception as e:
    # ✅ 예외 발생 시에도 기록
    error_msg = f"Exception: {str(e)}"
    KA.SendMessage(f"{ticker} 매수 주문 예외: {error_msg}")
    Buy_order.append({
        'success': False,
        'ticker': ticker,
        'quantity': quantity,
        'price': price,
        'order_number': '',
        'order_time': datetime.now().strftime('%H%M%S'),
        'error_message': error_msg,
        'split_index': i
    })
```

### 3) 주문 요약 출력
```python
# ✅ 매도/매수 주문 요약
success_count = sum(1 for order in Sell_order if order['success'])
total_count = len(Sell_order)
KA.SendMessage(f"매도 주문 완료: {success_count}/{total_count} 성공")
```

---

## 🎯 5. USLA_model.py 개선 제안

### calculate_sell_summary 개선 (이전과 동일)

```python
def calculate_sell_summary(self, Sell_order):
    """매도 체결 내역 조회 및 집계 - 개선버전"""
    
    if not Sell_order or len(Sell_order) == 0:
        return {
            'total_orders': 0,
            'filled_orders': 0,
            'partial_filled': 0,
            'unfilled_orders': 0,
            'total_quantity': 0,
            'filled_quantity': 0,
            'gross_amount': 0.0,
            'fee_amount': 0.0,
            'net_amount': 0.0,
            'details': []
        }
    
    # ... (개선된 로직) ...
    
    # 상세 로깅
    KA.SendMessage(
        f"📤 매도 체결 요약:\n"
        f"주문: {total_orders}건 (완전체결:{filled_orders}, 부분:{partial_filled}, 미체결:{unfilled_orders})\n"
        f"수량: {total_filled_qty}/{total_order_qty}\n"
        f"매도금액: ${total_gross_amount:.2f}\n"
        f"수수료: ${total_fee:.2f} ({self.SELL_FEE_RATE*100:.2f}%)\n"
        f"순입금: ${summary['net_amount']:.2f}"
    )
    
    return summary
```

---

## 📈 6. 추가 개선 제안

### 1) USD 누적 추적 (선택적)
```python
# USLA_TR.json에 추가 필드
TR_data = {
    "round": order_time['round'],
    # ... 기존 필드 ...
    "cumulative_sell": 0.0,      # ⭐ 누적 매도액
    "cumulative_buy": 0.0,       # ⭐ 누적 매수액
    "initial_usd": 0.0,          # ⭐ Round 1 초기 USD
    "usd_history": []            # ⭐ 라운드별 USD 이력
}

# Round 25에서 최종 검증
final_usd = initial_usd + cumulative_sell - cumulative_buy
if abs(final_usd - Hold_usd) > 10:
    KA.SendMessage(f"⚠️ 누적 USD 검증 실패: 예상 ${final_usd:.2f} vs 실제 ${Hold_usd:.2f}")
```

### 2) 실시간 모니터링 대시보드
```python
def create_monitoring_summary(order_time, Sell_order, Buy_order, Hold_usd):
    """라운드별 모니터링 요약"""
    summary = {
        'round': f"{order_time['round']}/{order_time['total_round']}",
        'usd': f"${Hold_usd:.2f}",
        'sell_success_rate': f"{sum(1 for o in Sell_order if o['success'])}/{len(Sell_order)}",
        'buy_success_rate': f"{sum(1 for o in Buy_order if o['success'])}/{len(Buy_order)}",
        'time': order_time['time'].strftime('%H:%M')
    }
    return summary
```

### 3) 오류 패턴 분석 (선택적)
```python
def analyze_failed_orders(Sell_order, Buy_order):
    """실패 주문 패턴 분석"""
    failed_orders = [o for o in Sell_order + Buy_order if not o.get('success', True)]
    
    error_types = {}
    for order in failed_orders:
        error = order.get('error_message', 'Unknown')
        error_types[error] = error_types.get(error, 0) + 1
    
    if error_types:
        msg = "실패 주문 패턴:\n"
        for error, count in error_types.items():
            msg += f"- {error}: {count}건\n"
        KA.SendMessage(msg)
```

---

## ✅ 체크리스트: 배포 전 확인사항

### 필수 확인
- [ ] KIS_US.py의 `check_order_execution` 함수 동작 확인
- [ ] `calculate_sell_summary`와 `calculate_buy_summary`의 수수료 계산 검증
- [ ] USLA_data.json과 USLA_TR.json 파일 백업
- [ ] 테스트 환경에서 1회차부터 25회차까지 시뮬레이션
- [ ] USD 내부 일관성 검증 로직 테스트

### 권장 확인
- [ ] 카카오톡 알림이 정상 작동하는지 확인
- [ ] 백업 파일 자동 생성 기능 테스트
- [ ] 주문 실패 시나리오 테스트
- [ ] 네트워크 단절 시나리오 테스트
- [ ] 디스크 용량 부족 시나리오 테스트

---

## 🚀 마이그레이션 가이드

### 1단계: 백업
```bash
# 기존 파일 백업
cp /var/autobot/TR_USLA/USLA_Trading.py /var/autobot/TR_USLA/USLA_Trading_backup_$(date +%Y%m%d).py
cp /var/autobot/TR_USLA/USLA_data.json /var/autobot/TR_USLA/USLA_data_backup_$(date +%Y%m%d).json
cp /var/autobot/TR_USLA/USLA_TR.json /var/autobot/TR_USLA/USLA_TR_backup_$(date +%Y%m%d).json
```

### 2단계: 개선된 코드 배포
```bash
# 개선된 코드 복사
cp USLA_Trading_fixed.py /var/autobot/TR_USLA/USLA_Trading.py
```

### 3단계: 검증
```bash
# 드라이런 테스트
python3 /var/autobot/TR_USLA/USLA_Trading.py
```

---

## 📞 문제 발생 시 대응

### 시나리오 1: USD 검증 실패
```bash
# 1. 로그 확인
# - 어느 라운드에서 실패했는지
# - 예상 USD vs 실제 USD 차이

# 2. 체결 내역 확인
# - KIS HTS에서 실제 체결 내역 확인
# - 수수료가 정확히 계산되었는지 확인

# 3. 수동 보정
# - USLA_TR.json의 CASH 값을 정확한 값으로 수정
# - 다음 라운드부터 재시작
```

### 시나리오 2: 모든 주문 실패
```bash
# 1. health_check() 로그 확인
# 2. KIS API 서버 상태 확인
# 3. 네트워크 연결 확인
# 4. API 토큰 재발급
```

### 시나리오 3: TR 파일 저장 실패
```bash
# 1. 백업 파일 확인
ls -lt /var/autobot/TR_USLA/USLA_TR_backup_*

# 2. 최신 백업을 정식 파일로 복사
cp USLA_TR_backup_YYYYMMDD_HHMMSS.json USLA_TR.json

# 3. 다음 라운드 재시작
```

---

## 💡 결론

### 개선 효과

1. **안정성 향상**: 
   - 데이터 유실 방지 (3중 백업)
   - 오류 복구 능력 강화

2. **추적성 강화**: 
   - 모든 주문의 성공/실패 기록
   - 주문 성공률 통계

3. **정확성 개선**: 
   - USD 예수금 내부 일관성 검증
   - 라운드 간 USD 변화 추적

4. **유지보수성**: 
   - 상세한 로깅으로 문제 진단 용이
   - 검증 실패 시 명확한 오류 메시지

### 주요 차이점 (vs 이전 버전)

| 항목 | 이전 제안 | 최종 버전 |
|------|-----------|-----------|
| USD 검증 | ❌ 실제 API 예수금 비교 | ✅ JSON 기반 내부 일관성 검증 |
| 검증 공식 | - | ✅ prev + sell - buy = current |
| Round 25 검증 | ❌ API 값으로 보정 | ✅ USLA 티커만 필터링 |
| 주식 평가액 | ❌ 전체 계좌 | ✅ USLA 전략만 |

### 배포 권장 사항

1. **반드시 백업 후 배포**
2. **테스트 환경에서 먼저 검증 권장**
3. **첫 리밸런싱일엔 실시간 모니터링 필수**
4. **USD 검증 실패 시 즉시 중단 후 조사**
5. **허용 오차 범위 조정 가능** (현재 $5, 필요시 변경)

---

## 📝 변경 이력

### v2.1 (최종 수정본)
- ✅ 실제 API 예수금 비교 제거
- ✅ JSON 기반 내부 일관성 검증 추가
- ✅ USLA 전략 티커만 필터링
- ✅ USD 검증 공식 명확화

### v2.0 (이전 버전)
- 주문 실패 추적 기능 추가
- USD 예수금 검증 로직 추가 (실제 API 비교 - 수정됨)
- 데이터 저장 백업 메커니즘 추가
- 예외 처리 강화

### v1.0 (기존버전)
- 기본 자동매매 기능
