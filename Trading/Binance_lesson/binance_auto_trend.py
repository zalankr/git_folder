import ccxt
import time
import pandas as pd
import pprint
       
import Trading.TR_Binance.myBinance as myBinance
import ende_key  #암복호화키
import my_key    #업비트 시크릿 액세스키

import line_alert #라인 메세지를 보내기 위함!

import json

'''
15분 봉을 보기에 15분마다 돌도록 크론탭에 설정하시면 됩니다.

어떤 분봉 혹은 일봉을 볼지는 테스트 해보세요 ^^!

업비트 봇처럼 추세가 변경될때 포지션 정리하는 것으로 변경해보시는 것도 응용 방법입니다!

제가 알아내지 못한 버그나 오류가 있을 수도 있으니
이상하거나 문의가 있다면 클래스 영상에 댓글로 언제든지 알려주세요!



하다가 잘 안되시면 계속 내용이 추가되고 있는 아래 FAQ를 꼭꼭 체크하시고

주식/코인 자동매매 FAQ
https://blog.naver.com/zacra/223203988739

그래도 안 된다면 구글링 해보시고
그래도 모르겠다면 클래스 댓글, 블로그 댓글, 단톡방( https://blog.naver.com/zacra/223111402375 )에 질문주세요! ^^

클래스 제작 완료 후 많은 시간이 흘렀고 그 사이 전략에 많은 발전이 있었습니다.
제가 직접 투자하고자 백테스팅으로 검증하여 더 안심하고 있는 자동매매 전략들을 블로그에 공개하고 있으니
완강 후 꼭 블로그&유튜브 심화 과정에 참여해 보세요! 기다릴께요!!

아래 빠른 자동매매 가이드 시간날 때 완독하시면 방향이 잡히실 거예요!
https://blog.naver.com/zacra/223086628069

'''

# Binance 토큰 불러오기
with open("C:/Users/ilpus/Desktop/NKL_invest/bnnkr.txt") as f:
    access, secret = [line.strip() for line in f.readlines()]

# binance 객체 생성

# 선물거래용 코드
binanceX = myBinance.ccxt.binance(config={
    'apiKey': access, 
    'secret': secret,
    'enableRateLimit': True,
    'options': {
        'defaultType': 'future'
    }
})

"""
# 현물거래용 코드
binanceX = myBinance.ccxt.binance(config={
    'apiKey': access, 
    'secret': secret,
    'enableRateLimit': True,
    'options': {
        'defaultType': 'spot'  # 또는 생략 가능
    }
})
"""


#선물 마켓에서 거래중인 모든 코인을 가져옵니다.
Tickers = binanceX.fetch_tickers()


#총 원금대비 설정 비율 
#아래처럼 0.1 로 셋팅하면 10%가 해당 전략에 할당된다는 이야기!
Invest_Rate = 0.1


#테스트를 위해 비트코인만 일단 체크해봅니다. 
#LovelyCoinList = ['BTC/USDT']

#매매 대상 코인 개수 
CoinCnt = 5.0 #len(LovelyCoinList)


#나중에 5개의 코인만 해당 전략으로 매매하기 위해 이를 저장할 리스트를 선언합니다.
DolPaCoinList = list()

#파일 경로입니다.
dolpha_type_file_path = "/var/autobot/BinanceTrendDolPaCoin.json"
try:
    #이 부분이 파일을 읽어서 리스트에 넣어주는 로직입니다. 
    with open(dolpha_type_file_path, 'r') as json_file:
        DolPaCoinList = json.load(json_file)

except Exception as e:
    #처음에는 파일이 존재하지 않을테니깐 당연히 예외처리가 됩니다!
    print("Exception by First")








###################################################
#설정할 레버리지!
set_leverage = 10



#선물 테더(USDT) 마켓에서 거래중인 코인을 거래대금이 많은 순서로 가져옵니다. 여기선 Top 25
TopCoinList = myBinance.GetTopCoinList(binanceX,25)

#비트코인과 이더리움을 제외 하고 싶다면이렇게 하면 됩니다!
#try - except로 감싸주는게 좋습니다. 왜냐하면 비트와 이더가 탑 25위 안에 안드는 일은 없겠지만
#다른 코인을 제외했는데 그 코인이 거래대금이 줄어들어 TopCoinList에서 빠지면
#리스트에서 없는 요소를 제거하려고 했기때문에 예외가 발생하고 아래 로직이 실행되지 않게 됩니다.
#이렇게 각각이요!

