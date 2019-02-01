import signal
import requests
import time

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
spread = 0.00
buy_volume = 1000
sell_volume = 1000
start_time = 295
stop_time = 10

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
            print("Waiting start...%d" % tick)
            time.sleep(1)

        while tick < stop_time:
            print("Stopped trading...%d" % tick)
            time.sleep(1)

        while tick > stop_time and tick < start_time and not shutdown:
            sec_best_bid = book.get_best_bid(ses, sec)['price']
            sec_best_ask = book.get_best_ask(ses, sec)['price']

            o = orders.orders_dict(ses)

            if len(o) != 2 and len(o) != 0:
                print("Cancelling orders")
                broker.cancel_order_bulk(ses, "<","0","<","0",all_flag=1)
                continue
            
            if len(o) == 0:
                new_bid = sec_best_bid + spread
                new_ask = sec_best_ask - spread

                print("Order book empty")
                print("Submitting buy @ %f, sell @ %f" % (new_bid, new_ask))
                
                broker.limit_order(ses, sec, 'BUY', buy_volume, new_bid)
                broker.limit_order(ses, sec, 'SELL', sell_volume, new_ask)
            
            

        

if __name__ == '__main__':
    signal.signal(signal.SIGINT, signal_handler)
    main()