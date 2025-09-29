import ccxt
import time
import pandas as pd
import pprint

import myBybit
import ende_key  #암복호화키
import my_key    #업비트 시크릿 액세스키


import line_alert #라인 메세지를 보내기 위함!

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

'''
!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!

클래스에서 제공 되는 모든 봇은 샘플입니다.
당연히 논리적 오류나 에러가 있을 수도 있으며
수익을 전혀 내지 못하고 (혹은 잘 만들어 내다가도)
오히려 손해를 만들 수도 있습니다.


해당 봇은 기존 거미줄 매매를 개선하고자
2개의 옵션을 즉석에서 생각해 내서 반영을 해봤습니다!


옵션1 익절해서 포지션을 새로 잡을 때 물량을 늘려준다! 

-> 처음에 1씩 잡았는데
-> 한방향으로만 움직여서 롱이 40이나 물려있는데 숏은 1씩 익절하면 간의 기별도 안간다.
-> 따라서 반대편 물량의 특정 수준 1/4 혹은 1/5 등등의 수준으로 맞춰준다! 


옵션2 거미줄이 다 닿아서 풀 매수 상태의 포지션의 경우. 
-> 그대로 계속 반대로 움직여 청산당하면 타격이 크므로
-> 절반을 손절하고. 그 절반의 수량으로 거미줄을 또 깔아준다.
-> (즉 손절 후 다시 거미줄 절반깔고 탈출 기회를 노린다)
-> 반복… 
-> 전체 청산보다는 좋고, 탈출한다면 어느정도 손해도 메꿀 수 있다!


물론 둘다 완벽하지 않은 보완 방법이기에 폐기 하시거나
다른 옵션을 생각하셔도 됩니다. 어디까지나 제가 즉석에서 생각해서 낸 전략이니까요.
이렇게 봇을 개선해 나갈 수 있다. 이렇게 봇을 수정해 나가면 된다를 보여드린거고
나도 저런식으로 수정해 나가봐야지가 핵심이지

이 봇이 완벽하겠구나 올인 가즈아!!!
하시면 안됩니다 ^^ (빠른 손해의 지름길입니다)


두 개의 옵션 둘다 단점이 있습니다!

옵션 1은 다시 반대로 움직이면 그만큼 물린다는 악순환(?)의 단점이 있구요.
옵션 2도 급격한 상승(혹은 하락)을 맞이하면 즉 청산빔을 맞이하면 저렇게 절반 손절했는데 바로 또 손절을 연속으로 하고 결국 청산으로 이어질 수 있습니다.

따라서 이 두개의 옵션은 제가 시간이 지남에 따라 아예 폐기할 수도 수정할 수도 있습니다.
새로운 옵션이 생각나 봇에 반영할 수도 있구요. (아마 다른 봇을 사용할 수도 있습니다 아직 이후 과정이 남아 있으니까요 ^^)
이 과정을 계속 영상으로 만들 수는 없으니 (그럼 1년 내내 만들어야 될 수도요? ㅎ)


해당 봇의 기본 전략이 맘에 드신다면
이전 강의의 옵션1,2가 없는 코드와 비교해 보시면서
소액으로 테스트 해보시면서 개선해 나가 보세요 ^^!


양방향 그리드 거미줄 매매의 승패는 제 생각에

레버리지가 얼마?
거미줄의 개수는?
거미줄의 간격은?
거미줄마다의 수량은?
어떤 코인으로?


이 5가지의 조합마다 수익율이 정말 천차만별입니다!
어떤 조합은 최악일 수도 있습니다.
최적의 조합은 저도 모르니 한번 찾아보세요~^^
클래스에서 보여드린 조합, 그리고 현재 이 봇에 또 제가 추가적으로 수정한 조합이 최적일지 최악일지 이도저도 아닐지는 저도 모릅니다~^^

잊지마세요!

본 클래스는 낚시대를 만드는 방법을 알려드리는 클래스이지
낚시하는 방법을 알려드리는 클래스는 아닙니다~! 

물론 나중에 성공적인 낚시를 하는 낚시대를 발견하게 되면 꼭 공유할께요~^^!
감사합니다!



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


!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!

'''




#선물 마켓에서 거래중인 모든 코인을 가져옵니다.
Tickers = bybitX.load_markets()




#총 원금대비 설정 비율 
#아래처럼 0.2 로 셋팅하면 20%가 해당 전략에 할당된다는 이야기!
Invest_Rate = 0.2


#!!!여기에 매매 대상 코인을 넣으세요.!!!
##################################################
#테스트를 위해 코인 1개만 일단 해보시는걸 추천드립니다!
#영상에서 보여드린 GMT, APE 코인은 변동성이 심하기에 거미줄이 자주 뚫리면 오히려 손해가 더 커질 수 있습니다.
#적당한 변동성을 지닌 MANA, SAND, LINK 등의 코인으로 테스트 해보세요!!!
##################################################
LovelyCoinList = ['MANA/USDT:USDT']


#매매 대상 코인 개수 
CoinCnt = len(LovelyCoinList)


#################################################################################################################

