import sys
sys.path.append('/application/3dots_exchange_api/')
sys.path.append('/application/crypto_tools/')
from Tools import logtool
from binance_api.spot_api import SpotAPI
from binance_api.usdt_api import USDTAPI
from binance_api.futures_api import FuturesAPI
import asyncio
import websockets
import json
import requests
import dateutil.parser as dp
import hmac
import base64
import zlib
import os
import yaml
import redis
from datetime import datetime, timedelta

HOURS8 = 8
log = logtool().addHandler()

class websocket_binance():

    def __init__(self):
        self.websocketPubUrl = "wss://stream.binance.com:9443/stream?streams="
        
        self.yaml_data = None
        self.conn_pool = None
    
    def load_yaml(self):
        yml_path = os.path.join("/","application", "account.yml")
        f = open(yml_path)
        yaml_file = yaml.full_load(f)
        self.yaml_data = yaml_file

    def load_redis_connection_pool(self):
        redis_key = 'redis_pro2'
        host = self.yaml_data[redis_key]['host']
        port = self.yaml_data[redis_key]['port']
        password = self.yaml_data[redis_key]['password']
        self.conn_pool = redis.ConnectionPool(host=host, port=port, password=password, decode_responses=True, max_connections=2)   

    def get_redis_connection(self):
        rc = redis.Redis(connection_pool=self.conn_pool)
        return rc

    def binance_info_into_redis(self):
        spot_api = SpotAPI()
        usdt_api = USDTAPI()
        futures_api = FuturesAPI()
        rc = self.get_redis_connection()
        
        result = spot_api.market_exchangeInfo()
        symbols = result['symbols']
        d = {}
        for symbol in symbols:
            d[symbol['symbol']] = symbol
        rc.set(f"binance:info:SPOT", json.dumps(d))

        result = usdt_api.market_get_exchangeInfo()
        symbols = result['symbols']
        d = {}
        for symbol in symbols:
            d[symbol['symbol']] = symbol
        rc.set(f"binance:info:USDT", json.dumps(d))
    
        result = futures_api.market_exchangeInfo()
        symbols = result['symbols']
        d = {}
        for symbol in symbols:
            d[symbol['symbol']] = symbol
        rc.set(f"binance:info:FUTURES", json.dumps(d))
        rc.close()
        
    def get_binance_tickers_all(self):
        spot_api = SpotAPI()
        usdt_api = USDTAPI()
        futures_api = FuturesAPI()
        tickers_all = {}
        try:
            tickers_spot = spot_api.market_bookTicker()
            for ticker in tickers_spot:
                symbol = ticker['symbol']
                if '123456' in ticker['symbol']:
                    continue
                tickers_all[symbol] = ticker
            tickers_swap_coin = futures_api.market_bookTicker()
            for ticker in tickers_swap_coin:
                symbol = ticker['symbol']
                tickers_all[symbol] = ticker
            tickers_swap_usdt = usdt_api.market_bookTicker()
            for ticker in tickers_swap_usdt:
                ticker['symbol'] = ticker['symbol'] + 'SWAP'
                symbol = ticker['symbol']
                tickers_all[symbol] = ticker
        except Exception as e:
            log.error(f"get binance tickers all error: {e}")
        return tickers_all

    async def binance_tickers_all_into_redis(self):
        while True:
            try:
                tickers_all = self.get_binance_tickers_all()
                if tickers_all:
                    d = {
                        '3dots_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                        'data': tickers_all
                    }
                    rc = self.get_redis_connection()
                    rc.set(f"tickers:binance:All", json.dumps(d))
                    rc.close()
            except Exception as e:
                log.error(f"binance tickers all into redis error: {e}")
                self.load_redis_connection_pool()
            await asyncio.sleep(2)

    async def market_without_login(self, symbols):
        # 选取
        channels = {"method": "SUBSCRIBE","params":[],"id": 1}
        params = []
        for symbol in symbols:
            params.append(symbol.lower() + '@bookTicker')

        channels['params'] = params
        
        while True:
            try:
                async with websockets.connect(self.websocketPubUrl) as ws:
                    await ws.send(json.dumps(channels))
                    while True:
                        try:
                            res = await asyncio.wait_for(ws.recv(), timeout=25)
                        except (asyncio.TimeoutError, websockets.exceptions.ConnectionClosed) as e:
                            try:
                                await ws.send('pong')
                                res = await asyncio.wait_for(ws.recv(), timeout=25)
                                continue
                            except Exception as e:
                                # timestamp = local_time()
                                # print(timestamp + "正在重连……"+ str(e))
                                print("正在重连……"+ str(e))
                                print(e)
                                break
                        
                        res = json.loads(res)
                        if 'result' in res.keys():
                            print(res)
                            continue
                        
                        if 'stream' in res.keys():
                            if 'bookTicker' in res['stream']:
                                symbol = res['stream'].split('@')[0].upper()
                                rc = self.get_redis_connection()
                                data = res['data']
                                data['3dots_time'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                                rc.set(f"tickers:binance:{symbol}", json.dumps(res['data']))
                                rc.close()
                                continue
                        print(res)

            except Exception as e:
                timestamp = local_time()
                print(timestamp + " binance_tickers_into_redis 连接断开，正在重连1……" + str(e))
                print(e)
                continue

    def main_loop(self, symbols):
        loop = asyncio.get_event_loop()
        self.load_yaml()
        self.load_redis_connection_pool()
        self.binance_info_into_redis()
        
        tasks = []
        task_market = self.market_without_login(symbols)
        tasks.append(task_market)
        task_ticker_all = self.binance_tickers_all_into_redis()
        tasks.append(task_ticker_all)

        loop.run_until_complete(asyncio.gather(*tasks))

        loop.close()

def okex_timestr():
    # 获取okex的时间数据格式 ISO 8601格式
    now = datetime.utcnow()
    t = now.isoformat("T", "milliseconds") + "Z"
    return t

def okex_timestamp():
    # OKEX的时间戳是  +8 也就是 香港/新加坡时间 北京时间
    now = int((datetime.utcnow() + timedelta(hours=HOURS8)).timestamp() * 1000)
    return now

def exch_to_local(time_exchange):
    # 交易所的时间 -> 本地的时间 str -> datetime
    # time_local = datetime.utcfromtimestamp(int(time_exchange / 1000))
    time_local = datetime.utcfromtimestamp(time_exchange / 1000)
    time_local = time_local.replace(tzinfo=None)
    time_local = time_local + timedelta(hours=HOURS8)
    # time_local = CHINA_TZ.localize(time_local)
    return time_local

def local_to_exch(time_local):
    # 本地的时间 ->交易所的时间 datetime -> str
    time_utc = time_local - timedelta(hours=HOURS8)
    stamp_utc = int(time_utc.timestamp() * 1000)
    time_exchange = stamp_utc + HOURS8 * 3600 * 1000
    return time_exchange

def local_timestamp(time_local):
    # 本地时间 -> 数据库时间 datetime ->
    return time_local.strftime("%Y-%m-%d %H:%M:%S")

def local_time():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

if __name__ == '__main__':
    
    mytest = websocket_binance()
    symbols = ['BTCUSDT']
    mytest.main_loop(symbols)