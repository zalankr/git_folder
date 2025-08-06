#-*-coding:utf-8 -*-
import myUpbit   #우리가 만든 함수들이 들어있는 모듈
import time
import pyupbit

import ende_key  #암복호화키
import my_key    #업비트 시크릿 액세스키

import line_alert #라인 메세지를 보내기 위함!

'''

코인을 장기투자 하되
내 원금의 일정 비중으로 유지해주는 봇입니다.

초기 설정은 매우(?) 보수적으로 잡았기에 
강의 참고하시어 변형해서 사용해보세요~^^!

이 이후 업비트 베스트 봇 과정을 진행하시면 더 이해가 쉬우실 수 있습니다

https://blog.naver.com/zacra/222670663136


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

#어자피 이 봇은 수시로 돌 필요가 없기에 
#우리가 다른 단타 봇을 돌릴 수 있으므로 그 봇들과 겹치게 실행되지 않게 30초를 쉬어줍니다
time.sleep(30.0)


#암복호화 클래스 객체를 미리 생성한 키를 받아 생성한다.
simpleEnDecrypt = myUpbit.SimpleEnDecrypt(ende_key.ende_key)

#암호화된 액세스키와 시크릿키를 읽어 복호화 한다.
Upbit_AccessKey = simpleEnDecrypt.decrypt(my_key.upbit_access)
Upbit_ScretKey = simpleEnDecrypt.decrypt(my_key.upbit_secret)

#업비트 객체를 만든다
upbit = pyupbit.Upbit(Upbit_AccessKey, Upbit_ScretKey)




#--장기 보유할 베스트 코인 ------------------------------------------------------------------------------------------------------#
Best_Coin_Portion = 0.1 #비중조절로 계속 가지고갈 베스트 코인 비중 총 10%
# 당연이 늘리셔도 됩니다. 너무 보수적인 수치이긴 하죠. 
# 각자 판단에 따라 내 원금의 50%는 몇 년이고 장기로 모아갈 생각이시라면 0.5로 공격적으로 모아가셔도 됩니다.


#장기로 모아갈 코인들 입니다!
BestCoinList = ['KRW-BTC','KRW-ETH','KRW-ADA','KRW-SOL','KRW-DOT']

#베스트 코인에 해당되는 비중에서 위 베스트 코인 개수를 나누면 각 코인별 할당 비중이 나온다!
Each_BestCoin_Portion = Best_Coin_Portion / float(len(BestCoinList))

print("Each_BestCoin_Portion : ", Each_BestCoin_Portion)
#----------------------------------------------------------------------------------------------------------------------#




#원화 마켓에 상장된 모든 코인들을 가져온다.
Tickers = pyupbit.get_tickers("KRW")



MinimunCash = 10000.0 #최소 매수매도 금액설정! 


#내가 가진 잔고 데이터를 다 가져온다.
balances = upbit.get_balances()

TotalMoney = myUpbit.GetTotalMoney(balances) #총 원금
TotalRealMoney = myUpbit.GetTotalRealMoney(balances) #총 평가금액
#내 총 수익율
TotalRevenue = (TotalRealMoney - TotalMoney) * 100.0/ TotalMoney

print("-----------------------------------------------")
print ("Total Money:", myUpbit.GetTotalMoney(balances))
print ("Total Real Money:", myUpbit.GetTotalRealMoney(balances))
print ("Total Revenue", TotalRevenue)
print("-----------------------------------------------")


#타겟 수익률
Target_Revenue_Rate = 1.0


#----------------------------------------------------------------------------------------------------------------------#
#베스트 코인 리스트를 순회한다
for ticker in BestCoinList:
    try: 
        #매수 된 상태
        if myUpbit.IsHasCoin(balances,ticker) == True:
            print("")


            '''

            이 부분에 장기로 모아가는 코인들을 매수하고자 하는 타점이 있다면 넣는다.

            ex) 수익률이 -50% 즉 반토막이 나면 추가매수를 한다.
                일봉 기준 RSI 지표가 30에서 빠져나올때마다 추가매수를 한다. 등등..

            '''


            NowCoinTotalMoney = myUpbit.GetCoinNowRealMoney(balances,ticker) #코인의 평가금액 구하는 함수는 제가 만들어 놓았습니다!

            Rate = NowCoinTotalMoney / TotalRealMoney
            print("---BEST-------> ",ticker, " rate : ",  Rate)

            #베스트 코인 목표 비중과 현재 비중이 다르다.
            if Rate != Each_BestCoin_Portion:

                #갭을 구한다!!!
                GapRate = Each_BestCoin_Portion - Rate
                print("---BEST-------> ",ticker," Gaprate : ", GapRate)

                GapMoney = TotalRealMoney * abs(GapRate)

                #갭이 음수면 해당 코인 비중보다 수익이 나서 더 많은 비중을 차지하고 있는 경우 (혹은 폭락했는데 다른 코인들은 더 폭락한 경우.)
                if GapRate < 0:

                    print("More Rate")


                    ##################################################################################
                    ##################################################################################
                    ##################################################################################
                    # 이 아래 if문안의 부분은 필요 없다면 과감히 날리거나 주석처리 하시면 됩니다. 
                    ##################################################################################
                    ##################################################################################
                    ##################################################################################
                    
                    #초과한 금액이 설정한 최소 주문금액보다 크고 갭이 어느정도 벌어진 경우!
                    if GapMoney >=  MinimunCash and abs(GapRate) >= (Each_BestCoin_Portion / 2.0):

                        #수익율을 구한다.
                        revenue_rate = myUpbit.GetRevenueRate(balances,ticker)

                        #타겟 수익율보다 높을때만 매도해서 비중을 맞춘다! (손해볼때는 비중조절을 하지 않는다.)
                        if revenue_rate > Target_Revenue_Rate:

                            #그 갭만큼 수량을 구해서 
                            GapAmt = GapMoney / pyupbit.get_current_price(ticker)

                            #시장가 매도를 한다.
                            balances = myUpbit.SellCoinMarket(upbit,ticker,GapAmt)
                            print("----BEST------> SELL ",ticker,"!!!!")
                                        
                            line_alert.SendMessage("ReBalance !!! : " + ticker + " by SELL:"+ str(TotalRealMoney) )
                    
                    


                #갭이 양수면 해당 코인 비중이 적으니 추매할 필요가 있는 경우
                else:

                    print("Less Rate")

                    #모자란 금액이 설정한 최소 주문금액보다 크고 그리고 어느정도 갭이 벌어진 경우
                    if GapMoney >=  MinimunCash and abs(GapRate) >= (Each_BestCoin_Portion / 10.0):

                        balances = myUpbit.BuyCoinMarket(upbit,ticker,GapMoney)
                        print("-----BEST------> BUY ",ticker,"!!!!")
                        
                        line_alert.SendMessage("ReBalance !!! : " + ticker + " by BUY:"+ str(TotalRealMoney))


        #매수되지 않은 상태 (최초 매수)
        else:

            if Each_BestCoin_Portion > 0:
                FirstMoney = TotalRealMoney * Each_BestCoin_Portion

                if FirstMoney < MinimunCash:
                    FirstMoney = MinimunCash

                balances = myUpbit.BuyCoinMarket(upbit,ticker,FirstMoney)
                print("--------------> BUY ", ticker, "!!!!")

    except Exception as e:
        print("Exception:", e)
#----------------------------------------------------------------------------------------------------------------------#