#$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$#
##################################################
# 사실 레버가 높기에 옵션1, 옵션2 를 넣은건데 (옵션에 대한 설명은 클래스 영상 참조)
# 레버가 낮고 거미줄도 충분하다면 청산위험이 그만큼 줄어들게 됩니다.
# 옵션1, 옵션2가 제대로 손실을 커버한다는 보장도 없고 원웨이로 계속 가거나 빔을 쏴서 한번에 청산 당하면 손해가 날 수 밖에 없기에
# 고 레버리지는 양날의 검으로 큰 손해로 이어질 수도 있다는 점 유의하시고 큰 금액은 저 레버리지로 돌리시는걸 권장드려요!
# 영상에선 20배였는데 테스트 결과 20배는 너무 잦은 청산이 일어나기에 5배로 바꿨습니다. (이 경우 원금이 많이 들어가겠죠?)
# 저라면 원금이 더 늘어나더라도 더디더라도 2배 정도를 쓸거 같은데
# 이는 각자의 취향, 전략, 상황에 맞게 조절해 보세요!!
##################################################
set_leverage = 20
#$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$#



##################################################
#영상과는 다르게 목표수익율을 상향 시켰습니다!
#이어지는 거미줄 갭과 맞췄다는걸 체크하실 수 있습니다
##################################################
target_rate = 0.005   #목표 수익은 일단 0.5% 알아서 조절하세요!!!!
target_revenute = target_rate * 100.0

##################################################
#영상에서 0.0025로 0.25%가 갭이었는데 
#변동성이 심한 코인들이기에 0.005으로 간격을 0.5%씩으로 늘렸습니다.
#그리고 레버에 따라 그리고 거미줄 깔때 배수에 따라서
#간격을 너무 늘리면 거미줄이 다 소진되기 전에 청산이 일어날 수도 있습니다. 
#(극단적인 예로 레버 100배인데 거미줄이 2%마다 깔려있다면 거미줄 체결되기 전에 청산 되겠죠?)
#정답은 없습니다! 전략에 맞게 간격을 수정하세요!!
##################################################
st_water_gap_rate = 0.005 #0.5% --> 몇 퍼센트씩 아래에 물타기를 넣을건지,.  0.005이면 0.5%로 -0.5%, -1.0%, -1.5%, 이렇게 물타기 라인을 긋는다.






