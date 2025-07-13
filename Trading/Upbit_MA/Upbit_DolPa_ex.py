#-*-coding:utf-8 -*-
import myUpbit   #우리가 만든 함수들이 들어있는 모듈
import time
import pyupbit
import kakao_alert   
import json

# 카카오톡 메세지 보내는 함수
def SendMessage(msg):
    kakao_alert.SendMessage(msg)

'''
변동성 돌파 전략 단타 변형!

변동성 = (전날 고가 - 전날 저가) * 0.5
기준가격 = 오늘 시가 +  (전날 고가 - 전날 저가) * 0.5

이 기준가격을 돌파하는 순간 매수!
+2% 위에 익절
-1% 아래로 가면 손절!

이렇게 매매한 코인을 그날은 매수하지 않는다.

파일에 매수한 코인을 저장해 놓고
이를 체크하기에

매일 9시에 파일의 리스트에 쓰여있는 코인을 지워줄 필요가 있다!
크론탭에 1분마다 혹은 5분마다 등록하셔도 무관합니다.
'''
upbit_access = "CvRZ8L3uWWx7SxeixwwX5mQVFXpJUaN7lxxT9gTe"
upbit_secret = "3iOZ7kGlSUP2v1yIUc7Y6zfOn50mXp2dMqHUqJR1"

#업비트 객체를 만든다
upbit = pyupbit.Upbit(upbit_access, upbit_secret)


#내가 매수할 총 코인 개수
MaxCoinCnt = 5.0

#내가 가진 잔고 데이터를 다 가져온다.
balances = upbit.get_balances()

#TotalMoney = myUpbit.GetTotalMoney(balances) #총 원금

#내 남은 원화(현금)을 구한다.
TotalWon = float(upbit.get_balance("KRW"))


#코인당 매수할 매수금액
CoinMoney = TotalWon / MaxCoinCnt

#5천원 이하면 매수가 아예 안되나 5천원 미만일 경우 강제로 5000원으로 만들어 준다!
if CoinMoney < 5000:
    CoinMoney = 5000

print("-----------------------------------------------")
print ("TotalWon:", TotalWon)
print ("CoinMoney:", CoinMoney)

#빈 리스트를 선언합니다.
DolPaCoinList = list()

#파일 경로입니다.
dolpha_type_file_path = "/var/autobot/UpbitDolPaCoin.json"
try:
    #이 부분이 파일을 읽어서 리스트에 넣어주는 로직입니다. 
    with open(dolpha_type_file_path, 'r') as json_file:
        DolPaCoinList = json.load(json_file)

except Exception as e:
    #처음에는 파일이 존재하지 않을테니깐 당연히 예외처리가 됩니다!
    print("Exception by First")



#시간 정보를 가져옵니다. 아침 9시의 경우 서버에서는 hour변수가 0이 됩니다.
time_info = time.gmtime()
hour = time_info.tm_hour
min = time_info.tm_min
print(hour, min)





#거래대금이 많은 탑코인 30개의 리스트
#TopCoinList = myUpbit.GetTopCoinList("day",30)

Tickers = pyupbit.get_tickers("KRW")

