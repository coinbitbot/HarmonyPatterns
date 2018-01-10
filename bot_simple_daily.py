import json
import logging
import smtplib

import time

import datetime
from poloniex import Poloniex
from creds import POLONIEX_API_KEY, POLONIEX_SECRET_KEY, GMAIL_USER, GMAIL_PASSWORD


PROJECT_PATH = '/home/devuser/exchange/bot_simple_daily/'

PAIRS = [
    'USDT_ETC',
    'USDT_ETH',
    'USDT_XRP',
    'USDT_LTC',
    'USDT_XMR',
    'USDT_STR',
    'USDT_ZEC',
    'USDT_DASH',
    'USDT_REP',
    'USDT_NXT'
]

BUY_ENSURE_COEF = 1.5
CANDLE_PERIOD = 86400
CANDLES_NUM = 3
HIGHER_COEF = 1.68
LOWER_COEF = 16.8
VOL_COEF = 1.68
NUM_OF_PAIRS = 6
TRADE_AMOUNT = 12000
DEPTH_OF_SELLING_GLASS = 50
STOP_LOSS = 0.8


class Gmail(object):
    def __init__(self, email, password):
        self.email = email
        self.password = password
        self.server = 'smtp.gmail.com'
        self.port = 587
        session = smtplib.SMTP(self.server, self.port)
        session.ehlo()
        session.starttls()
        session.ehlo
        session.login(self.email, self.password)
        self.session = session

    def send_message(self, subject, body):
        """ This must be removed """
        headers = [
            "From: " + self.email,
            "Subject: " + subject,
            "To: " + self.email,
            "MIME-Version: 1.0",
            "Content-Type: text/html"]
        headers = "\r\n".join(headers)
        self.session.sendmail(
            self.email,
            self.email,
            headers + "\r\n\r\n" + body)


def create_poloniex_connection():
    polo = Poloniex()
    polo.key = POLONIEX_API_KEY
    polo.secret = POLONIEX_SECRET_KEY
    return polo