#모든 선물 거래가능한 코인을 가져온다.
for ticker in Tickers:

    try: 

   
        #하지만 여기서는 USDT 테더로 살수 있는 모든 선물 거래 코인들을 대상으로 돌려봅니다.
        if "/USDT:USDT" in ticker:
            Target_Coin_Ticker = ticker

            #러블리 코인이 아니라면 스킵! 러블리 코인만 대상으로 한다!!
            if myBybit.CheckCoinInList(LovelyCoinList,ticker) == False:
                continue

            
            time.sleep(0.2)
            
            Target_Coin_Symbol = ticker.replace("/", "").replace(":USDT","")



            time.sleep(0.05)
            #최소 주문 수량을 가져온다 
            minimun_amount = myBybit.GetMinimumAmount(bybitX,Target_Coin_Symbol)

            print("--- Target_Coin_Ticker:", Target_Coin_Ticker ," minimun_amount : ", minimun_amount)





            #잔고 데이타 가져오기 
            balances = bybitX.fetch_balance(params={"type": "future"})
            time.sleep(0.1)

                        
            print(balances['USDT'])
            print("Total Money:",float(balances['USDT']['total']))
            print("Remain Money:",float(balances['USDT']['free']))



            leverage = set_leverage  #레버리지

            #해당 코인 가격을 가져온다.
            coin_price = myBybit.GetCoinNowPrice(bybitX, Target_Coin_Ticker)





            #해당 코인에 할당된 금액에 따른 최대 매수수량을 구해본다!
            Max_Amt = float(bybitX.amount_to_precision(Target_Coin_Ticker, myBybit.GetAmount(float(balances['USDT']['total']),coin_price,Invest_Rate / CoinCnt)))  * leverage 
 
            print("Max_Amt:", Max_Amt)
    


            ##################################################################
            #영상엔 없지만 할당된 수량을 최소 주문 수량으로 나누면 분할이 가능한 숫자가 나옵니다
            minimun_divid_num = Max_Amt / minimun_amount
            
    
            #영상에서 100 분할이었으나
            #금액이 허용하는 한도내에서 최대 200분할로 변경해 거미줄 개수를 늘이고자 했습니다!
            divid_num= 200

            #다만 이 분할하고자 하는 개수는 최대 minimun_divid_num 만큼만 가능하니
            #크다면 조정해야 합니다!
            #즉 200분할을 위해 200을 넣었어도 할당된 원금(Max_Amt)이 작다면 200분할이 되지 않고
            #최소 주문 수량 기준으로 분할된 숫자가 나오게 됩니다. (원금이 매우 작다면 200으로 설정했지만 50분할밖에 안 나올 수도 있습니다!)
            if divid_num > minimun_divid_num:
                divid_num = minimun_divid_num

            ##################################################################



            #100분할 해서 1회 매수 코인 수량으로 정한다!
            Buy_Amt = Max_Amt / divid_num
            Buy_Amt = float(bybitX.amount_to_precision(Target_Coin_Ticker,Buy_Amt))

            
            print("Buy_Amt:", Buy_Amt)

            #최소 주문 수량보다 작다면 이렇게 셋팅!
            if Buy_Amt < minimun_amount:
                Buy_Amt = minimun_amount

            


            #################################
            #롱 숏 각각 거미줄들에 할당할 맥스 수량!
            #영상에서는 직관적으로 숫자로 직접 넣었지만
            #이렇게 자동계산되도록 하는게 더 맞습니다~^^
            #최대 할당 수량에서 첫 진입한 수량 1개씩 총 2개를 빼주면 총 물탈 수량이 나오는데
            #이를 롱과 숏이 나눠가져야 되니깐 2로 나누면 됩니다!
            Max_Water_Amt = (Max_Amt - (Buy_Amt * 2.0)) / 2.0
            #################################
            

            


            amt_s = 0 
            amt_b = 0
            entryPrice_s = 0 #평균 매입 단가. 따라서 물을 타면 변경 된다.
            entryPrice_b = 0 #평균 매입 단가. 따라서 물을 타면 변경 된다.
            is_isolated = False

            #잔고 데이타 가져오기 
            balances2 = bybitX.fetch_positions(None, {'type':'Future'})
            time.sleep(0.1)


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
            #레버리지와 격리모드 셋팅합니다! 
            print("###############", leverage)

            #교차 모드로 했다가 다시 격리모드로 설정하는 이유는 이미 교차모드일 경우 레버리지만 변경할려는 경우 이미 교차여서 레버리지 수정이 안되는 현상이 발견되어
            #이렇게 교차모드와 레버리지 설정했다가 다시 격리모드로 설정하는 식으로 보완을 했습니다!
            if is_isolated == False or leverage != set_leverage:
                try:
                    print(bybitX.set_margin_mode("cross",Target_Coin_Symbol, {'leverage':set_leverage}))
                except Exception as e:
                    print("---:", e)

                try:
                    print(bybitX.set_margin_mode("isolated",Target_Coin_Symbol, {'leverage':set_leverage}))
                except Exception as e:
                    print("---:", e)
            #################################################################################################################


  


            #숏 포지션이 없을 경우
            if abs(amt_s) == 0:

                #영상엔 없지만 포지션 잡을때 마다 내게 메세지를 보내봅니다! (이게 오면 익절했다는 이야기겠죠?) 자꾸 오는게 싫으시면 주석처리 하시면 됩니다!
                line_alert.SendMessage(Target_Coin_Ticker + " Grid Short Start!! " )


                #주문 정보를 읽어서 혹시 걸려있는 주문이 있다면 모두 취소해준다! 새로 숏포지션 잡고 거미줄 새로 깔꺼니깐
                orders = bybitX.fetch_orders(Target_Coin_Ticker,None,500)

                for order in orders:

                    close_on_trigger = None
                    try:
                        close_on_trigger = order['info']['close_on_trigger']
                    except Exception as e:
                        close_on_trigger = order['info']['closeOnTrigger']
                        
                    #숏의 오픈 주문을 취소합니다.
                    if order['status'] == "open" and close_on_trigger == False and order['side'] == "sell":
                        bybitX.cancel_order(order['id'],Target_Coin_Ticker)

                        #영상에 빠뜨렸지만 이렇게 꼭 쉬어줘야 합니다!
                        time.sleep(0.05)
         

                #옵션1 반대편 포시션의 수량이 너무 커졌을때 그 일부분으로 비중을 맞춰준다!
                ##################################################
                #영상에서 0.25로 1/4 이었는데 0.2 1/5로 수정했습니다. 
                #너무 많은 수량으로 시작하면 반대로 움직일시 그만큼 물리기에 사실 정답은 없습니다.
                ##################################################
                #영상에 빠졌지만 FirstAmt라고 처음 진입 하는 변수를 만들어 처리를 했습니다!
                FirstAmt = Buy_Amt

                if abs(amt_b) * 0.2 > FirstAmt:
                    FirstAmt = abs(amt_b) * 0.2





                #숏 시장가 주문!
                #data = bybitX.create_market_sell_order(Target_Coin_Ticker, FirstAmt)
                print(bybitX.create_order(Target_Coin_Ticker, 'market', 'sell', FirstAmt, None ,{'position_idx':2}))
                #해당 코인 가격을 가져온다.
                coin_price = myBybit.GetCoinNowPrice(bybitX, Target_Coin_Ticker)


                
                #익절할 가격을 구합니다.
                target_price = coin_price * (1.0 - target_rate)
                            

                #숏 포지션 지정가 종료 주문!!                 
                #print(bybitX.create_limit_buy_order(Target_Coin_Ticker, FirstAmt, target_price, {'reduce_only': True,'close_on_trigger':True}))
                print(bybitX.create_order(Target_Coin_Ticker, 'limit', 'buy', FirstAmt, target_price,{'position_idx':2, 'reduce_only': True,'close_on_trigger':True}))



                

                #아래는 물타기 라인을 긋는 로직입니다.
                TotalWater_Amt = 0 #누적 거미줄에 깔린 수량


                ##################################################
                #물타는 시작 금액을 첫 매수 수량의 1/2로 보정하고 이게 Buy_Amt보다 작으면 다시 Buy_Amt로 맞춰줍니다
                #보정 하는 이유는 거미줄 개수를 늘리기 위함이고 전략에 따라 안해도 됩니다.
                ##################################################
                Water_amt = FirstAmt * 0.5

                if Water_amt < Buy_Amt:
                    Water_amt = Buy_Amt

                print("Water_amt", Water_amt)

                i = 1
       
       
                ##################################################
                #영상에 없지만 첫 진입 수량이 200분할(Buy_Amt)보다 클 수 있으므로 물타기 최대 매수 가능 수량을 보정해줘야 합니다!
                #즉 처음에 원래 1씩 잡는데... 4를 잡았다면 4-1 = 3
                #3이란 숫자가 아래 변수에 들어가고 아래 while문에서 보정 값으로 쓰입니다.
                ##################################################
                Adjust_Max_Amt = (FirstAmt - Buy_Amt)


                while TotalWater_Amt + Water_amt < Max_Water_Amt - Adjust_Max_Amt: ######여기서 최대 맥스수량을 보정해 줍니다#####

                    print("--------------------->",i ,": Grid!!!")

                    water_price = coin_price * (1.0 + (st_water_gap_rate * i)) 



                    #실제 물타는 매수 라인 주문을 넣는다.
                    #print(bybitX.create_limit_sell_order(Target_Coin_Ticker, Water_amt, water_price))
                    print(bybitX.create_order(Target_Coin_Ticker, 'limit', 'sell', Water_amt, water_price,{'position_idx':2}))
                    

                    TotalWater_Amt += Water_amt

                        
                    ##################################################
                    #이 값은 자유롭게 조절하세요! 영상에선 1.1 이었으나 거미줄 개수를 늘려보고자 1.05로 조정해 봤습니다!
                    #즉 배수를 줄인건데 이러면 오히려 탈출이 힘들어 질 수 있습니다. (따라서 저도 다시 늘릴 수 있습니다)
                    #사실 원금이 많다면 이상적인 베스트 배수는 1.5, 2.0, 3.0 이런식으로 물을 확확 타는게 가장 좋습니다!
                    #즉 배수가 높으면 탈출 확율이 높아지는 대신 한정된 원금에 의해 거미줄 개수가 줄어드니 거미줄 간격을 늘릴 필요성이 생기고
                    #배수가 낮으면 거미줄 개수가 많아져 좋은데 탈출 확율이 줄어들게 됩니다. (물을 확확 타지 않기에 평단이 잘 안 움직임)
                    #정답은 없습니다 여러분 자금 사정에 맞게 전략에 맞게 선택하세요!
                    ##################################################
                    Water_amt *= 1.05

                    i += 1

                    time.sleep(0.1)

   

                

            else:
                #숏 포지션이 있는 경우
                if abs(amt_s) > 0:

                    #주문 정보를 읽어온다.
                    orders = bybitX.fetch_orders(Target_Coin_Ticker,None,500)

                    #물타기 거미줄이 남아있는지 알아낸다.
                    Is_Water_Remain = False
                    for order in orders:

                        close_on_trigger = None
                        try:
                            close_on_trigger = order['info']['close_on_trigger']
                        except Exception as e:
                            close_on_trigger = order['info']['closeOnTrigger']
                            
                        if order['status'] == "open"  and close_on_trigger == False and order['side'] == "sell":
                            Is_Water_Remain = True
                            break


                    #옵션2. 거미줄이 없다. 풀 매수 상태다
                    if Is_Water_Remain == False:
                        print("FULL")




                        #영상엔 없지만 손절들어갈 때 나에게 메세지를 보낼 수 있습니다.
                        line_alert.SendMessage(Target_Coin_Ticker + " Grid Short CUT LOSS!! " )

                        #영상엔 없지만 손절 수량을 변수로 담아서 처리합니다!
                        Cut_Amt = abs(amt_s) * 0.5

                        #그럴리는 없지만 손절 수량이 최소 매수수량보다 작다면 보정해줍니다.
                        #쓸데 없지만 이렇게 보정하는 습관은 필요합니다.
                        if Cut_Amt < minimun_amount:
                            Cut_Amt = minimun_amount


                        #절반 손절!! 시장가로!
                        #print(bybitX.create_market_buy_order(Target_Coin_Ticker,Cut_Amt,{'reduce_only': True,'close_on_trigger':True}))
                        print(bybitX.create_order(Target_Coin_Ticker, 'market', 'buy', Cut_Amt, None,{'position_idx':2,'reduce_only': True,'close_on_trigger':True}))
                        

                        time.sleep(1.0)

                        #잔고 데이타 가져오기 
                        balances2 = bybitX.fetch_positions(None, {'type':'Future'})
                        time.sleep(0.1)


                        #숏 잔고
                        for posi in balances2:
                            if posi['info']['symbol'] == Target_Coin_Symbol and posi['info']['side'] == "Sell":


                                try:
                                    amt_s = float(posi['info']['size'])
                                    entryPrice_s = float(posi['info']['entry_price'])
                                    leverage = float(posi['info']['leverage'])

                                except Exception as e:
                                    amt_s = float(posi['info']['size'])
                                    entryPrice_s = float(posi['info']['avgPrice'])
                                    leverage = float(posi['info']['leverage'])


                                break



                        for order in orders:


                            close_on_trigger = None
                            try:
                                close_on_trigger = order['info']['close_on_trigger']
                            except Exception as e:
                                close_on_trigger = order['info']['closeOnTrigger']
                                
                            #숏의 익절 주문을 취소합니다.
                            if order['status'] == "open" and close_on_trigger == True and order['side'] == "buy":
                                bybitX.cancel_order(order['id'],Target_Coin_Ticker)

                                #영상에 빠뜨렸지만 이렇게 꼭 쉬어줘야 합니다!
                                time.sleep(0.05)

            


                        #익절할 가격을 구합니다.
                        target_price = entryPrice_s * (1.0 - target_rate)


                        #그리고 지정가로 익절 주문을 걸어놓는다!                      
                        #print(bybitX.create_limit_buy_order(Target_Coin_Ticker, abs(amt_s), target_price, {'reduce_only': True,'close_on_trigger':True}))
                        print(bybitX.create_order(Target_Coin_Ticker, 'limit', 'buy', abs(amt_s), target_price,{'position_idx':2,'reduce_only': True,'close_on_trigger':True}))



                        
                        TotalWater_Amt = 0 #누적 거미줄에 깔린 수량

                        ##################################################
                        #영상에서 Water_amt = abs(amt_s) 였지만 그대로 쓰시면 거미줄이 1개 밖에 깔리지 않겠더라구요.
                        #그렇다고 Buy_amt로 시작하면 물타는게 의미가 사리지고 그래서 0.2라는 수치를 설정했습니다. 1/5
                        #즉 0.2을 곱해 거미줄 시작 비중을 줄였는데 이는 전략에 맞게 조절해 보세요!
                        ##################################################
                        Water_amt = abs(amt_s) * 0.2
                        print("Water_amt", Water_amt)
                        
                        if Water_amt < Buy_Amt:
                            Water_amt = Buy_Amt

                        i = 1

                        ##################################################
                        #여기서도 물타기 맥스 수량 보정이 필요합니다.
                        #절반을 손절해 절반이 남았다면 그 절반의 수량 만큼은 
                        #물타기 맥스 수량에서 빼줘야 거미줄이 내 원금 이상으로 깔리지 않습니다.
                        ##################################################
                        Adjust_Max_Amt = (abs(amt_s) - Buy_Amt)

                        while TotalWater_Amt + Water_amt < Max_Water_Amt - Adjust_Max_Amt: #이렇게 보정을 합니다!

                        
                            print("--------------------->",i ,": Grid!!!")

                            water_price = entryPrice_s * (1.0 + (st_water_gap_rate * i)) # 0.25%씩 가격이 상승합니다.


                            #실제 물타는 매수 라인 주문을 넣는다.
                            #print(bybitX.create_limit_sell_order(Target_Coin_Ticker, Water_amt, water_price))
                            print(bybitX.create_order(Target_Coin_Ticker, 'limit', 'sell', Water_amt, water_price ,{'position_idx':2}))
                            

                            TotalWater_Amt += Water_amt


                            ##################################################
                            #이 값은 자유롭게 조절하세요! 영상에선 1.1 이었으나 거미줄 개수를 늘려보고자 1.05로 조정해 봤습니다!
                            #즉 배수를 줄인건데 이러면 오히려 탈출이 힘들어 질 수 있습니다. (따라서 저도 다시 늘릴 수 있습니다)
                            #사실 원금이 많다면 이상적인 베스트 배수는 1.5, 2.0, 3.0 이런식으로 물을 확확 타는게 가장 좋습니다!
                            #즉 배수가 높으면 탈출 확율이 높아지는 대신 한정된 원금에 의해 거미줄 개수가 줄어드니 거미줄 간격을 늘릴 필요성이 생기고
                            #배수가 낮으면 거미줄 개수가 많아져 좋은데 탈출 확율이 줄어들게 됩니다. (물을 확확 타지 않기에 평단이 잘 안 움직임)
                            #정답은 없습니다 여러분 자금 사정에 맞게 전략에 맞게 선택하세요!
                            ##################################################
                            Water_amt *= 1.05

                            i += 1

                            time.sleep(0.1)




                    else:


                        #익절할 가격을 구합니다.
                        target_price = entryPrice_s * (1.0 - target_rate)

                        #### 영상에 없지만 익절 주문이 있는지 여부 플래그 변수를 하나 만들었어요! ###
                        bExist = False


                        for order in orders:


                            close_on_trigger = None
                            try:
                                close_on_trigger = order['info']['close_on_trigger']
                            except Exception as e:
                                close_on_trigger = order['info']['closeOnTrigger']
                                
                            #익절 주문을 필터합니다.
                            if order['status'] == "open"  and close_on_trigger == True and order['side'] == "buy":

                                                                
                                bExist = True #### 익절 주문이 있다면 (당연히 있겠죠)! True를 입력해줍니다. ###


                                #이 안에 들어왔다면 익절 주문인데
                                #익절 주문의 가격이 위에서 방금 구한 익절할 가격과 다르다면? 거미줄에 닿아 평단과 수량이 바뀐 경우니깐 
                                if float(order['price']) != float(bybitX.price_to_precision(Target_Coin_Ticker,target_price)):

                                    #기존 익절 주문 취소하고
                                    bybitX.cancel_order(order['id'],Target_Coin_Ticker)

                                    time.sleep(0.1)

        
                                    #숏 포지션 지정가 종료 주문!!                 
                                    #print(bybitX.create_limit_buy_order(Target_Coin_Ticker, abs(amt_s), target_price, {'reduce_only': True,'close_on_trigger':True}))
                                    print(bybitX.create_order(Target_Coin_Ticker, 'limit', 'buy', abs(amt_s), target_price,{'position_idx':2,'reduce_only': True,'close_on_trigger':True}))


                        #### 앗 그런데 익절 주문이 없다고???? ###
                        if bExist == False:

                            #그리고 지정가로 익절 주문을 걸어놓는다!                      
                            #print(bybitX.create_limit_buy_order(Target_Coin_Ticker, abs(amt_s), target_price, {'reduce_only': True,'close_on_trigger':True}))
                            print(bybitX.create_order(Target_Coin_Ticker, 'limit', 'buy', abs(amt_s), target_price,{'position_idx':2,'reduce_only': True,'close_on_trigger':True}))

                                                
            
            
            #롱 포지션이 없을 경우
            if abs(amt_b) == 0:

                #영상엔 없지만 포지션 잡을때 마다 내게 메세지를 보내봅니다! (이게 오면 익절했다는 이야기겠죠?) 자꾸 오는게 싫으시면 주석처리 하시면 됩니다!
                line_alert.SendMessage(Target_Coin_Ticker + " Grid Long Start!! " )


                #주문 정보를 읽어서 혹시 걸려있는 주문이 있다면 모두 취소해준다! 새로 롱포지션 잡고 거미줄 새로 깔꺼니깐
                orders = bybitX.fetch_orders(Target_Coin_Ticker,None,500)

                for order in orders:

                    close_on_trigger = None
                    try:
                        close_on_trigger = order['info']['close_on_trigger']
                    except Exception as e:
                        close_on_trigger = order['info']['closeOnTrigger']

                        
                    #롱의 오픈 주문을 취소합니다.
                    if order['status'] == "open" and close_on_trigger == False and order['side'] == "buy":
                        bybitX.cancel_order(order['id'],Target_Coin_Ticker)

                        #영상에 빠뜨렸지만 이렇게 꼭 쉬어줘야 합니다!
                        time.sleep(0.05)
         

                #옵션1 반대편 포시션의 수량이 너무 커졌을때 그 일부분으로 비중을 맞춰준다!
                ##################################################
                #영상에서 0.25로 1/4 이었는데 0.2 1/5로 수정했습니다. 
                #너무 많은 수량으로 시작하면 반대로 움직일시 그만큼 물리기에 사실 정답은 없습니다.
                ##################################################
                #영상에 빠졌지만 FirstAmt라고 처음 진입 하는 변수를 만들어 처리를 했습니다!
                FirstAmt = Buy_Amt 
                if abs(amt_s) * 0.2 > FirstAmt:
                    FirstAmt = abs(amt_s) * 0.2



                #롱 시장가 주문!
                #data = bybitX.create_market_buy_order(Target_Coin_Ticker, FirstAmt)
                print(bybitX.create_order(Target_Coin_Ticker, 'market', 'buy', FirstAmt, None, {'position_idx':1}))

                #해당 코인 가격을 가져온다.
                coin_price = myBybit.GetCoinNowPrice(bybitX, Target_Coin_Ticker)

                #익절할 가격을 구합니다.
                target_price = coin_price * (1.0 + target_rate)
                            

                #롱 포지션 지정가 종료 주문!!     
                #print(bybitX.create_limit_sell_order(Target_Coin_Ticker, FirstAmt, target_price, {'reduce_only': True,'close_on_trigger':True}))
                print(bybitX.create_order(Target_Coin_Ticker, 'limit', 'sell', FirstAmt, target_price,{'position_idx':1,'reduce_only': True,'close_on_trigger':True}))

                




                #아래는 물타기 라인을 긋는 로직입니다.
                TotalWater_Amt = 0 #누적 거미줄에 깔린 수량


                ##################################################
                #물타는 시작 금액을 첫 매수 수량의 1/2로 보정하고 이게 Buy_Amt보다 작으면 다시 Buy_Amt로 맞춰줍니다
                #보정 하는 이유는 거미줄 개수를 늘리기 위함이고 전략에 따라 안해도 됩니다.
                ##################################################
                Water_amt = FirstAmt * 0.5

                if Water_amt < Buy_Amt:
                    Water_amt = Buy_Amt

                print("Water_amt", Water_amt)

                i = 1
       

                ##################################################
                #영상에 없지만 첫 진입 수량이 200분할(Buy_Amt)보다 클 수 있으므로 물타기 최대 매수 가능 수량을 보정해줘야 합니다!
                #즉 처음에 원래 1씩 잡는데... 4를 잡았다면 4-1 = 3
                #3이란 숫자가 아래 변수에 들어가고 아래 while문에서 보정 값으로 쓰입니다.
                ##################################################
                Adjust_Max_Amt = (FirstAmt - Buy_Amt)


                while TotalWater_Amt + Water_amt < Max_Water_Amt - Adjust_Max_Amt: ######여기서 최대 맥스수량을 보정해 줍니다#####

                    print("--------------------->",i ,": Grid!!!")

                    water_price = coin_price * (1.0 - (st_water_gap_rate * i)) 



                    #실제 물타는 매수 라인 주문을 넣는다.
                    #print(bybitX.create_limit_buy_order(Target_Coin_Ticker, Water_amt, water_price))
                    print(bybitX.create_order(Target_Coin_Ticker, 'limit', 'buy', Water_amt, water_price, {'position_idx':1}))

                    TotalWater_Amt += Water_amt

                    ##################################################
                    #이 값은 자유롭게 조절하세요! 영상에선 1.1 이었으나 거미줄 개수를 늘려보고자 1.05로 조정해 봤습니다!
                    #즉 배수를 줄인건데 이러면 오히려 탈출이 힘들어 질 수 있습니다. (따라서 저도 다시 늘릴 수 있습니다)
                    #사실 원금이 많다면 이상적인 베스트 배수는 1.5, 2.0, 3.0 이런식으로 물을 확확 타는게 가장 좋습니다!
                    #즉 배수가 높으면 탈출 확율이 높아지는 대신 한정된 원금에 의해 거미줄 개수가 줄어드니 거미줄 간격을 늘릴 필요성이 생기고
                    #배수가 낮으면 거미줄 개수가 많아져 좋은데 탈출 확율이 줄어들게 됩니다. (물을 확확 타지 않기에 평단이 잘 안 움직임)
                    #정답은 없습니다 여러분 자금 사정에 맞게 전략에 맞게 선택하세요!
                    ##################################################
                    Water_amt *= 1.05

                    i += 1

                    time.sleep(0.1)

                    


            else:
                #롱 포지션이 있는 경우
                if abs(amt_b) > 0:



                    orders = bybitX.fetch_orders(Target_Coin_Ticker,None,500)

                    #물타기 거미줄이 남아있는지 알아낸다.
                    Is_Water_Remain = False
                    for order in orders:
                        close_on_trigger = None
                        try:
                            close_on_trigger = order['info']['close_on_trigger']
                        except Exception as e:
                            close_on_trigger = order['info']['closeOnTrigger']
                        
                        if order['status'] == "open"  and close_on_trigger == False and order['side'] == "buy":
                            Is_Water_Remain = True
                            break


                    #옵션2. 거미줄이 없다. 풀 매수 상태다
                    if Is_Water_Remain == False:


                        #영상엔 없지만 손절들어갈 때 나에게 메세지를 보낼 수 있습니다.
                        line_alert.SendMessage(Target_Coin_Ticker + " Grid Long CUT LOSS!! " )

                        print("FULL")


                        #영상엔 없지만 손절 수량을 변수로 담아서 처리합니다!
                        Cut_Amt = abs(amt_b) * 0.5

                        #그럴리는 없지만 손절 수량이 최소 매수수량보다 작다면 보정해줍니다.
                        #쓸데 없지만 이렇게 보정하는 습관은 필요합니다.
                        if Cut_Amt < minimun_amount:
                            Cut_Amt = minimun_amount


                        #절반 손절!! 시장가로!
                        #print(bybitX.create_market_sell_order(Target_Coin_Ticker,Cut_Amt,{'reduce_only': True,'close_on_trigger':True}))
                        print(bybitX.create_order(Target_Coin_Ticker, 'market', 'sell', Cut_Amt, None,{'position_idx':1,'reduce_only': True,'close_on_trigger':True}))


                        time.sleep(1.0)



                        #잔고 데이타 가져오기 
                        balances2 = bybitX.fetch_positions(None, {'type':'Future'})
                        time.sleep(0.1)


                        #롱 잔고
                        for posi in balances2:
                            if posi['info']['symbol'] == Target_Coin_Symbol and posi['info']['side'] == "Buy":


                                try:

                                    amt_b = float(posi['info']['size'])
                                    entryPrice_b = float(posi['info']['entry_price'])
                                    leverage = float(posi['info']['leverage'])

                                except Exception as e:

                                    amt_b = float(posi['info']['size'])
                                    entryPrice_b = float(posi['info']['avgPrice'])
                                    leverage = float(posi['info']['leverage'])

                                break



                        for order in orders:

                            close_on_trigger = None
                            try:
                                close_on_trigger = order['info']['close_on_trigger']
                            except Exception as e:
                                close_on_trigger = order['info']['closeOnTrigger']


                            #롱의 익절 주문을 취소합니다.
                            if order['status'] == "open" and close_on_trigger == True and order['side'] == "sell":
                                bybitX.cancel_order(order['id'],Target_Coin_Ticker)

                                #영상에 빠뜨렸지만 이렇게 꼭 쉬어줘야 합니다!
                                time.sleep(0.05)




                        #익절할 가격을 구합니다.
                        target_price = entryPrice_b * (1.0 + target_rate)
                                    
           
                        #롱 포지션 지정가 종료 주문!!     
                        #print(bybitX.create_limit_sell_order(Target_Coin_Ticker, abs(amt_b), target_price, {'reduce_only': True,'close_on_trigger':True}))
                        print(bybitX.create_order(Target_Coin_Ticker, 'limit', 'sell', abs(amt_b), target_price,{'position_idx':1, 'reduce_only': True,'close_on_trigger':True}))
                        



                        TotalWater_Amt = 0 #누적 거미줄에 깔린 수량

                        ##################################################
                        #영상에서 Water_amt = abs(amt_b) 였지만 그대로 쓰시면 거미줄이 1개 밖에 깔리지 않겠더라구요.
                        #그렇다고 Buy_amt로 시작하면 물타는게 의미가 사리지고 그래서 0.2라는 수치를 설정했습니다. 1/5
                        #즉 0.2을 곱해 거미줄 시작 비중을 줄였는데 이는 전략에 맞게 조절해 보세요!
                        ##################################################
                        Water_amt = abs(amt_b) * 0.2
                        print("Water_amt", Water_amt)

                        if Water_amt < Buy_Amt:
                            Water_amt = Buy_Amt


                        i = 1


                        ##################################################
                        #여기서도 물타기 맥스 수량 보정이 필요합니다.
                        #절반을 손절해 절반이 남았다면 그 절반의 수량 만큼은 
                        #물타기 맥스 수량에서 빼줘야 거미줄이 내 원금 이상으로 깔리지 않습니다.
                        ##################################################
                        Adjust_Max_Amt = (abs(amt_b) - Buy_Amt)

                        while TotalWater_Amt + Water_amt < Max_Water_Amt - Adjust_Max_Amt: #여기서 보정을 합니다

                            print("--------------------->",i ,": Grid!!!")

                            water_price = entryPrice_b * (1.0 - (st_water_gap_rate * i)) 

                            #실제 물타는 매수 라인 주문을 넣는다.

                            #print(bybitX.create_limit_buy_order(Target_Coin_Ticker, Water_amt, water_price))
                            print(bybitX.create_order(Target_Coin_Ticker, 'limit', 'buy', Water_amt, water_price,{'position_idx':1, 'reduce_only': True,'close_on_trigger':True}))


                            TotalWater_Amt += Water_amt

                            ##################################################
                            #이 값은 자유롭게 조절하세요! 영상에선 1.1 이었으나 거미줄 개수를 늘려보고자 1.05로 조정해 봤습니다!
                            #즉 배수를 줄인건데 이러면 오히려 탈출이 힘들어 질 수 있습니다. (따라서 저도 다시 늘릴 수 있습니다)
                            #사실 원금이 많다면 이상적인 베스트 배수는 1.5, 2.0, 3.0 이런식으로 물을 확확 타는게 가장 좋습니다!
                            #즉 배수가 높으면 탈출 확율이 높아지는 대신 한정된 원금에 의해 거미줄 개수가 줄어드니 거미줄 간격을 늘릴 필요성이 생기고
                            #배수가 낮으면 거미줄 개수가 많아져 좋은데 탈출 확율이 줄어들게 됩니다. (물을 확확 타지 않기에 평단이 잘 안 움직임)
                            #정답은 없습니다 여러분 자금 사정에 맞게 전략에 맞게 선택하세요!
                            ##################################################
                            Water_amt *= 1.05

                            i += 1

                            time.sleep(0.1)

                    else:

                        #익절할 가격을 구합니다.
                        target_price = entryPrice_s * (1.0 + target_rate)


                        #### 영상에 없지만 익절 주문이 있는지 여부 플래그 변수를 하나 만들었어요! ###
                        bExist = False


                        for order in orders:

                            close_on_trigger = None
                            try:
                                close_on_trigger = order['info']['close_on_trigger']
                            except Exception as e:
                                close_on_trigger = order['info']['closeOnTrigger']



                            #익절 주문을 필터합니다.
                            if order['status'] == "open"  and close_on_trigger == True and order['side'] == "sell":


                                bExist = True #### 익절 주문이 있다면 (당연히 있겠죠)! True를 입력해줍니다. ###

                                #이 안에 들어왔다면 익절 주문인데
                                #익절 주문의 가격이 위에서 방금 구한 익절할 가격과 다르다면? 거미줄에 닿아 평단과 수량이 바뀐 경우니깐 
                                if float(order['price']) != float(bybitX.price_to_precision(Target_Coin_Ticker,target_price)):

                                    #기존 익절 주문 취소하고
                                    bybitX.cancel_order(order['id'],Target_Coin_Ticker)

                                    time.sleep(0.1)

        
                                    #롱 포지션 지정가 종료 주문!!                 
                                    #print(bybitX.create_limit_sell_order(Target_Coin_Ticker, abs(amt_b), target_price, {'reduce_only': True,'close_on_trigger':True}))
                                    print(bybitX.create_order(Target_Coin_Ticker, 'limit', 'sell', abs(amt_b), target_price,{'position_idx':1,'reduce_only': True,'close_on_trigger':True}))


                                


                        #### 앗 그런데 익절 주문이 없다고???? ###
                        if bExist == False:

                            #그럼 익절 주문을 걸어 둡니다     
                            #print(bybitX.create_limit_sell_order(Target_Coin_Ticker, abs(amt_b), target_price, {'reduce_only': True,'close_on_trigger':True}))
                            print(bybitX.create_order(Target_Coin_Ticker, 'limit', 'sell', abs(amt_b), target_price,{'position_idx':1,'reduce_only': True,'close_on_trigger':True}))

                           

                


    except Exception as e:
        print("---:", e)