#CCXT구버전
try:
    TopCoinList.remove("BTC/USDT")
except Exception as e:
    print("Exception", e)
#CCXT최신버전
try:
    TopCoinList.remove("BTC/USDT:USDT")
except Exception as e:
    print("Exception", e)
#CCXT구버전
try:
    TopCoinList.remove("ETH/USDT")
except Exception as e:
    print("Exception", e)
#CCXT최신버전
try:
    TopCoinList.remove("ETH/USDT:USDT")
except Exception as e:
    print("Exception", e)

#그냥 위처럼 제외할때는 BTC/USDT BTC/USDT:USDT 이렇게 쌍으로 처리하세요!



print(TopCoinList)



#잔고 데이타 가져오기 
balance = binanceX.fetch_balance(params={"type": "future"})
time.sleep(0.1)
#pprint.pprint(balance)




#모든 선물 거래가능한 코인을 가져온다.
for ticker in Tickers:

    try: 

        if "/USDT" in ticker:
            Target_Coin_Ticker = ticker

            #러블리 코인이 아니라면 스킵! 러블리 코인만 대상으로 한다!!
            #즉 현재는 비트코인만 체크하게 됩니다.
            #if myBinance.CheckCoinInList(LovelyCoinList,ticker) == False:
            #    continue

            #탑코인 리스트에 속하거나 추세선 돌파에 의해 매매된 코인이라면...
            if myBinance.CheckCoinInList(TopCoinList,ticker) == True or myBinance.CheckCoinInList(DolPaCoinList,ticker) == True:


            
                time.sleep(0.2)

                Target_Coin_Symbol = ticker.replace("/", "").replace(":USDT", "")


                time.sleep(0.05)
                #최소 주문 수량을 가져온다 
                minimun_amount = myBinance.GetMinimumAmount(binanceX,Target_Coin_Ticker)

                print("--- Target_Coin_Ticker:", Target_Coin_Ticker ," minimun_amount : ", minimun_amount)




                print(balance['USDT'])
                print("Total Money:",float(balance['USDT']['total']))
                print("Remain Money:",float(balance['USDT']['free']))


                leverage = 0  #레버리지

                #해당 코인 가격을 가져온다.
                coin_price = myBinance.GetCoinNowPrice(binanceX, Target_Coin_Ticker)


                #해당 코인에 할당된 금액에 따른 최대 매수수량을 구해본다!
                Max_Amt = float(binanceX.amount_to_precision(Target_Coin_Ticker, myBinance.GetAmount(float(balance['USDT']['total']),coin_price,Invest_Rate / CoinCnt)))  * set_leverage 
    
                print("Max_Amt:", Max_Amt)


                #코인별 할당된 수량의 절반으로 매수합니다. (혹시 롱과 숏 동시에 잡을 수도 있으므로...)
                Buy_Amt = Max_Amt / 2.0
                Buy_Amt = float(binanceX.amount_to_precision(Target_Coin_Ticker,Buy_Amt))


                print("Buy_Amt:", Buy_Amt)


                #최소 주문 수량보다 작다면 이렇게 셋팅!
                if Buy_Amt < minimun_amount:
                    Buy_Amt = minimun_amount

                
                print("Final Buy_Amt:", Buy_Amt)


                amt_s = 0 
                amt_b = 0
                entryPrice_s = 0 #평균 매입 단가. 따라서 물을 타면 변경 된다.
                entryPrice_b = 0 #평균 매입 단가. 따라서 물을 타면 변경 된다.


                isolated = True #격리모드인지 



                print("------")
                #숏잔고
                for posi in balance['info']['positions']:
                    if posi['symbol'] == Target_Coin_Symbol and posi['positionSide'] == 'SHORT':
                        print(posi)
                        amt_s = float(posi['positionAmt'])
                        entryPrice_s= float(posi['entryPrice'])
                        leverage = float(posi['leverage'])
                        isolated = posi['isolated']
                        break


                #롱잔고
                for posi in balance['info']['positions']:
                    if posi['symbol'] == Target_Coin_Symbol and posi['positionSide'] == 'LONG':
                        print(posi)
                        amt_b = float(posi['positionAmt'])
                        entryPrice_b = float(posi['entryPrice'])
                        leverage = float(posi['leverage'])
                        isolated = posi['isolated']
                        break





                #################################################################################################################
                #레버리지 셋팅
                if leverage != set_leverage:
                        
                    try:
                        print(binanceX.fapiPrivate_post_leverage({'symbol': Target_Coin_Symbol, 'leverage': set_leverage}))
                    except Exception as e:
                        try:
                            print(binanceX.fapiprivate_post_leverage({'symbol': Target_Coin_Symbol, 'leverage': set_leverage}))
                        except Exception as e:
                            print("Exception:", e)

                #################################################################################################################


                #################################################################################################################
                #격리 모드로 설정
                if isolated == False:
                    try:
                        print(binanceX.fapiPrivate_post_margintype({'symbol': Target_Coin_Symbol, 'marginType': 'ISOLATED'}))
                    except Exception as e:
                        try:
                            print(binanceX.fapiprivate_post_margintype({'symbol': Target_Coin_Symbol, 'marginType': 'ISOLATED'}))
                        except Exception as e:
                            print("Exception:", e)
                #################################################################################################################  







                #캔들 정보 가져온다 - 15분봉 
                df = myBinance.GetOhlcv(binanceX,Target_Coin_Ticker, '15m')





                #변동성의 절반! 이걸로 익절 손절 하자!
                change_value = (float(df['high'].iloc[-2]) - float(df['low'].iloc[-2])) * 0.5


                #단 변동성이 현재 코인가격의 0.3%보다 작다면 맞춰준다!
                if change_value < coin_price * 0.003:
                    change_value = coin_price * 0.003

                





                #첫번째 꺾인 지점 (전저점)
                up_first_point = 0
                up_first_value = 0

                #두번째 꺾인 지점 (전전저점)
                up_second_point = 0
                up_second_value = 0


        
                #전저, 전전저점 구해서 상승 추세선을 구할수 있으니 구해보자!
                for index in range(3,len(df)):

                    #꺾인 지점을 체크한다 
                    if df['close'].iloc[-(index-1)] > df['close'].iloc[-(index)] < df['close'].iloc[-(index+1)]:

                        # 이 안에 들어왔다는 이야기는 꺾인 지점을 발견한거다!!!
                        # 즉 꺾인 지점이닷!!!

                        if up_first_point == 0: #첫번째 꺾인 지점이 아직 셋팅 안되었다면 

                            if coin_price > df['close'].iloc[-(index)]: #그 지점이 현재가보다 작다면 

                                #당첨!! 첫번째 꺾인 지점을 저장해 놓는다!
                                up_first_point = index #캔들 번호 
                                up_first_value = df['close'].iloc[-(index)] #캔들의 (종가)값

                        else: # 첫번째 꺾인 지점이 셋팅되어 0이 아니다! 그럼 두번째 꺾인 지점을 셋팅할 차례!

                            if up_second_point == 0: # 두번째 꺾인 지점이 아직 셋팅 안되었다?

                                #첫번째 꺾인 지점보다 가격이 낮을때만 두번째 지점을 셋팅한다!
                                if up_first_value > df['close'].iloc[-(index)]:

                                    #위 조건을 만족했다면 두번째 지점 셋팅!!
                                    up_second_point = index
                                    up_second_value = df['close'].iloc[-(index)]

                                    #탈출!! 추세선을 그을 수 있는 저점 두 개를 찾았다!
                                    break

                print("----------------------------------------------------------------------")
                print("----------------------------------------------------------------------")
                print("----------------------------------------------------------------------")
                                        
                #실제 두 개의 좌표를 프린트 해봅니다.                         
                print("up_first_point X:", up_first_point , " Y:" ,up_first_value)
                print("up_second_point X:", up_second_point ," Y:" ,up_second_value)

                # 기울기를 구합니다!
                resultUp = (up_first_value - up_second_value) / (up_first_point - up_second_point)

                # 직선의 방정식을 통해 X(캔들 번호)에 해당하는 Y값(추세선의 값)을 구할 수 있습니다!
                print("---------UpLine " ,resultUp*(1.0 - up_second_point) + up_second_value)


                UpTrendLineBefore = resultUp*(3.0 - up_second_point) + up_second_value
                UpTrendLine = resultUp*(2.0 - up_second_point) + up_second_value

                

                #상승 추세선을 하락 돌파했는지 여부
                IsDolPaShort = False

                #숏이 없는데 추세선을 하향 돌파 했다! 숏을 잡을 수 있다!
                if abs(amt_s) == 0 and  UpTrendLineBefore < df['close'].iloc[-3] and UpTrendLine > df['close'].iloc[-2] and len(DolPaCoinList) < CoinCnt:
                
                    #영상엔 빠져있지만 두 개의 점을 모두 다 찾았을 때만 유효하다!
                    if up_first_point != 0 and up_second_point != 0:
                        IsDolPaShort = True






                #첫번째 꺾인 지점 (전고점)
                down_first_point = 0
                down_first_value = 0

                #첫번째 꺾인 지점 (전전고점)
                down_second_point = 0
                down_second_value = 0


                #전고, 전전고점 구해서 하락 추세선을 구할수 있으니 구해보자!
                for index in range(3,len(df)):

                    #꺾인 지점을 체크한다 
                    if df['close'].iloc[-(index-1)] < df['close'].iloc[-(index)] > df['close'].iloc[-(index+1)]:


                        # 이 안에 들어왔다는 이야기는 꺾인 지점을 발견한거다!!!
                        # 즉 꺾인 지점이닷!!!


                        if down_first_point == 0: #첫번째 꺾인 지점이 아직 셋팅 안되었다면 

                            if coin_price < df['close'].iloc[-(index)]: #그 지점이 현재가보다 높다면 

                                #당첨!! 첫번째 꺾인 지점을 저장해 놓는다!
                                down_first_point = index #캔들 번호 
                                down_first_value = df['close'].iloc[-(index)] #캔들의 (종가)값

                        else:  # 첫번째 꺾인 지점이 셋팅되어 0이 아니다! 그럼 두번째 꺾인 지점을 셋팅할 차례!
                            
                            if down_second_point == 0: # 두번째 꺾인 지점이 아직 셋팅 안되었다?

                                #첫번째 꺾인 지점보다 가격이 높을 때만 두번째 지점을 셋팅한다!
                                if down_first_value < df['close'].iloc[-(index)]:

                                    #위 조건을 만족했다면 두번째 지점 셋팅!!
                                    down_second_point = index
                                    down_second_value = df['close'].iloc[-(index)]

                                    #탈출!! 추세선을 그을 수 있는 저점 두 개를 찾았다!
                                    break

                #실제 두 개의 좌표를 프린트 해봅니다.      
                print("down_first_point X:", down_first_point , " Y:" ,down_first_value)
                print("down_second_point X:", down_second_point ," Y:" ,down_second_value)

                # 기울기를 구합니다!
                resultDown = (down_first_value - down_second_value) / (down_first_point - down_second_point)

                # 직선의 방정식을 통해 X(캔들 번호)에 해당하는 Y값(추세선의 값)을 구할 수 있습니다!
                print("-------- DownLine " ,resultDown*(1.0 - down_second_point) + down_second_value)

                DownTrendLineBefore = resultDown*(3.0 - down_second_point) + down_second_value
                DownTrendLine = resultDown*(2.0 - down_second_point) + down_second_value
                

                #하락 추세선을 상승 돌파했는지 여부
                IsDolPaLong = False

                #롱이 없는데 추세선을 상향 돌파 했다! 롱을 잡을 수 있다!
                if abs(amt_b) == 0 and DownTrendLineBefore > df['close'].iloc[-3] and DownTrendLine < df['close'].iloc[-2] and len(DolPaCoinList) < CoinCnt:
      
                    #영상엔 빠져있지만 두 개의 점을 모두 다 찾았을 때만 유효하다!
                    if down_first_point != 0 and down_second_point != 0:
                        IsDolPaLong = True





                #전략에 의해 매수 했는데..
                if myBinance.CheckCoinInList(DolPaCoinList,ticker) == True:


                    #그런데 포지션이 없다. 익절이나 손절한 상태!
                    if abs(amt_s) == 0 and abs(amt_b) == 0:

                        #남은 주문읠 모두 취소하고
                        binanceX.cancel_all_orders(Target_Coin_Ticker)
                        time.sleep(0.1)

                        #그때 파일에서 제거해줘서 포지션을 잡을 수 있는 상태로 만든다!
                        DolPaCoinList.remove(Target_Coin_Ticker)
                                
                        #파일에 리스트를 저장합니다
                        with open(dolpha_type_file_path, 'w') as outfile:
                            json.dump(DolPaCoinList, outfile)





                #롱포지션을 잡을 수 있다! 하락 추세선을 위로 돌파한 상황!
                if IsDolPaLong == True and IsDolPaShort == False:
                    #롱 포지션을 잡습니다.
                    params = {
                        'positionSide': 'LONG'
                    }
                    #data = binanceX.create_market_buy_order(Target_Coin_Ticker,Buy_Amt,params)
                    data = binanceX.create_order(Target_Coin_Ticker, 'market', 'buy', Buy_Amt, None, params)
                    


                    #익절할 가격을 구합니다.
                    target_price = data['price'] + (change_value * 1.2)
                    #그리고 지정가로 익절 주문을 걸어놓는다!            
                    #print(binanceX.create_limit_sell_order(Target_Coin_Ticker,data['amount'],target_price,params))
                    print(binanceX.create_order(Target_Coin_Ticker, 'limit', 'sell', data['amount'], target_price, params))



                    #스탑할 가격을 구합니다.
                    stop_price = data['price'] - (change_value * 0.8)
                    #실제로 스탑로스를 가격으로 겁니다!
                    myBinance.SetStopLossLongPrice(binanceX, Target_Coin_Ticker, stop_price, False)



                    ####################################################################
                    #실제로 리스트에 매수(포지션 잡았다고)했다고 해당 코인 이름(티커)를 저장해둔다!
                    DolPaCoinList.append(Target_Coin_Ticker)
                            
                    
                    with open(dolpha_type_file_path, 'w') as outfile:
                        json.dump(DolPaCoinList, outfile)
                    ####################################################################
                    


                    line_alert.SendMessage("Trend Start Long : " + Target_Coin_Ticker + " X: " + str(down_first_point) +  "," + str(down_second_point) )

                                        
                    #매수 했다면 한번 더 잔고 데이타 가져오기 
                    balance = binanceX.fetch_balance(params={"type": "future"})




                #숏포지션을 잡을 수 있다! 상승 추세선을 아래로 돌파한 상황!
                if IsDolPaShort == True and IsDolPaLong == False:


                    #숏 포지션을 잡습니다.
                    params = {
                        'positionSide': 'SHORT'
                    }
                    #data = binanceX.create_market_sell_order(Target_Coin_Ticker,Buy_Amt,params)
                    data = binanceX.create_order(Target_Coin_Ticker, 'market', 'sell', Buy_Amt, None, params)


                    #익절할 가격을 구합니다.
                    target_price = data['price'] - (change_value * 1.2)
                    #그리고 지정가로 익절 주문을 걸어놓는다!            
                    #print(binanceX.create_limit_buy_order(Target_Coin_Ticker,data['amount'],target_price,params))
                    print(binanceX.create_order(Target_Coin_Ticker, 'limit', 'buy', data['amount'], target_price, params))


                    #스탑할 가격을 구합니다.
                    stop_price = data['price'] + (change_value * 0.8)
                    #실제로 스탑로스를 가격으로 겁니다!
                    myBinance.SetStopLossShortPrice(binanceX, Target_Coin_Ticker, stop_price, False)



                    ####################################################################
                    #실제로 리스트에 매수(포지션 잡았다고)했다고 해당 코인 이름(티커)를 저장해둔다!
                    DolPaCoinList.append(Target_Coin_Ticker)
                            
                    
                    with open(dolpha_type_file_path, 'w') as outfile:
                        json.dump(DolPaCoinList, outfile)
                    ####################################################################

                    line_alert.SendMessage("Trend Start Short : " + Target_Coin_Ticker + " X: " + str(up_first_point) +  "," + str(up_second_point) )


                    #매수 했다면 한번 더 잔고 데이타 가져오기 
                    balance = binanceX.fetch_balance(params={"type": "future"})




   




    except Exception as e:
        print("Exception:", e)











