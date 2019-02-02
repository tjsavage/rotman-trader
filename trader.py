import signal
import requests
import time
from time import sleep
import math
import sys

import pandas as pd
import numpy as np
import matplotlib as plt

from ritpytrading.ritpytrading import cases
from ritpytrading.ritpytrading import securities_book as book
from ritpytrading.ritpytrading import submit_cancel_orders as broker
from ritpytrading.ritpytrading import orders
from ritpytrading.ritpytrading import securities

API_KEY = {'X-API-Key': 'PEGP33T3'}
shutdown = False

host_url = 'localhost:9999'
base_path = '/v1'
base_url = host_url + base_path

sec = "ALGO"
default_spread = 0.02
buy_volume = 2000
sell_volume = 2000
start_time = 295
stop_time = 5
max_order_size = 5000
lag = 0.1
limit_stock = 25000

class ApiException(Exception):
    pass

def signal_handler(signum, frame):
    global shutdown
    signal.signal(signal.SIGINT, signal.SIG_DFL)
    shutdown = True

def _price_vol_array_to_price_dict(arr):
    price_dict = {}

    for price, vol in arr:
        if price not in price_dict:
            price_dict[price] = 0
        price_dict[price] += vol
    return price_dict

def _convert_orders_dict_to_book(orders_dict):
    curr_book = {"bids":{}, "asks":{}}

    for k, v in orders_dict.items():
        if v.action == "BUY":
            curr_book['bids'][v.order_id] = (v.price, v.quantity - v.quantity_filled)
        else:
            curr_book['asks'][v.order_id] = (v.price, v.quantity - v.quantity_filled)

    return curr_book

def get_trades_for_ideal_book(curr_book, ideal_book, max_trade=None):
    '''
    curr_book should be of the form:
    {
        bids: { id: (price, vol) },
        asks: { id: (price, vol) }
    }

    ideal_book should be of the form:
    {   bids: [(price, vol)],
        asks: [(price, vol)]
    }
    where volume is positive for bids and negative for asks

    returns:
    {
        bids: [(price, vol)],
        asks: [(price, vol)],
        cancels: [orderId]
    }
    '''
   
    curr_vol_by_price = {"bids":{}, "asks":{}}
    curr_orders_by_price = {"bids":{}, "asks":{}}
    new_vol_by_price = {"bids":{}, "asks":{}}
    new_orders = {"bids":[], "asks":[], "cancels":[]}

    for direction in ["bids", "asks"]:
        for id, val in curr_book[direction].items():
            p, vol = val
            if p not in curr_vol_by_price[direction]:
                curr_vol_by_price[direction][p] = 0
            curr_vol_by_price[direction][p] += vol

            if p not in curr_orders_by_price[direction]:
                curr_orders_by_price[direction][p] = []
            curr_orders_by_price[direction][p].append((id, p, vol))
        
        ideal_vol_by_price = _price_vol_array_to_price_dict(ideal_book[direction])

        prices = set(curr_vol_by_price[direction].keys()).union(set(ideal_vol_by_price.keys()))

        for p in sorted(prices):
            if p in ideal_vol_by_price:
                curr_vol = curr_vol_by_price[direction][p] if p in curr_vol_by_price[direction] else 0
                ideal_vol = ideal_vol_by_price[p]

                if curr_vol < ideal_vol:
                    new_vol_by_price[direction][p] = ideal_vol - curr_vol
                elif ideal_vol < curr_vol:
                    potential_orders = [(id, price, vol) for (id, price, vol) in curr_orders_by_price[direction][p]]
                    potential_orders = sorted(potential_orders, key=lambda x: x[0])

                    remaining_vol = curr_vol
                    cancellable_orders = []
                    i = 0
                    while remaining_vol > ideal_vol and i < len(potential_orders):
                        o = potential_orders[i]
                        cancellable_orders.append(o[0])
                        remaining_vol -= o[2]
                    
                    new_orders['cancels'].extend(cancellable_orders)

                    if remaining_vol < ideal_vol:
                        new_vol_by_price[direction][p] = ideal_vol - remaining_vol

            else:
                orders = [id for (id, _price, _vol) in curr_orders_by_price[direction][p]]
                new_orders['cancels'].extend(orders)

            
        
        for p, vol in new_vol_by_price[direction].items():
            if max_trade and vol > max_trade:
                remaining_vol = vol
                while remaining_vol > 0:
                    trade_vol = min(max_trade, remaining_vol)

                    new_orders[direction].append((p, trade_vol))

                    remaining_vol -= trade_vol
            else:
                new_orders[direction].append((p, vol))
    
    return new_orders

def execute_orders(ses, sec, orders):
    bids = orders['bids']
    asks = orders['asks']
    cancels = orders['cancels']

    for p, v in bids:
        broker.limit_order(ses, sec, 'BUY', v, p)
    
    for p, v in asks:
        broker.limit_order(ses, sec, 'SELL', v, p)
    
    for c in cancels:
        broker.cancel_order(ses, c)

def generate_ideal_book(strategy, ses):
    ideal_book = {
        "bids": [],
        "asks": []
    }
    #sec_best_bid = book.get_best_bid(ses, sec)['price']
    #sec_best_ask = book.get_best_ask(ses, sec)['price']

    #spread = default_spread

    sec_data = securities.security_dict(ses, ticker_sym=sec)[sec]
    sec_last = sec_data.last
    position = sec_data.position

    if strategy == "simple_weighted":
        max_buy_volume = limit_stock / 2 - position
        max_sell_volume = limit_stock / 2 + position

        # Buy orders            
        for i in range(-5, 0):
            curr_price = sec_last + i / 100
            vol_to_buy = math.trunc(max_buy_volume / 5)

            while vol_to_buy > 0:
                vol = min(max_order_size, vol_to_buy)
                ideal_book['bids'].append((curr_price, vol))

                vol_to_buy -= vol
        
        # Sell orders
        for i in range(1, 6):
            curr_price = sec_last + i / 100
            vol_to_sell = math.trunc(max_sell_volume / 5)

            while vol_to_sell > 0:
                vol = min(max_order_size, vol_to_sell)
                ideal_book['asks'].append((curr_price, vol))

                vol_to_sell -= vol
    return ideal_book

def main():
    print("Booting up")
    with requests.Session() as ses:
        ses.headers.update(API_KEY)
        current_case = cases.case(ses)
        current_case_lim = cases.case_limits(ses)

        strategy = "simple_weighted"
        print(sys.argv)
        if len(sys.argv) == 2:
            strategy = sys.argv[1]
        print("Using strategy: %s" % strategy)

        tick = current_case.tick

        while tick > start_time:
            print("Waiting start...%d" % (tick - start_time))
            current_case = cases.case(ses)
            tick = current_case.tick
            time.sleep(1)

        while tick < stop_time:
            print("Stopped trading...%d" % tick)
            current_case = cases.case(ses)
            tick = current_case.tick
            time.sleep(1)

        while tick >= stop_time and tick <= start_time and not shutdown:
            orders_dict = orders.orders_dict(ses)
            curr_book = _convert_orders_dict_to_book(orders_dict)
            ideal_book = generate_ideal_book(strategy, ses)
            trades = get_trades_for_ideal_book(curr_book, ideal_book, max_trade=max_order_size)

            execute_orders(ses, sec, trades)

            sleep(lag)

            current_case = cases.case(ses)
            tick = current_case.tick
            
            

        

if __name__ == '__main__':
    signal.signal(signal.SIGINT, signal_handler)
    main()