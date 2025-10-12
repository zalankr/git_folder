def make_split_price(market, round):
    if market == "Pre-market":
        order_type = "order_daytime_US"
        sell_splits = 4
        sell_price_adjust = [1.015, 1.03, 1.045, 1.06]
        buy_splits = 2
        buy_price_adjust = [0.995, 0.99]

    elif market == "Regular":
        order_type = "order_US"
        sell_splits = 6
        sell_price_adjust = [1.0025, 1.005, 1.0075, 1.01, 1.0125, 1.015]
        buy_splits = 6
        buy_price_adjust = [0.9975, 0.995, 0.9925, 0.99, 0.9875, 0.985]

        if round in range(1, 7):
            pass

        elif round in range(7, 13):
            sell_price_adjust[0] = 0.99

        elif round in range(13, 19):
            sell_splits = 5
            sell_price_adjust = sell_price_adjust[:sell_splits]
            buy_price_adjust[0] = 1.01

        elif round in range(19, 25):
            sell_splits = 5
            sell_price_adjust = sell_price_adjust[:sell_splits]
            buy_splits = 5
            buy_price_adjust = buy_price_adjust[:buy_splits]

        elif round in range(25, 31):
            sell_splits = 5
            sell_price_adjust = sell_price_adjust[:sell_splits]
            sell_price_adjust[0] = 0.99
            buy_splits = 5
            buy_price_adjust = buy_price_adjust[:buy_splits]

        elif round in range(31, 37):
            sell_splits = 4
            sell_price_adjust = sell_price_adjust[:sell_splits]
            buy_splits = 5
            buy_price_adjust = buy_price_adjust[:buy_splits]
            buy_price_adjust[0] = 1.01

        elif round in range(37, 43):
            sell_splits = 4
            sell_price_adjust = sell_price_adjust[:sell_splits]
            buy_splits = 4
            buy_price_adjust = buy_price_adjust[:buy_splits]

        elif round in range(43, 49):
            sell_splits = 4
            sell_price_adjust = sell_price_adjust[:sell_splits]
            sell_price_adjust[0] = 0.99
            buy_splits = 4
            buy_price_adjust = buy_price_adjust[:buy_splits]

        elif round in range(49, 55):
            sell_splits = 3
            sell_price_adjust = sell_price_adjust[:sell_splits]
            buy_splits = 4
            buy_price_adjust = buy_price_adjust[:buy_splits]
            buy_price_adjust[0] = 1.01

        elif round in range(55, 61):
            sell_splits = 3
            sell_price_adjust = sell_price_adjust[:sell_splits]
            buy_splits = 3
            buy_price_adjust = buy_price_adjust[:buy_splits]

        elif round in range(61, 67):
            sell_splits = 3
            sell_price_adjust = sell_price_adjust[:sell_splits]
            sell_price_adjust[0] = 0.99
            buy_splits = 3
            buy_price_adjust = buy_price_adjust[:buy_splits]

        elif round in range(67, 73):
            sell_splits = 2
            sell_price_adjust = sell_price_adjust[:sell_splits]
            buy_splits = 3
            buy_price_adjust = buy_price_adjust[:buy_splits]
            buy_price_adjust[0] = 1.01

        elif round in range(73, 76):
            sell_splits = 2
            sell_price_adjust = [0.99, 1.0025]
            buy_splits = 2
            buy_price_adjust = buy_price_adjust[:buy_splits]

        elif round == 77:
            sell_splits = 1
            sell_price_adjust = [0.97]
            buy_splits = 2
            buy_price_adjust = [1.01, 0.9975]

        elif round == 78:
            sell_splits = 1
            sell_price_adjust = [0.97]
            buy_splits = 1
            buy_price_adjust = [1.03]
        
    result = {
        "sell_splits": sell_splits, 
        "sell_price_adjust": sell_price_adjust, 
        "buy_splits": buy_splits, 
        "buy_price_adjust": buy_price_adjust
    }

    return result

market = "Regular"
round = 66
print(make_split_price(market, round))