import signal
import requests
import time
from time import sleep
import math

import pandas as pd
import numpy as np
import matplotlib as plt

from ritpytrading.ritpytrading import cases
from ritpytrading.ritpytrading import securities_book as book
from ritpytrading.ritpytrading import submit_cancel_orders as broker
from ritpytrading.ritpytrading import orders
from ritpytrading.ritpytrading import securities

API_KEY = {'X-API-Key': 'SUOIT2WZ'}
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
lag = 0.5
limit_stock = 25000

class ApiException(Exception):
    pass

def signal_handler(signum, frame):
    global shutdown
    signal.signal(signal.SIGINT, signal.SIG_DFL)
    shutdown = True

def main():
    print("Booting up")
    with requests.Session() as ses:
        ses.headers.update(API_KEY)
        current_case = cases.case(ses)
        current_case_lim = cases.case_limits(ses)

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
            sec_best_bid = book.get_best_bid(ses, sec)['price']
            sec_best_ask = book.get_best_ask(ses, sec)['price']

            spread = default_spread

            sec_data = securities.security_dict(ses, ticker_sym=sec)[sec]
            sec_last = sec_data.last
            position = sec_data.position

            o = orders.orders_dict(ses)

            broker.cancel_order_bulk(ses, "<","0","<","0",all_flag=1)

            max_buy_volume = limit_stock / 2 - position
            max_sell_volume = limit_stock / 2 + position

            bids = []
            asks = []

            # Buy orders            
            for i in range(-5, 0):
                curr_price = sec_last + i / 100
                vol_to_buy = math.trunc(max_buy_volume / 5)

                while vol_to_buy > 0:
                    vol = min(max_order_size, vol_to_buy)
                    bids.append((vol, curr_price))

                    vol_to_buy -= vol
            
            # Sell orders
            for i in range(1, 6):
                curr_price = sec_last + i / 100
                vol_to_sell = math.trunc(max_sell_volume / 5)

                while vol_to_sell > 0:
                    vol = min(max_order_size, vol_to_sell)
                    asks.append((vol, curr_price))

                    vol_to_sell -= vol


            print("Position: %d" % position)
            #print("Asks: " + asks)
            #print("Bids: " + bids)

            for bid in bids:
                q, p = bid
                broker.limit_order(ses, sec, 'BUY', q, p)
            
            for ask in asks:
                q, p = ask
                broker.limit_order(ses, sec, 'SELL', q, p)

            sleep(lag)

            current_case = cases.case(ses)
            tick = current_case.tick
            
            

        

if __name__ == '__main__':
    signal.signal(signal.SIGINT, signal_handler)
    main()