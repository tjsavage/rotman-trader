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

import py_vollib
from py_vollib.black_scholes.greeks.analytical import delta, gamma, theta


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

start_time = 300
stop_time = 1
lag = 1
sec = "SAC"

BASE = {
    "upper_delta_threshold": 3000,
    "lower_delta_threshold": -3000
}

class ApiException(Exception):
    pass

def signal_handler(signum, frame):
    global shutdown
    signal.signal(signal.SIGINT, signal.SIG_DFL)
    shutdown = True

def calculate_portfolio_delta(tick, securities_data, orders_data):
    S = securities_data["SAC"].last
    K = 50
    t =((300 - tick) / 15)/252
    r = 0
    sigma = .15
    
    d = delta("c", S, K, t, r, sigma)
    sac50c_position = -200
    delta_from_options = sac50c_position * d * 100

    sac_position = securities_data["SAC"].position
    delta_from_stocks = sac_position

    portfolio_delta = delta_from_options + delta_from_stocks
    return portfolio_delta


def trade(strategy, ses, tick, securities_data, orders_data):
    portfolio_delta = calculate_portfolio_delta(tick, securities_data, orders_data)

    if strategy == "base":
        if portfolio_delta > BASE['upper_delta_threshold']:
            vol = portfolio_delta - BASE['upper_delta_threshold']
            broker.market_order(ses, "SAC", "SELL", vol)
        elif portfolio_delta < BASE['lower_delta_threshold']:
            vol = BASE['lower_delta_threshold'] - portfolio_delta
            broker.market_order(ses, "SAC", "BUY", vol)
    elif strategy == "base_zero":
        if portfolio_delta > BASE['upper_delta_threshold']:
            vol = portfolio_delta
            broker.market_order(ses, "SAC", "SELL", vol)
        elif portfolio_delta < BASE['lower_delta_threshold']:
            vol = 0 - portfolio_delta
            broker.market_order(ses, "SAC", "BUY", vol)


def main():
    print("Booting up")
    while not shutdown:
        with requests.Session() as ses:
            ses.headers.update(API_KEY)
            current_case = cases.case(ses)

            strategy = "base"
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
                securities_data = securities.security_dict(ses)
                orders_data = orders.orders_dict(ses)

                trade(strategy, ses, tick, securities_data, orders_data)

                sleep(lag)
                current_case = cases.case(ses)
                tick = current_case.tick
            
            

        

if __name__ == '__main__':
    signal.signal(signal.SIGINT, signal_handler)
    main()