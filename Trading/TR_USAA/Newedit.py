# ========================================
# 치명적 에러 수정 패치 (간결한 버전)
# ========================================

# ========================================
# 1. ZeroDivisionError 방지 (1357, 1368라인)
# ========================================
# 기존:
# USLA_target_qty = int((USLA[ticker]['target_weight'] * Total_balance) / USLA[ticker]['current_price'])

# 수정:
for ticker in USLA_ticker:
    USLA[ticker]['hold_qty'] = USLA_qty[ticker]
    USLA[ticker]['current_price'] = USLA_price[ticker]
    
    # 가격 0 체크
    if USLA[ticker]['current_price'] <= 0:
        USLA[ticker]['target_qty'] = 0
        USLA[ticker]['buy_qty'] = 0
        USLA[ticker]['sell_qty'] = USLA_qty[ticker]
        continue
    
    USLA_target_qty = int((USLA[ticker]['target_weight'] * Total_balance) / USLA[ticker]['current_price'])
    USLA_target_balance = USLA[ticker]['target_weight'] * Total_balance
    USLA[ticker]['target_balance'] = USLA_target_balance
    USLA[ticker]['target_qty'] = USLA_target_qty
    USLA[ticker]['buy_qty'] = max(0, USLA_target_qty - USLA_qty[ticker])
    USLA[ticker]['sell_qty'] = max(0, USLA_qty[ticker] - USLA_target_qty)

# HAA도 동일


# ========================================
# 2. TIP 티커 처리 (96-97라인)
# ========================================
# 기존:
# if ticker == 'TIP':
#     continue

# 수정: TIP도 정상 처리
for ticker in HAA_ticker:
    balance = KIS.get_ticker_balance(ticker)
    if balance:
        eval_amount = balance.get('eval_amount', 0)
        HAA_qty[ticker] = balance.get('holding_qty', 0)
        HAA_price[ticker] = balance.get('current_price', 0)
    else:
        eval_amount = 0
        HAA_qty[ticker] = 0
        HAA_price[ticker] = 0
    HAA_balance += eval_amount
    time_module.sleep(0.05)


# ========================================
# 3. 분할 매매 IndexError 방지 (184, 186라인)
# ========================================
# 기존:
# price = round(current_price * sell_split_USLA[1][i], 2)

# 수정:
for i in range(sell_split_USLA[0]):
    # ... 수량 계산 ...
    
    # 가격 조정 - IndexError 방지
    if ticker in USLA_ticker:
        if i < len(sell_split_USLA[1]):
            price_ratio = sell_split_USLA[1][i]
        else:
            price_ratio = 0.99  # 기본값
        price = round(current_price * price_ratio, 2)
    else:
        if i < len(sell_split_HAA[1]):
            price_ratio = sell_split_HAA[1][i]
        else:
            price_ratio = 0.99  # 기본값
        price = round(current_price * price_ratio, 2)


# ========================================
# 4. 메시지 중복 수정 (1384라인)
# ========================================
# 기존:
# order_messages.extend(order_messages)  # 잘못됨

# 수정:
Sell_order, sell_messages = Selling(USLA, HAA, sell_split_USLA, sell_split_HAA, order_time)
message.extend(sell_messages)  # 올바른 변수명


# ========================================
# 5. FULL_BUYUSD 계산 시 가격 0 처리 (1285-1296라인)
# ========================================
# 기존:
# invest = USLA[ticker]['buy_qty'] * USLA[ticker]['current_price']

# 수정:
FULL_BUYUSD = 0
price_error = False

for ticker in USLA_ticker:
    if USLA[ticker]['current_price'] <= 0:
        message.append(f"⚠️ {ticker} 가격 조회 실패 - 매수 스킵")
        USLA[ticker]['buy_qty'] = 0
        price_error = True
        continue
    invest = USLA[ticker]['buy_qty'] * USLA[ticker]['current_price']
    FULL_BUYUSD += invest

for ticker in HAA_ticker:
    if HAA[ticker]['current_price'] <= 0:
        message.append(f"⚠️ {ticker} 가격 조회 실패 - 매수 스킵")
        HAA[ticker]['buy_qty'] = 0
        price_error = True
        continue
    invest = HAA[ticker]['buy_qty'] * HAA[ticker]['current_price']
    FULL_BUYUSD += invest

if price_error:
    message.append("⚠️ 일부 종목 가격 조회 실패로 매수 수량 조정됨")


