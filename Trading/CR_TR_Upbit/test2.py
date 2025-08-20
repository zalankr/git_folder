from datetime import datetime
import time as time_module  # time 모듈을 별칭으로 import
import pyupbit
import UP_signal_weight as SW

# 현재 시간 가져오기
# now = datetime.now()
# print(f"현재 시간: {now.strftime('%Y-%m-%d %H:%M:%S')}")

# current_time = now.time()
# print(f"현재 시간 (time 객체): {current_time}")

# # 시간 비교 시 초 단위까지 정확히 매칭하기 어려우므로 시간 범위로 체크
# current_hour = current_time.hour
# current_minute = current_time.minute

# if current_hour == 23 and current_minute == 58:  # 23:58
#     TR_time = ["0858", 0]
# elif current_hour == 0 and current_minute == 5:  # 00:05
#     TR_time = ["0905", 1]
# elif current_hour == 0 and current_minute == 12:  # 00:12
#     TR_time = ["0912", 2]
# elif current_hour == 0 and current_minute == 19:  # 00:19
#     TR_time = ["0919", 3]
# elif current_hour == 17 and 0 <= current_minute <= 59: 
#     TR_time = ["anytime", 4]
# else:
#     TR_time = [None, 5]

# print("sleep(1)")
# time_module.sleep(1)
# print(TR_time)

ETH_Invest = ["Buy", 10000000]
TR_time = ["0858", 5]

#넘겨받은 가격과 수량으로 지정가 매수한다.
# def buy_limit_order(self, ticker, price, volume, contain_req=False)

def ETH_Buy(ETH_Invest, TR_time):
    volume_per_times = (ETH_Invest[1] / TR_time[1]) # 분할 매매 횟수당 KRW Quantity
    print("분할 매매 횟수:", TR_time[1], "분할 매매 금액:", volume_per_times) # 완성 후 삭제
    current_price = pyupbit.get_current_price("KRW-ETH") # 이더리움 가격
    # TR 분할 매매 가격 계산 & tick size에 맞춰 가격 조정
    prices = []
    for i in range(TR_time[1]):
        price = (current_price * (1 - (i * 0.002))) # 가격을 0.2%씩 낮추는 분할 매매 가격 계산
        prices.append(SW.get_tick_size(price = price,  method="floor"))
        ## if문으로 TR_time[1]이 3미만이면 주문을 +2%(유사 시장가)주문으로 대체
        if TR_time[1] < 3:
            prices[0] = [SW.get_tick_size(price = current_price*1.02,  method="floor")]
    for price in prices:
        time_module.sleep(0.05)
        print(f"upbit.buy_limit_order(upbit, ticker='KRW-ETH', {price}, {volume_per_times})")

    result = ({"TR_time": TR_time[0]})

    return result

trade = ETH_Buy(ETH_Invest, TR_time)
print(trade)