def main():
    polo = create_poloniex_connection()
    logging.basicConfig(level=logging.INFO,
                        format='%(asctime)s %(levelname)s %(message)s',
                        datefmt='%H:%M:%S',
                        filename='{}log/logger{}.log'.format(PROJECT_PATH,
                                                             time.strftime('%Y_%m_%d', datetime.datetime.now(
                                                             ).timetuple())))
    with open(PROJECT_PATH + 'bot_daily_btc_pairs.json') as data_file:
        pairs_bought = json.load(data_file)
    with open(PROJECT_PATH + 'bot_daily_btc_date.json') as data_file:
        last_bought_date = json.load(data_file)
    if pairs_bought != '':
        if pairs_bought != 'no pairs':
            balances = polo.returnBalances()
            null_balances_pairs = 0
            for pair in pairs_bought:
                altcoin_amount = float(balances[pair['name'].split('_')[-1]])
                current_buy_glass = polo.returnOrderBook(pair['name'])['bids']
                sum_previous = 0
                sell_price = 0
                for order in current_buy_glass:
                    sum_previous += float(order[1])
                    if float(sum_previous) >= BUY_ENSURE_COEF * altcoin_amount:
                        sell_price = float(order[0])
                        break
                if sell_price == 0:
                    logging.info('Sell price of {} = 0'.format(pair['name']))
                    continue
                if altcoin_amount > 0 and \
                        (time.time() - last_bought_date >= CANDLE_PERIOD or sell_price < STOP_LOSS * pair['price']):
                    polo.sell(pair['name'], sell_price, altcoin_amount)
                    logging.info(
                        'Selling {} {}. Price: {}'.format(altcoin_amount, pair['name'].split('_')[-1], sell_price))

                    gm = Gmail(GMAIL_USER, GMAIL_PASSWORD)
                    gm.send_message('SELL_DAILY', 'Selling {} {}. Price: {}. Time: {}'.format(
                        altcoin_amount, pair['name'].split('_')[-1], sell_price, datetime.datetime.now()))
                if float(polo.returnBalances()[pair['name'].split('_')[-1]]) > 0:
                    null_balances_pairs += 1

            if (time.time() - last_bought_date) >= CANDLE_PERIOD and null_balances_pairs == 0:
                with open(PROJECT_PATH + 'bot_daily_btc_pairs.json', 'w') as f:
                    json.dump('', f)
        else:
            if (time.time() - last_bought_date) >= CANDLE_PERIOD:
                with open(PROJECT_PATH + 'bot_daily_btc_pairs.json', 'w') as f:
                    json.dump('', f)
    with open(PROJECT_PATH + 'bot_daily_btc_pairs.json') as data_file:
        pairs_bought = json.load(data_file)
    if pairs_bought == '':
        pairs_info = []
        for pair in PAIRS:
            data = polo.returnChartData(
                pair, period=CANDLE_PERIOD, start=int(time.time()) - CANDLE_PERIOD * CANDLES_NUM)[:-1]
            hard_condition = True
            yest_open = float(data[1]['open'])
            yest_close = float(data[1]['close'])
            yest_high = float(data[1]['high'])
            yest_low = float(data[1]['low'])
            if yest_close > yest_open:
                close_open = yest_close - yest_open
                high_candle = yest_high - yest_close
                candle_low = yest_open - yest_low if yest_open != yest_low else 0.0001
            elif yest_close < yest_open:
                close_open = yest_open - yest_close
                high_candle = yest_high - yest_open
                candle_low = yest_close - yest_low if yest_close != yest_low else 0.0001
            else:
                close_open = 0.0001
                candle_low = yest_close - yest_low if yest_close != yest_low else 0.0001
                high_candle = yest_high - yest_open
            if high_candle / close_open > HIGHER_COEF and high_candle / candle_low > LOWER_COEF:
                hard_condition = False
            if hard_condition and float(data[1]['volume']) / float(data[0]['volume']) > VOL_COEF:
                pairs_info.append({
                    'name': pair,
                    'coef': float(data[1]['volume']) / float(data[0]['volume'])
                })
        pairs_info = sorted(pairs_info, key=lambda k: k['coef'], reverse=True)[:NUM_OF_PAIRS]
        logging.info('Number of pairs: {}'.format(len(pairs_info)))
        balances = polo.returnBalances()
        current_usdt = float(balances['USDT'])
        if len(pairs_info) > 0:
            buy_amount = TRADE_AMOUNT / len(pairs_info) if current_usdt > TRADE_AMOUNT else current_usdt / len(
                pairs_info)
            for pair_info in pairs_info:
                current_sell_glass = [
                    [float(order[0]), float(order[1]), float(order[0]) * float(order[1])]
                    for order in polo.returnOrderBook(pair_info['name'], depth=DEPTH_OF_SELLING_GLASS)['asks']
                ]
                sum_previous = 0
                order_price = 0
                for order in current_sell_glass:
                    sum_previous += order[2]
                    if sum_previous >= BUY_ENSURE_COEF * buy_amount:
                        order_price = order[0]
                        break
                if order_price:
                    polo.buy(pair_info['name'], order_price, buy_amount / order_price)
                    logging.info('Buying {} for {} USDT'.format(pair_info['name'].split('_')[-1], buy_amount))
                    pair_info['price'] = order_price

                    gm = Gmail(GMAIL_USER, GMAIL_PASSWORD)
                    gm.send_message(
                        'BUY_DAILY', 'Buying {}{} for {} USDT with rate {} at {}'.format(
                            buy_amount / order_price, pair_info['name'].split(
                                '_')[-1], buy_amount, order_price, datetime.datetime.now()))
            with open(PROJECT_PATH + 'bot_daily_btc_pairs.json', 'w') as f:
                json.dump([{'name': p['name'], 'price': p['price']} for p in pairs_info], f)
        with open(PROJECT_PATH + 'bot_daily_btc_pairs.json', 'w') as f:
            json.dump('no pairs', f)
        with open(PROJECT_PATH + 'bot_daily_btc_date.json', 'w') as f:
            json.dump(time.time(), f)


if __name__ == '__main__':
    try:
        main()
    except Exception as e:
        logging.exception('message')
