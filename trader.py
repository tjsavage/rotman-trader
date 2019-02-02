import signal
import requests
import time
from time import sleep
import math
import sys
from scipy import stats

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
lag = 0.250
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

def _flesh_out_book(curr_book, center_price, max_buy_volume=25000, max_sell_volume=25000, buy_range=5, buy_offset=1, sell_range=5, sell_offset=1):
    # Buy order
    new_book = dict(curr_book)
    curr_buy_volume = 0
    curr_sell_volume = 0

    for p, v in new_book['bids']:
        curr_buy_volume += v

    for p, v in new_book['asks']:
        curr_sell_volume += v

    max_buy_volume -= curr_buy_volume
    max_sell_volume -= curr_sell_volume

    for i in range(1 - buy_range - buy_offset, 1 - buy_offset):
        curr_price = center_price + i / 100
        vol_to_buy = math.trunc(max_buy_volume / buy_range)

        while vol_to_buy > 0:
            vol = min(max_order_size, vol_to_buy)
            new_book['bids'].append((curr_price, vol))

            vol_to_buy -= vol
    
    # Sell orders
    for i in range(sell_offset, sell_offset + sell_range):
        curr_price = center_price + i / 100
        vol_to_sell = math.trunc(max_sell_volume / sell_range)

        while vol_to_sell > 0:
            vol = min(max_order_size, vol_to_sell)
            new_book['asks'].append((curr_price, vol))

            vol_to_sell -= vol
    return new_book

def generate_ideal_book(strategy, ses):
    # Make it easy to test out different strategies

    # Get the minimum amount of data needed from the server
    ideal_book = {
        "bids": [],
        "asks": []
    }
    sec_data = securities.security_dict(ses, ticker_sym=sec)[sec]
    sec_last = sec_data.last
    position = sec_data.position

    if strategy == "simple_weighted":
        max_buy_volume = limit_stock / 2 - position
        max_sell_volume = limit_stock / 2 + position
        center_price = sec_last
        ideal_book = _flesh_out_book(ideal_book, center_price, max_buy_volume=max_buy_volume, max_sell_volume=max_sell_volume, buy_range=5, buy_offset=1, sell_range=5, sell_offset=1)

    elif strategy == "swoop_best":
        # Beat the best order in the book to close position, then do normal weighting
        max_buy_volume = limit_stock / 2 - position
        max_sell_volume = limit_stock / 2 + position

        bids_asks = book.get_all_bids_asks(ses, sec)
        curr_bids = bids_asks['bids']
        curr_asks = bids_asks['asks']
        if position < 0:
            best_bid = 0
            for order in curr_bids:
                if order['price'] > best_bid:
                    best_bid = order['price']
            ideal_book['bids'].append((best_bid, abs(position / 2)))
        elif position > 0:
            best_ask = 99999
            for order in curr_asks:
                if order['price'] < best_ask:
                    best_ask = order['price']
            ideal_book['asks'].append((best_ask, abs(position / 2)))
        
        ideal_book = _flesh_out_book(ideal_book, sec_last, max_buy_volume=max_buy_volume, max_sell_volume=max_sell_volume, buy_range=5, buy_offset=1, sell_range=5, sell_offset=1)
    elif strategy == "swoop_and_spread":
        # Beat the best order in the book to close position, then do normal weighting
        max_buy_volume = limit_stock / 2 - position
        max_sell_volume = limit_stock / 2 + position

        bids_asks = book.get_all_bids_asks(ses, sec)
        curr_bids = bids_asks['bids']
        curr_asks = bids_asks['asks']

        buy_offset = 1
        sell_offset = 1
        if position < 0:
            best_bid = 0
            for order in curr_bids:
                if order['price'] > best_bid:
                    best_bid = order['price']
            ideal_book['bids'].append((best_bid, abs(position / 2)))

            sell_offset += round(abs(position) / 5000)
        elif position > 0:
            best_ask = 99999
            for order in curr_asks:
                if order['price'] < best_ask:
                    best_ask = order['price']
            ideal_book['asks'].append((best_ask, abs(position / 2)))
        
            buy_offset += round(abs(position) / 5000)
        ideal_book = _flesh_out_book(ideal_book, sec_last, max_buy_volume=max_buy_volume, max_sell_volume=max_sell_volume, buy_range=6, buy_offset=buy_offset, sell_range=6, sell_offset=sell_offset)
    elif strategy == "normal":
        print("normal is broken don't use it yet!")
        center_price_cents = sec_last * 100 + round(position / 4000)
        sdev_cents = 2
        print((center_price_cents, sdev_cents))
        dist = stats.norm(center_price_cents, sdev_cents)

        max_buy_volume = limit_stock / 2 - position
        max_sell_volume = limit_stock / 2 + position

        remaining_buy_volume = max_buy_volume
        remaining_sell_volume = max_sell_volume

        for i in range(int(-sdev_cents * 3), int(sdev_cents * 3 + 1)):
            p = round(center_price_cents / 100 + i / 100, 2)
            ideal_vol = (dist.cdf(p*100+1) - dist.cdf(p * 100)) * max_buy_volume
            if p < sec_last:
                actual_vol = min(remaining_buy_volume, ideal_vol)

                ideal_book['bids'].append((p, actual_vol))
                remaining_buy_volume -= actual_vol
            elif p > sec_last:
                actual_vol = min(remaining_sell_volume, ideal_vol)
                
                ideal_book['asks'].append((p, actual_vol))
                remaining_sell_volume -= actual_vol            
    #sec_best_ask = book.get_best_ask(ses, sec)['price']

    #spread = default_spread

    return ideal_book

def main():
    print("Booting up")
    while not shutdown:
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