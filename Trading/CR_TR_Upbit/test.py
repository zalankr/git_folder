ETH20_signal = ["ETH20", "Buy"]
ETH40_signal = ["ETH40", "Cash"]
BTC30_signal = ["BTC30", "Buy"]

ETH_balance = 0
BTC_balance = 0
KRW_balance = 100
ETH_Buying = 0
ETH_Selling = 0
BTC_Buying = 0
BTC_Selling = 0


def get_Invest_balance(ETH20_signal, ETH40_signal, BTC30_signal, ETH_balance, BTC_balance, KRW_balance):
    ETH_Buying = 0
    ETH_Selling = 0
    BTC_Buying = 0
    BTC_Selling = 0

    if ETH20_signal[1] == "Buy" :
        if ETH40_signal[1] == "Buy":
            if BTC30_signal[1] == "Buy":
                ETH_Buying = KRW_balance * 0.66
                BTC_Buying = KRW_balance * 0.33
            elif BTC30_signal[1] == "Cash":
                ETH_Buying = KRW_balance * 0.66
                BTC_Buying = 0
            elif BTC30_signal[1] == "Sell":
                ETH_Buying = KRW_balance * 0.99
                BTC_Selling = BTC_balance
            elif BTC30_signal[1] == "Hold":
                ETH_Buying = KRW_balance * 0.99
                BTC_Buying = 0
        elif ETH40_signal[1] == "Cash":
            if BTC30_signal[1] == "Buy":
                ETH_Buying = KRW_balance * 0.33
                BTC_Buying = KRW_balance * 0.33
            elif BTC30_signal[1] == "Cash":
                ETH_Buying = KRW_balance * 0.33
                BTC_Buying = 0
            elif BTC30_signal[1] == "Sell":
                ETH_Buying = KRW_balance * 0.495
                BTC_Selling = BTC_balance
            elif BTC30_signal[1] == "Hold":
                ETH_Buying = KRW_balance * 0.495
                BTC_Buying = 0
        elif ETH40_signal[1] == "Sell":
            if BTC30_signal[1] == "Buy":
                ETH_Buying = 0
                BTC_Buying = KRW_balance * 0.495
            elif BTC30_signal[1] == "Cash":
                ETH_Buying = 0
                BTC_Buying = 0
            elif BTC30_signal[1] == "Sell":
                ETH_Buying = 0
                BTC_Selling = BTC_balance
            elif BTC30_signal[1] == "Hold":
                ETH_Buying = 0
                BTC_Buying = 0
        elif ETH40_signal[1] == "Hold":
            if BTC30_signal[1] == "Buy":
                ETH_Buying = KRW_balance * 0.495
                BTC_Buying = KRW_balance * 0.495
            elif BTC30_signal[1] == "Cash":
                ETH_Buying = KRW_balance * 0.495
                BTC_Buying = 0
            elif BTC30_signal[1] == "Sell":
                ETH_Buying = KRW_balance * 0.99
                BTC_Selling = BTC_balance
            elif BTC30_signal[1] == "Hold":
                ETH_Buying = KRW_balance * 0.99
                BTC_Buying = 0

    if ETH20_signal[1] == "Cash" :
        if ETH40_signal[1] == "Buy":
            if BTC30_signal[1] == "Buy":
                ETH_Buying = KRW_balance * 0.33
                BTC_Buying = KRW_balance * 0.33
            elif BTC30_signal[1] == "Cash":
                ETH_Buying = KRW_balance * 0.33
                BTC_Buying = 0
            elif BTC30_signal[1] == "Sell":
                ETH_Buying = KRW_balance * 0.495
                BTC_Selling = BTC_balance
            elif BTC30_signal[1] == "Hold":
                ETH_Buying = KRW_balance * 0.495
                BTC_Buying = 0
        elif ETH40_signal[1] == "Cash":
            if BTC30_signal[1] == "Buy":
                ETH_Buying = 0
                BTC_Buying = KRW_balance * 0.33
            elif BTC30_signal[1] == "Cash":
                ETH_Buying = 0
                BTC_Buying = 0
            elif BTC30_signal[1] == "Sell":
                ETH_Buying = 0
                BTC_Selling = BTC_balance
            elif BTC30_signal[1] == "Hold":
                ETH_Buying = 0
                BTC_Buying = 0
        elif ETH40_signal[1] == "Sell":
            if BTC30_signal[1] == "Buy":
                ETH_Selling = ETH_balance
                BTC_Buying = KRW_balance * 0.495
            elif BTC30_signal[1] == "Cash":
                ETH_Selling = ETH_balance
                BTC_Buying = 0
            elif BTC30_signal[1] == "Sell":
                ETH_Selling = ETH_balance
                BTC_Selling = BTC_balance
            elif BTC30_signal[1] == "Hold":
                ETH_Selling = ETH_balance
                BTC_Buying = 0
        elif ETH40_signal[1] == "Hold":
            if BTC30_signal[1] == "Buy":
                ETH_Buying = 0
                BTC_Buying = KRW_balance * 0.495
            elif BTC30_signal[1] == "Cash":
                ETH_Buying = 0
                BTC_Buying = 0
            elif BTC30_signal[1] == "Sell":
                ETH_Buying = 0
                BTC_Selling = BTC_balance
            elif BTC30_signal[1] == "Hold":
                ETH_Buying = 0
                BTC_Buying = 0

    if ETH20_signal[1] == "Sell" :
        if ETH40_signal[1] == "Buy":
            if BTC30_signal[1] == "Buy":
                ETH_Buying = 0
                BTC_Buying = KRW_balance * 0.495
            elif BTC30_signal[1] == "Cash":
                ETH_Buying = 0
                BTC_Buying = 0
            elif BTC30_signal[1] == "Sell":
                ETH_Buying = 0
                BTC_Selling = BTC_balance
            elif BTC30_signal[1] == "Hold":
                ETH_Buying = 0
                BTC_Buying = 0
        elif ETH40_signal[1] == "Cash":
            if BTC30_signal[1] == "Buy":
                ETH_Selling = ETH_balance
                BTC_Buying = KRW_balance * 0.495
            elif BTC30_signal[1] == "Cash":
                ETH_Selling = ETH_balance
                BTC_Buying = 0
            elif BTC30_signal[1] == "Sell":
                ETH_Selling = ETH_balance
                BTC_Selling = BTC_balance
            elif BTC30_signal[1] == "Hold":
                ETH_Selling = ETH_balance
                BTC_Buying = 0
        elif ETH40_signal[1] == "Sell":
            if BTC30_signal[1] == "Buy":
                ETH_Selling = ETH_balance
                BTC_Buying = KRW_balance * 0.99
            elif BTC30_signal[1] == "Cash":
                ETH_Selling = ETH_balance
                BTC_Buying = 0
            elif BTC30_signal[1] == "Sell":
                ETH_Selling = ETH_balance
                BTC_Selling = BTC_balance
            elif BTC30_signal[1] == "Hold":
                ETH_Selling = ETH_balance
                BTC_Buying = 0
        elif ETH40_signal[1] == "Hold":
            if BTC30_signal[1] == "Buy":
                ETH_Selling = ETH_balance*0.5
                BTC_Buying = KRW_balance * 0.99
            elif BTC30_signal[1] == "Cash":
                ETH_Selling = ETH_balance*0.5
                BTC_Buying = 0
            elif BTC30_signal[1] == "Sell":
                ETH_Selling = ETH_balance*0.5
                BTC_Selling = BTC_balance
            elif BTC30_signal[1] == "Hold":
                ETH_Selling = ETH_balance*0.5
                BTC_Buying = 0

    if ETH20_signal[1] == "Hold" :
        if ETH40_signal[1] == "Buy":
            if BTC30_signal[1] == "Buy":
                ETH_Buying = KRW_balance * 0.495
                BTC_Buying = KRW_balance * 0.495
            elif BTC30_signal[1] == "Cash":
                ETH_Buying = KRW_balance * 0.495
                BTC_Buying = 0
            elif BTC30_signal[1] == "Sell":
                ETH_Buying = KRW_balance * 0.99
                BTC_Selling = BTC_balance
            elif BTC30_signal[1] == "Hold":
                ETH_Buying = KRW_balance * 0.99
                BTC_Buying = 0
        elif ETH40_signal[1] == "Cash":
            if BTC30_signal[1] == "Buy":
                ETH_Buying = 0
                BTC_Buying = KRW_balance * 0.495
            elif BTC30_signal[1] == "Cash":
                ETH_Buying = 0
                BTC_Buying = 0
            elif BTC30_signal[1] == "Sell":
                ETH_Buying = 0
                BTC_Selling = BTC_balance
            elif BTC30_signal[1] == "Hold":
                ETH_Buying = 0
                BTC_Buying = 0
        elif ETH40_signal[1] == "Sell":
            if BTC30_signal[1] == "Buy":
                ETH_Selling = ETH_balance*0.5
                BTC_Buying = KRW_balance * 0.99
            elif BTC30_signal[1] == "Cash":
                ETH_Selling = ETH_balance*0.5
                BTC_Buying = 0
            elif BTC30_signal[1] == "Sell":
                ETH_Selling = ETH_balance*0.5
                BTC_Selling = BTC_balance
            elif BTC30_signal[1] == "Hold":
                ETH_Selling = ETH_balance
                BTC_Buying = 0
        elif ETH40_signal[1] == "Hold":
            if BTC30_signal[1] == "Buy":
                ETH_Buying = 0
                BTC_Buying = KRW_balance * 0.99
            elif BTC30_signal[1] == "Cash":
                ETH_Buying = 0
                BTC_Buying = 0
            elif BTC30_signal[1] == "Sell":
                ETH_Buying = 0
                BTC_Selling = BTC_balance
            elif BTC30_signal[1] == "Hold":
                ETH_Buying = 0
                BTC_Buying = 0

    return(ETH_Buying, ETH_Selling, BTC_Buying, BTC_Selling, KRW_balance)

list = get_Invest_balance(ETH20_signal, ETH40_signal, BTC30_signal, ETH_balance, BTC_balance, KRW_balance)
print("ETH_Buying:", list[0], "ETH_Selling:", list[1], "BTC_Buying:", list[2], "BTC_Selling:", list[3], "KRW_balance:", list[4])