for ticker in Tickers:
    try: 
        print("Coin Ticker: ",ticker)

        #변동성 돌파로 매수된 코인이다!!! (실제로 매도가 되서 잔고가 없어도 파일에 쓰여있다면 참이니깐 이 안의 로직을 타게 됨)
        if myUpbit.CheckCoinInList(DolPaCoinList,ticker) == True:


            #아침 9시 0분에 체크해서 보유 중이라면 (아직 익절이나 손절이 안된 경우) 매도하고 리스트에서 빼준다!
            if hour == 0 and min == 0:

                #매수한 코인이라면.
                if myUpbit.IsHasCoin(balances, ticker) == True:
                    #시장가로 모두 매도!
                    balances = myUpbit.SellCoinMarket(upbit,ticker,upbit.get_balance(ticker))

                #리스트에서 코인을 빼 버린다.
                DolPaCoinList.remove(ticker)

                #파일에 리스트를 저장합니다
                with open(dolpha_type_file_path, 'w') as outfile:
                    json.dump(DolPaCoinList, outfile)
            


            #영상에 빠져 있지만 이렇게 매수된 상태의 코인인지 체크하고 난뒤 진행합니다~!
            if myUpbit.IsHasCoin(balances, ticker) == True:

                #수익율을 구한다.
                revenue_rate = myUpbit.GetRevenueRate(balances,ticker)

                #수익율이 -1%에 도달하면 모두 손절한다!!!
                if revenue_rate < -1.0:
                    
                    #기존에 걸린 주문 취소
                    myUpbit.CancelCoinOrder(upbit,ticker)
                    
                    #시장가로 모두 매도!
                    balances = myUpbit.SellCoinMarket(upbit,ticker,upbit.get_balance(ticker))


                    #이렇게 손절했다고 메세지를 보낼수도 있다
                    line_alert.SendMessage("Cut DolPa Coin : " + ticker)

                ''' 
                #익절 순간 메세지를 보내려면 아래 지정가 익절 주문을 주석처리 하고 이 부분을 해제!
                if revenue_rate >= 2.0:
                
                    #기존에 걸린 주문 취소
                    myUpbit.CancelCoinOrder(upbit,ticker)
                    
                    
                    #시장가로 모두 매도!
                    balances = myUpbit.SellCoinMarket(upbit,ticker,upbit.get_balance(ticker))


                    #이렇게 익절했다고 메세지를 보낼수도 있다
                    line_alert.SendMessage("Revenue DolPa Coin : " + ticker)
                '''


        #아니다!
        else:
            
            time.sleep(0.05)
            df = pyupbit.get_ohlcv(ticker,interval="day") #일봉 데이타를 가져온다.
            
            #어제의 고가와 저가의 변동폭에 0.5를 곱해서
            #오늘의 시가와 더해주면 목표 가격이 나온다!
            target_price = float(df['open'].iloc[-1]) + (float(df['high'].iloc[-2]) - float(df['low'].iloc[-2])) * 0.5
            
            #현재가
            now_price = float(df['close'].iloc[-1])

            print(now_price , " > ", target_price)

            #이를 돌파했다면 변동성 돌파 성공!! 코인을 매수하고 지정가 익절을 걸고 파일에 해당 코인을 저장한다!
            if now_price > target_price and len(DolPaCoinList) < MaxCoinCnt: #and myUpbit.GetHasCoinCnt(balances) < MaxCoinCnt:


                #보유하고 있지 않은 코인 (매수되지 않은 코인)일 경우만 매수한다!
                if myUpbit.IsHasCoin(balances, ticker) == False:

                    print("!!!!!!!!!!!!!!!DolPa GoGoGo!!!!!!!!!!!!!!!!!!!!!!!!")
                    #시장가 매수를 한다.
                    balances = myUpbit.BuyCoinMarket(upbit,ticker,CoinMoney)
            
            
                    ########################################################################
                    ####익절 순간 메세지를 받고 싶다면 이 로직을 주석처리 하고 위에서 시장가로 익절한다.####

                    #평균매입단가와 매수개수를 구해서 2% 상승한 가격으로 지정가 매도주문을 걸어놓는다.
                    avgPrice = myUpbit.GetAvgBuyPrice(balances,ticker)
                    coin_volume = upbit.get_balance(ticker)

                    targetPrice = avgPrice * 1.02

                    #지정가 매도 익절 라인을 그어 놓는다!
                    myUpbit.SellCoinLimit(upbit,ticker,targetPrice,coin_volume)

                    ########################################################################



                    #매수된 코인을 DolPaCoinList 리스트에 넣고 이를 파일로 저장해둔다!
                    DolPaCoinList.append(ticker)
                    
                    #파일에 리스트를 저장합니다
                    with open(dolpha_type_file_path, 'w') as outfile:
                        json.dump(DolPaCoinList, outfile)



                    #이렇게 매수했다고 메세지를 보낼수도 있다
                    line_alert.SendMessage("BUY Done DolPa Coin : " + ticker)



    except Exception as e:
        print("---:", e)



'''
강의에서 설명할때
이전에 매수된 코인이라도 즉 내가 비트코인 장기 투자 하는데
따로 단타를 치고 싶다. 그래서 파일저장을 이용하면 된다고 말씀 드렸는데

생각해보면 더 고려할 점이 있습니다.
왜냐면 우리가 매도할때 매수한만큼만 팔아야 되잖아요?
비트코인이 내가 10개있는데 변동성 돌파로 1개를 샀다
그러면 1개를 팔아야겠죠.

그럼 또 이 샀다는 수량 정보를 또 따로 저장해야 되는 필요성이 있습니다.
즉 매수 수량을 계산해서 파일 저장해야 하는데요 (이는 8-4에서 나올 딕셔너리 파일 저장을 응용)
그래야 나중에 그 수량 만큼 팔테니까요. (부분 매도)

즉 비트코인 5천원어치를 샀는데 얼마큼 수량이 사졌는지 넘겨 받을 수 있는 데이터가 없는 걸로 현재 체크가 되기에

결국 매수 시점에 수량 정보를 계산해야 되는데. 

이 수량을 구하기 위해 매수가인 

매수금액(5천원) / 현재가격 = 매수 수량

이렇게 구할 수 있습니다.

실제 시장가로 체결될때 모든 수량이 지금 구한 현재 가격에 체결되지 않을 수 있기에
여기서 구한 수량은 수수료도 감안한다면 완전 정확한 수량이 아니라 얼추 맞는 수량이 됩니다.

이미 보유한 비트코인의 경우 부분 매도니깐 수량차이가 조금 있어도 크게 상관 없지만
그렇지 않은 코인의 경우 어설프게 잔량이 남아서 완전히 매도가 안될 여지가 있으므로 

1. 완전 매도해야하는 즉 기존에 잔고 없이 새로 전략에 의해 매수하는 코인들 리스트
2. 이미 기존 잔고가 있어서 부분 매도해야 하는 코인들 리스트

이렇게 2개의 리스트를 파일에 저장할 필요가 있습니다.
1번은 이미 만들었고 2번의 리스트 파일저장을 만들 필요가 있겠죠. ^^

이는 필요하신 분의 과제로 남겨두고요.

그래서 일단 여기서는 심플하게 봇의 전략으로 매수할 코인은 잔고가 없다는 조건을 걸겠습니다.
아래 if문으로 보유하고 있지 않은 코인만 전략 매수 대상이 됩니다!!
'''




