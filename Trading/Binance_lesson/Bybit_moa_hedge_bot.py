import ccxt
import time
import pandas as pd
import pprint

import myBybit
import ende_key  #암복호화키
import my_key    #업비트 시크릿 액세스키


import line_alert #라인 메세지를 보내기 위함!



#암복호화 클래스 객체를 미리 생성한 키를 받아 생성한다.
simpleEnDecrypt = myBybit.SimpleEnDecrypt(ende_key.ende_key)


#암호화된 액세스키와 시크릿키를 읽어 복호화 한다.
Bybit_AccessKey = simpleEnDecrypt.decrypt(my_key.bybit_access)
Bybit_ScretKey = simpleEnDecrypt.decrypt(my_key.bybit_secret)

# bybit 객체 생성
bybitX = ccxt.bybit(config={
    'apiKey': Bybit_AccessKey, 
    'secret': Bybit_ScretKey,
    'enableRateLimit': True,
    'options': {
        'defaultType': 'future'
    }
})




'''

장기로 롱포지션을 유지하면 특정 비중을 맞춰주는 봇입니다.

헷지모드로 구현한 내용도 사실 트레일링 스탑 함수 예시를 보여주기 위해
만든게 큽니다.

따라서 참고만 하시고 헷징전략(숏을 언제 잡고 언제 종료할 것인지) 등은 클래스 메이트 여러분만의
전략으로 바꿔서 사용해 보세요!!!


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




###################################################
#설정할 레버리지!
set_leverage = 5



#--장기 보유할 베스트 코인 ------------------------------------------------------------------------------------------------------#
Best_Coin_Portion = 0.1 #비중조절로 계속 가지고갈 베스트 코인 비중 총 10%



#장기로 모아갈 코인들 입니다!
BestCoinList = ['BTC/USDT:USDT','ETH/USDT:USDT']

#베스트 코인에 해당되는 비중에서 위 베스트 코인 개수를 나누면 각 코인별 할당 비중이 나온다!
Each_BestCoin_Portion = Best_Coin_Portion / float(len(BestCoinList))

print("Each_BestCoin_Portion : ", Each_BestCoin_Portion)
#----------------------------------------------------------------------------------------------------------------------#




#잔고 데이타 가져오기 
balances = bybitX.fetch_balance(params={"type": "future"})
pprint.pprint(balances)
time.sleep(0.1)

#잔고 데이타 가져오기 
balances2 = bybitX.fetch_positions(None, {'type':'Future'})
time.sleep(0.1)



#현재 평가금액을 구합니다.
TotalRealMoney = myBybit.GetTotalRealMoney(balances)

print("TotalRealMoney ", TotalRealMoney)


#타겟 수익률
Target_Revenue_Rate = 1.0


#----------------------------------------------------------------------------------------------------------------------#

#시간 정보를 가져옵니다. 아침 9시의 경우 서버에서는 hour변수가 0이 됩니다.
time_info = time.gmtime()
hour = time_info.tm_hour
min = time_info.tm_min
print(hour, min)



for ticker in BestCoinList:

    try: 

        time.sleep(0.2)

        Target_Coin_Ticker = ticker

        Target_Coin_Symbol = ticker.replace("/", "").replace(":USDT","")


        time.sleep(0.05)
        #최소 주문 수량을 가져온다 
        minimun_amount = myBybit.GetMinimumAmount(bybitX,Target_Coin_Symbol)

        print("--- Target_Coin_Ticker:", Target_Coin_Ticker ," minimun_amount : ", minimun_amount)




        amt_s = 0 
        amt_b = 0
        entryPrice_s = 0 #평균 매입 단가. 따라서 물을 타면 변경 된다.
        entryPrice_b = 0 #평균 매입 단가. 따라서 물을 타면 변경 된다.
        is_isolated = False


        leverage = 0
        #숏 잔고
        for posi in balances2:
            if posi['info']['symbol'] == Target_Coin_Symbol and posi['info']['side'] == "Sell":
                try:
                    amt_s = float(posi['info']['size'])
                    entryPrice_s = float(posi['info']['entry_price'])
                    leverage = float(posi['info']['leverage'])
                    is_isolated = posi['info']['is_isolated']
                except Exception as e:
                    amt_s = float(posi['info']['size'])
                    entryPrice_s = float(posi['info']['avgPrice'])
                    leverage = float(posi['info']['leverage'])

                    if posi['marginMode'] == 'isolated':
                        is_isolated = True
                    else:
                        is_isolated = False
                break

        #롱 잔고
        for posi in balances2:
            if posi['info']['symbol'] == Target_Coin_Symbol and posi['info']['side'] == "Buy":
                try:
                    amt_b = float(posi['info']['size'])
                    entryPrice_b = float(posi['info']['entry_price'])
                    leverage = float(posi['info']['leverage'])
                    is_isolated = posi['info']['is_isolated']
                except Exception as e:
                    amt_b = float(posi['info']['size'])
                    entryPrice_b = float(posi['info']['avgPrice'])
                    leverage = float(posi['info']['leverage'])
                    
                    if posi['marginMode'] == 'isolated':
                        is_isolated = True
                    else:
                        is_isolated = False
                break

            
        #################################################################################################################
        #레버리지와 교차모드 셋팅합니다! 
        print("###############", leverage)

        #######################################
        #교차모드로 셋팅합니다!
        if is_isolated == True or leverage != set_leverage:
            try:
                print(bybitX.set_margin_mode("isolated",Target_Coin_Symbol, {'leverage':set_leverage}))
            except Exception as e:
                print("---:", e)
            try:
                print(bybitX.set_margin_mode("cross",Target_Coin_Symbol, {'leverage':set_leverage}))
            except Exception as e:
                print("---:", e)


        #################################################################################################################

        '''



        마찬가지로 주요 타점에 롱포지션을 잡는 로직을 추가해줘도 됩니다!






        '''

        #해당 코인 가격을 가져온다.
        coin_price = myBybit.GetCoinNowPrice(bybitX, Target_Coin_Ticker)


        CoinPortion = Each_BestCoin_Portion



        #롱 매수된 상태!
        if abs(amt_b) > 0:

            #현재 코인의 총 매수평가금액 롱을 가져온다!
            NowCoinTotalMoney = myBybit.GetCoinRealMoney(balances2,Target_Coin_Ticker,"Buy")



            Rate = NowCoinTotalMoney / TotalRealMoney
            print("--------------> " , Target_Coin_Ticker , " rate : ", Rate)

            if Rate > 0 and Rate != CoinPortion:

                

                #갭을 구한다!!!
                GapRate = CoinPortion - Rate
                print("--------------> " , Target_Coin_Ticker , " Gaprate : ", GapRate)

                GapMoney = TotalRealMoney * abs(GapRate)
                GapAmt = float(bybitX.amount_to_precision(Target_Coin_Ticker,(GapMoney / coin_price) * set_leverage))

                print("--------------> " , Target_Coin_Ticker , " GapMoney : ", GapMoney)
                print("--------------> " , Target_Coin_Ticker , " GapAmt : ", GapAmt)

                
                #갭이 음수면 비트코인 비중보다 수익이 나서 더 많은 비중을 차지하고 있는 경우
                if GapRate < 0:
                    
                    print("Rate More")



                    ##################################################################################
                    ##################################################################################
                    ##################################################################################
                    # 이 아래 if문안의 부분은 필요 없다면 과감히 날리거나 주석처리 하시면 됩니다. 
                    ##################################################################################
                    ##################################################################################
                    ##################################################################################
                    if GapAmt >=  minimun_amount and abs(GapRate) >= (CoinPortion / 2.0): 
                        print("--------------> SELL " , Target_Coin_Ticker , "!!!!")

                        #수익율을 구한다.
                        revenue_rate_b = (coin_price - entryPrice_b) / entryPrice_b * 100.0

                        if revenue_rate_b >= Target_Revenue_Rate:

                            #########################################
                            # 영상엔 없지만 
                            # 팔려고 하는 물량보다  3배 이상 많을 때만 포지션 정리를 하자   
                            # 현재 롱 포지션 자체가 너무 적은 물량인데 수익 났다고 파는 경우 
                            # (비트의 경우 최소주문수량 0.001인 경우) 롱 포지션이 아예 다 종료될 여지가 있다.
                            ######################################################
                            if abs(amt_b) >= GapAmt * 3.0:

                                #print(bybitX.create_market_sell_order(Target_Coin_Ticker, GapAmt, {'reduce_only': True,'close_on_trigger':True}))
                                print(bybitX.create_order(Target_Coin_Ticker, 'market', 'sell', GapAmt, None,{'position_idx':1,'reduce_only': True,'close_on_trigger':True}))

                            
                                line_alert.SendMessage("ReBalance !!! : " + Target_Coin_Ticker + " by SELL:" )
                                print("--------------> SELL " , Target_Coin_Ticker , "!!!!")

                #갭이 양수면 비트코인 비중이 적으니 추매할 필요가 있는 경우
                else:
                    print("Rate Less")
                   
                    if GapAmt >=  minimun_amount  and abs(GapRate) >= (CoinPortion / 10.0):

                        #print(bybitX.create_market_buy_order(Target_Coin_Ticker, GapAmt))
                        print(bybitX.create_order(Target_Coin_Ticker, 'market', 'buy', GapAmt ,None,{'position_idx':1}))


                        
                        line_alert.SendMessage("ReBalance !!! : " + Target_Coin_Ticker + " by BUY:" )
                        print("--------------> BUY " , Target_Coin_Ticker , "!!!!")

        else:
            if CoinPortion > 0:

                BestMoney = TotalRealMoney * CoinPortion
                BestAmt = float(bybitX.amount_to_precision(Target_Coin_Ticker,(BestMoney / coin_price) * set_leverage))

                if BestAmt < minimun_amount:
                    BestAmt = minimun_amount

                
                #print(bybitX.create_market_buy_order(Target_Coin_Ticker, BestAmt))
                print(bybitX.create_order(Target_Coin_Ticker, 'market', 'buy', BestAmt, None, {'position_idx':1}))

    
                print("--------------> BUY " , Target_Coin_Ticker , "!!!!")



        '''
        다양한 숏 헷징 전략을 사용해 봅니다.
        여기서는 단순히 이전 일봉이 음봉이었다면 숏을 롱의 절반의 수량만큼 잡고 이전 음봉의 절반수준의 비율로 트레일링 스탑을 걸어놓습니다!
        '''

        #숏이 없을때..
        if abs(amt_s) == 0 and hour == 0:

            time.sleep(0.2)
            #캔들 정보 가져온다 여기서는 15분봉을 보지만 자유롭게 조절 하세요!!!
            df_day= myBybit.GetOhlcv(bybitX,Target_Coin_Ticker, '1d')

            #이전 캔들이 음봉이다!
            if df_day['open'].iloc[-2] > df_day['close'].iloc[-2]:


                #캔들 크기를 구합니다. 
                candle_rate = ((df_day['open'].iloc[-2] / df_day['close'].iloc[-2]) - 1.0) * 100

                if df_day['close'].iloc[-2] > df_day['open'].iloc[-2]:
                    candle_rate = ((df_day['close'].iloc[-2] / df_day['open'].iloc[-2]) - 1.0) * 100


                print("candle_rate", candle_rate)


                #지난 캔들 하락분의 절반으로 트레일링 스탑을 겁니다
                candle_rate *= 0.5

                
                #너무 작음을 방지하기 위해 최소 0.3정도로 보정해준다!
                if candle_rate < 0.3:
                    candle_rate = 0.3


                print("Final candle_rate ", candle_rate)


                traillingStop = round(candle_rate,1)

                if traillingStop < 0.2:
                    traillingStop = 0.2

                if traillingStop > 5.0:
                    traillingStop = 5.0


                hedge_amt =  abs(amt_b) * 0.5

                if hedge_amt < minimun_amount:
                    hedge_amt =  minimun_amount
                    
                hedge_amt = bybitX.amount_to_precision(Target_Coin_Ticker,hedge_amt)


                #숏 포지션을 잡습니다.
                #data = bybitX.create_market_sell_order(Target_Coin_Ticker, hedge_amt)
                print(bybitX.create_order(Target_Coin_Ticker, 'market', 'sell', hedge_amt,None ,{'position_idx':2}))


                #트레일링 스탑함수(버전업 되면서 개선 필요..)
                #myBybit.add_trailing_to_sell_order(bybitX,Target_Coin_Ticker,traillingStop)
                
                
                
                #!!!!!!!!!!숏 익절 주문으로 변경!!!!!!!
                #익절할 가격을 구합니다.
                target_price = coin_price - (1.0 - candle_rate/100.0)
                #그리고 지정가로 익절 주문을 걸어놓는다!            
                #print(bybitX.create_limit_buy_order(Target_Coin_Ticker, Buy_Amt, target_price, {'reduce_only': True,'close_on_trigger':True}))
                print(bybitX.create_order(Target_Coin_Ticker, 'limit', 'buy', hedge_amt, target_price,{'position_idx':2,'reduce_only': True,'close_on_trigger':True}))


   

                line_alert.SendMessage("Hedge Start !!! : " + Target_Coin_Ticker )

    except Exception as e:
        print("error:", e)








