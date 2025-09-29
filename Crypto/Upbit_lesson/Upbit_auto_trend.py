#-*-coding:utf-8 -*-
import myUpbit   #우리가 만든 함수들이 들어있는 모듈
import time
import pyupbit

import ende_key  #암복호화키
import my_key    #업비트 시크릿 액세스키

import line_alert   

import json

'''
15분 봉을 보기에 15분마다 돌도록 크론탭에 설정하시면 됩니다.

어떤 분봉 혹은 일봉을 볼지는 테스트 해보세요 ^^!

바이낸스 봇처럼 단타로 변경해보시는 것도 응용 방법입니다!


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

####################################
#필요하지 않다면 주석처리하세요!!!
time.sleep(20.0)
####################################

# Upbit 토큰 불러오기
with open("C:/Users/ilpus/Desktop/NKL_invest/upnkr.txt") as f:
    access_key, secret_key = [line.strip() for line in f.readlines()]
#업비트 접속
upbit = pyupbit.Upbit(access_key, secret_key)


#내가 매수할 총 코인 개수
MaxCoinCnt = 5.0

#내가 가진 잔고 데이터를 다 가져온다.
balances = upbit.get_balances()

#TotalMoney = myUpbit.GetTotalMoney(balances) #총 원금

#내 남은 원화(현금))을 구한다.
TotalWon = float(upbit.get_balance("KRW"))

######################################################
#이런식으로 해당 전략에 할당할 금액을 조절할 수도 있습니다.
#이 경우 내가 가진 원화의 10%를 맥스로 해서 매매합니다!
TotalWon = TotalWon * 0.1
######################################################



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
dolpha_type_file_path = "/var/autobot/UpbitTrendDolPaCoin.json"
try:
    #이 부분이 파일을 읽어서 리스트에 넣어주는 로직입니다. 
    with open(dolpha_type_file_path, 'r') as json_file:
        DolPaCoinList = json.load(json_file)

except Exception as e:
    #처음에는 파일이 존재하지 않을테니깐 당연히 예외처리가 됩니다!
    print("Exception by First")






#########################################################
#거래대금이 많은 탑코인 30개의 리스트
TopCoinList = myUpbit.GetTopCoinList("day",30)

'''
현재 위에처럼 가져오면 느리니
아래 과정을 통해 개선해보세요!

업비트 거래대금 탑 코인 리스트를 파일로 빠르게 읽는 방법 :
https://blog.naver.com/zacra/222670663136
#(업비트 베스트 봇 과정인데 이 1탄 만 보시고 적용하셔도 됩니다)
'''

Tickers = pyupbit.get_tickers("KRW")
#########################################################


#구매 제외 코인 리스트 - 필요없다면 비워두세요
#OutCoinList = []
OutCoinList = ['KRW-BTC','KRW-ETH','KRW-ADA','KRW-DOT','KRW-AVAX','KRW-SOL','KRW-POL','KRW-ALGO','KRW-MANA','KRW-LINK','KRW-BAT','KRW-ATOM']



for ticker in Tickers:
    try: 
        print("Coin Ticker: ",ticker)

        #구매 제외 코인 들은 어떠한 매매도 하지 않는다!!
        if myUpbit.CheckCoinInList(OutCoinList,ticker) == True:
            continue


        #탑코인 리스트에 속하거나 추세선 돌파에 의해 매매된 코인이라면...
        if myUpbit.CheckCoinInList(TopCoinList,ticker) == True or myUpbit.CheckCoinInList(DolPaCoinList,ticker) == True:

            time.sleep(0.2)
            df = pyupbit.get_ohlcv(ticker,interval="minute15") #여기선 15분봉 데이타를 가져온다.

            coin_price = df['close'].iloc[-1] #현재가!



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

            #추세선을 하향 돌파 했다! 
            if  UpTrendLineBefore < df['close'].iloc[-3] and UpTrendLine > df['close'].iloc[-2]:
            
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

            #추세선을 상향 돌파 했다! 매수할 수 있다!
            if DownTrendLineBefore > df['close'].iloc[-3] and DownTrendLine < df['close'].iloc[-2]:
    
                #영상엔 빠져있지만 두 개의 점을 모두 다 찾았을 때만 유효하다!
                if down_first_point != 0 and down_second_point != 0:
                    IsDolPaLong = True

 


            #전략에 의해 매수 했고
            if myUpbit.CheckCoinInList(DolPaCoinList,ticker) == True:


                #따라서 잔고도 있다.
                if myUpbit.IsHasCoin(balances, ticker) == True:

                    #하향 돌파했다?
                    if IsDolPaShort == True:


                        #수익율을 구한다.
                        revenue_rate = myUpbit.GetRevenueRate(balances,ticker)

                        #수익율이 2%이상일 때만!!
                        if revenue_rate >= 2.0:
                            #시장가로 모두 매도!
                            balances = myUpbit.SellCoinMarket(upbit,ticker,upbit.get_balance(ticker))


                            #이렇게 익절했다고 메세지를 보낼수도 있다
                            line_alert.SendMessage("Revenue Upbit Trend DolPa Coin : " + ticker + " X: " + str(up_first_point) +  "," + str(up_second_point) )

                            #그때 파일에서 제거해줘서 리스트 개수도 줄이고 다음에 다시 매수할 수 있는 상태로 만든다!
                            DolPaCoinList.remove(ticker)
                                    
                            #파일에 리스트를 저장합니다
                            with open(dolpha_type_file_path, 'w') as outfile:
                                json.dump(DolPaCoinList, outfile)

            else:
                #아직 전략에 의해 매수되지 않은 코인!

                    
                #상승 돌파를 했다!!!
                if IsDolPaLong == True:
                    #현재 해당 전략에 의해 매수된 코인 개수가 맥스 코인보다 적다면! 그리고 아직 매수되지 않은 코인만!
                    if len(DolPaCoinList) < MaxCoinCnt and myUpbit.IsHasCoin(balances, ticker) == False:

                        #시장가 매수를 한다.
                        balances = myUpbit.BuyCoinMarket(upbit,ticker,CoinMoney)


                        #매수된 코인을 DolPaCoinList 리스트에 넣고 이를 파일로 저장해둔다!
                        DolPaCoinList.append(ticker)
                        
                        #파일에 리스트를 저장합니다
                        with open(dolpha_type_file_path, 'w') as outfile:
                            json.dump(DolPaCoinList, outfile)


                        #이렇게 매수했다고 메세지를 보낼수도 있다
                        line_alert.SendMessage("BUY Done Upbit Trend Dolpa Coin : " + ticker + " X: " + str(down_first_point) +  "," + str(down_second_point) )
        





    except Exception as e:
        print("---:", e)



