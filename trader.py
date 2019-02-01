import signal
import requests

import pandas as pd
import numpy as np
import matplotlib as plt

from ritpytrading import cases
from ritpytrading import securities_book as book
from ritpytrading import submit_cancel_orders as order

API_KEY = {'X-API-Key': ''}
shutdown = False

host_url = ''
base_path = '/v1'
base_url = host_url + base_path

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
        current_case_lim = case.case_limits(ses)

if __name__ == '__main__':
    signal.signal(signal.SIGINT, signal_handler)
    main()