# ========================================
# 6. ADJUST_RATE 적용 후 검증 (1292-1299라인)
# ========================================
# 기존:
# if FULL_BUYUSD > USD:
#     ADJUST_RATE = USD / FULL_BUYUSD
#     for ticker in USLA_ticker:
#         USLA[ticker]['buy_qty'] = int(USLA[ticker]['buy_qty'] * ADJUST_RATE)

# 수정:
if FULL_BUYUSD > USD:
    ADJUST_RATE = USD / FULL_BUYUSD
    message.append(f"⚠️ 예수금 부족 - 매수 수량 {ADJUST_RATE:.1%}로 조정")
    
    # 조정 적용
    for ticker in USLA_ticker:
        USLA[ticker]['buy_qty'] = int(USLA[ticker]['buy_qty'] * ADJUST_RATE)
    for ticker in HAA_ticker:
        HAA[ticker]['buy_qty'] = int(HAA[ticker]['buy_qty'] * ADJUST_RATE)
    
    # 조정 후 재계산
    adjusted_total = 0
    for ticker in USLA_ticker:
        adjusted_total += USLA[ticker]['buy_qty'] * USLA[ticker]['current_price']
    for ticker in HAA_ticker:
        adjusted_total += HAA[ticker]['buy_qty'] * HAA[ticker]['current_price']
    
    message.append(f"조정 후 필요금액: ${adjusted_total:,.2f} / 예수금: ${USD:,.2f}")
    
    # 안전 마진 체크
    if adjusted_total > USD * 0.99:
        message.append("⚠️ 조정 후에도 예수금 부족 가능성 있음")
else:
    message.append(f"✓ 예수금 충분 (필요: ${FULL_BUYUSD:,.2f} / 보유: ${USD:,.2f})")


# ========================================
# 7. 매수/매도 순서 개선 (1회차만 매도 우선)
# ========================================
# 1회차 (1277-1302라인)
if order_time['round'] == 1:
    # 1회차: 매도 → 대기 → 매수
    Sell_order, sell_messages = Selling(USLA, HAA, sell_split_USLA, sell_split_HAA, order_time)
    message.extend(sell_messages)
    
    # 10초 대기 (매도 주문 전송 시간)
    time_module.sleep(10)
    
    # 예수금 재조회
    USD = KIS.get_US_dollar_balance().get('withdrawable', 0)
    message.append(f"매도 주문 후 예수금: ${USD:,.2f}")
    
    # 매수 수량 조정
    # ... FULL_BUYUSD 계산 및 ADJUST_RATE 적용 ...
    
    Buy_order, buy_messages = Buying(USLA, HAA, buy_split_USLA, buy_split_HAA, order_time)
    message.extend(buy_messages)

# 2-24회차 (1383-1409라인)
else:
    # 2회차부터: 매수 → 매도 (이미 매도 주문 진행 중)
    # 예수금 조정 로직
    # ... FULL_BUYUSD 계산 및 ADJUST_RATE 적용 ...
    
    Buy_order, buy_messages = Buying(USLA, HAA, buy_split_USLA, buy_split_HAA, order_time)
    message.extend(buy_messages)
    
    time_module.sleep(5)
    
    Sell_order, sell_messages = Selling(USLA, HAA, sell_split_USLA, sell_split_HAA, order_time)
    message.extend(sell_messages)


# ========================================
# 8. 추가 안전장치 - 목표 비중 합계 검증
# ========================================
# USLA, HAA 생성 직후 추가 (1회차 기준 1237라인 이후)

total_weight = 0
for ticker in USLA.keys():
    total_weight += USLA[ticker].get('target_weight', 0)
for ticker in HAA.keys():
    total_weight += HAA[ticker].get('target_weight', 0)

if total_weight > 1.01:
    error_msg = f"❌ 목표 비중 초과: {total_weight:.2%}"
    message.append(error_msg)
    KA.SendMessage("\n".join(message))
    sys.exit(1)
elif total_weight < 0.90:
    message.append(f"⚠️ 목표 비중 부족: {total_weight:.2%}")
else:
    message.append(f"✓ 목표 비중 합계: {total_weight:.2%}")


# ========================================
# 전체 수정 요약
# ========================================
"""
1. ZeroDivisionError 방지: current_price <= 0 체크
2. TIP 티커 정상 처리: skip 제거
3. IndexError 방지: 리스트 범위 체크 + 기본값
4. 메시지 변수 수정: order_messages → sell_messages
5. FULL_BUYUSD 가격 0 처리: 에러 종목 스킵 + 경고
6. ADJUST_RATE 검증: 조정 후 재계산 + 메시지
7. 매수/매도 순서: 1회차만 매도 우선
8. 목표 비중 검증: 합계 체크
"""