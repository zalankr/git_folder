def make_split_price(market, round):
    if market == "Pre-market":
        sell_splits = 4
        sell_price_adjust = [1.015, 1.03, 1.045, 1.06]
        buy_splits = 2
        buy_price_adjust = [0.995, 0.99]

    elif market == "Regular":
        sell_splits = 6
        sell_price_adjust = [1.0025, 1.005, 1.0075, 1.01, 1.0125, 1.015]
        buy_splits = 6
        buy_price_adjust = [0.9975, 0.995, 0.9925, 0.99, 0.9875, 0.985]

        if round in range(1, 7):
            pass

        elif round in range(7, 13):
            sell_price_adjust[0] = 0.99

        elif round in range(13, 19):
            pass ###################################################################################3
        
    result = {
        "sell_splits": sell_splits, 
        "sell_price_adjust": sell_price_adjust, 
        "buy_splits": buy_splits, 
        "buy_price_adjust": buy_price_adjust
    }

    return result


market = "Regular"
round = 8
print(make_split_price(market, round))