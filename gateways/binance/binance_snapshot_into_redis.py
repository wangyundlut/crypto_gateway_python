
import sys
sys.path.append('/application/3dots_exchange_api/')
sys.path.append('/application/crypto_tools/')

from binance_api.spot_api import SpotAPI
from binance_api.usdt_api import USDTAPI
from binance_api.futures_api import FuturesAPI
from Tools import logtool, dbMysql, noticeDingDing, dbMongo

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
from time import sleep
from datetime import datetime, timedelta

HOURS8 = 8
MINASSET = 0.00000001
TABLENAME = 'binance_trade'
CONS = 'binance_trade_'

log = logtool().addHandler()

class websocket_binance():

    def __init__(self):
        
        self.yaml_data = None
        self.conn_pool = None
        self.binance_tickers = {}
    
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

        redis_key = 'redis_aliyun'
        host = self.yaml_data[redis_key]['host']
        port = self.yaml_data[redis_key]['port']
        password = self.yaml_data[redis_key]['password']
        self.conn_pool_aliyun = redis.ConnectionPool(host=host, port=port, password=password, decode_responses=True, max_connections=2)   

    def get_redis_connection(self):
        rc = redis.Redis(connection_pool=self.conn_pool)
        return rc

    def get_redis_connection_aliyun(self):
        rc = redis.Redis(connection_pool=self.conn_pool_aliyun)
        return rc

    def get_binance_tickers(self):
        rc = self.get_redis_connection()
        result = rc.get(f"tickers:binance:All")
        result = json.loads(result)
        data = result['data']
        tickers = {}
        for key, value in data.items():
            tickers[key] = float(value['bidPrice'])
        tickers['USDTUSDT'] = 1
        self.binance_tickers = tickers

    async def binance_account_into_redis(self, account_all):
        binance_account = self.yaml_data[account_all]['binance']
        key = self.yaml_data[binance_account]['key']
        secret = self.yaml_data[binance_account]['secret']
        name_redis = self.yaml_data[binance_account]['name_redis']

        api_spot = SpotAPI(key, secret)
        api_futures = FuturesAPI(key, secret)
        api_usdt = USDTAPI(key, secret)

        def account_spot():
            # spot 账户净值
            def calculate_usdt_value(result):
                usdt_value = 0.0
                for balance in result['balances']:
                    asset = balance['asset']
                    free_num = round(float(balance['free']), 8)
                    lock_num = round(float(balance['locked']), 8)
                    if (free_num + lock_num) > MINASSET:
                        if "USD" in balance['asset']:
                            price = 1.0
                        else:
                            if asset + 'USDT' in self.binance_tickers.keys():
                                price = self.binance_tickers[asset + 'USDT']
                            else:
                                price = 0.0
                        usdt_value += price * (free_num + lock_num)
                return round(usdt_value, 4)

            result = api_spot.spot_get_account()
            if 'balances' in result.keys():
                d = {}
                d['3dots_time'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                d['data'] = result
                rc = self.get_redis_connection()
                rc_aliyun = self.get_redis_connection_aliyun()
                rc.set(f"binance:{name_redis}:account_spot", json.dumps(d))
                rc_aliyun.set(f"binance:{name_redis}:account_spot", json.dumps(d))
                return calculate_usdt_value(result)
            
        def account_lever():
            def calculate_usdt_value(result):
                balances = result['userAssets']
                usdt_value = 0.0
                for balance in balances:
                    asset = balance['asset']
                    netAsset = round(float(balance['netAsset']), 8)
                    if netAsset > MINASSET:
                        if "USD" in balance['asset']:
                            price = 1.0
                        else:
                            if asset + 'USDT' in self.binance_tickers.keys():
                                price = self.binance_tickers[asset + 'USDT']
                            else:
                                price = 0.0
                        usdt_value += price * netAsset
                return round(usdt_value, 4)

            # 测试level
            result = api_spot.level_get_account()
            if 'userAssets' in result.keys():
                d = {}
                d['3dots_time'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                d['data'] = result
                rc = self.get_redis_connection()
                rc_aliyun = self.get_redis_connection_aliyun()
                rc.set(f"binance:{name_redis}:account_lever", json.dumps(d))
                rc_aliyun.set(f"binance:{name_redis}:account_lever", json.dumps(d))

                return calculate_usdt_value(result)

        def account_lever_isolated():
            def calculate_usdt_value(result):
                balance = result['totalNetAssetOfBtc']
                usdt_value = float(balance) * self.binance_tickers['BTCUSDT']
                return round(usdt_value, 4)
            result = api_spot.level_get_isolated_account()
            if 'assets' in result.keys():
                d = {}
                d['3dots_time'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                d['data'] = result
                rc = self.get_redis_connection()
                rc_aliyun = self.get_redis_connection_aliyun()
                rc.set(f"binance:{name_redis}:account_lever_isolated", json.dumps(d))
                rc_aliyun.set(f"binance:{name_redis}:account_lever_isolated", json.dumps(d))
                return calculate_usdt_value(result)

        def account_usdt():
            def calculate_usdt_value(result):
                usdt_value = 0
                for result in result:
                    usdt_value += self.binance_tickers[result['asset'] + 'USDT'] * (round(float(result['balance']), 8) + round(float(result['crossUnPnl'])))
                return usdt_value
            result= api_usdt.trade_get_balance()
            d = {}
            d['3dots_time'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            usdt_dict = {}
            for li in result:
                usdt_dict[li['asset']] = li
            d['data'] = usdt_dict
            rc = self.get_redis_connection()
            rc_aliyun = self.get_redis_connection_aliyun()
            rc.set(f"binance:{name_redis}:account_usdt", json.dumps(d))
            rc_aliyun.set(f"binance:{name_redis}:account_usdt", json.dumps(d))
            return calculate_usdt_value(result)

        def account_futures():
            def calculate_usdt_value(result):
                usdt_value = 0.0
                for balance in result:
                    num = round(float(balance['balance']), 8)
                    if num > 0:
                        asset = balance['asset']
                        if "USD" in balance['asset']:
                            price = 1.0
                        else:
                            if asset + 'USDT' in self.binance_tickers.keys():
                                price = self.binance_tickers[asset + 'USDT']
                            else:
                                price = 0.0
                                
                        usdt_value += price * num
                return usdt_value

            # 测试futures
            result = api_futures.trade_get_balance()
            d = {}
            d['3dots_time'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            futures_dict = {}
            for li in result:
                futures_dict[li['asset']] = li
            d['data'] = futures_dict
            rc = self.get_redis_connection()
            rc_aliyun = self.get_redis_connection_aliyun()
            rc.set(f"binance:{name_redis}:account_futures", json.dumps(d))
            rc_aliyun.set(f"binance:{name_redis}:account_futures", json.dumps(d))
            return calculate_usdt_value(result)

        while True:
            now = datetime.now()
            second = now.second
            minute = now.minute
            if second > 2:
                await asyncio.sleep(1)
                continue
            if minute % 5:
                await asyncio.sleep(1)
                continue 

            try:
                self.get_binance_tickers()

                usdt_spot = account_spot()
                usdt_lever = account_lever()
                usdt_lever_isolated = account_lever_isolated()
                usdt_usdt = account_usdt()
                usdt_futures = account_futures()

                usdt_num = usdt_spot + usdt_lever + usdt_lever_isolated + usdt_usdt + usdt_futures
                
                d = {}
                d['3dots_time'] = datetime.now().replace(second=0).strftime('%Y-%m-%d %H:%M:%S')
                d['data'] = {'netvalue': usdt_num}
                rc = self.get_redis_connection()
                rc_aliyun = self.get_redis_connection_aliyun()
                rc.set(f"binance:{name_redis}:netvalue:USDT", json.dumps(d))
                rc_aliyun.set(f"binance:{name_redis}:netvalue:USDT", json.dumps(d))
                
            except Exception as e:
                self.load_redis_connection_pool()
                log.error(f"binance_account_into_redis error: {e}")
            await asyncio.sleep(10)

    async def binance_position_into_redis(self, account_all):
        binance_account = self.yaml_data[account_all]['binance']
        key = self.yaml_data[binance_account]['key']
        secret = self.yaml_data[binance_account]['secret']
        name_redis = self.yaml_data[binance_account]['name_redis']

        api_futures = FuturesAPI(key, secret)
        api_usdt = USDTAPI(key, secret)

        def position_usdt_info():
            result = api_usdt.trade_get_account()
            d = {}
            d['3dots_time'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            d['data'] = result
            rc = self.get_redis_connection()
            rc_aliyun = self.get_redis_connection_aliyun()
            rc.set(f"binance:{name_redis}:position_usdt_info", json.dumps(d))
            rc_aliyun.set(f"binance:{name_redis}:position_usdt_info", json.dumps(d))
                
        def position_usdt_risk():
            result = api_usdt.trade_get_positionRisk()
            d = {}
            d['3dots_time'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            risk_dict = {}
            for li in result:
                risk_dict[li['symbol']] = li
            d['data'] = risk_dict
            rc = self.get_redis_connection()
            rc_aliyun = self.get_redis_connection_aliyun()
            rc.set(f"binance:{name_redis}:position_usdt_risk", json.dumps(d))
            rc_aliyun.set(f"binance:{name_redis}:position_usdt_risk", json.dumps(d))

        def position_coin_info():
            result = api_futures.trade_get_account()
            d = {}
            d['3dots_time'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            d['data'] = result
            rc = self.get_redis_connection()
            rc_aliyun = self.get_redis_connection_aliyun()
            rc.set(f"binance:{name_redis}:position_coin_info", json.dumps(d))
            rc_aliyun.set(f"binance:{name_redis}:position_coin_info", json.dumps(d))

        def position_coin_risk():
            result = api_futures.trade_get_positionRisk()
            d = {}
            d['3dots_time'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            coin_dict = {}
            for li in result:
                coin_dict[li['symbol']] = li
            d['data'] = coin_dict
            rc = self.get_redis_connection()
            rc_aliyun = self.get_redis_connection_aliyun()
            rc.set(f"binance:{name_redis}:position_coin_risk", json.dumps(d))
            rc_aliyun.set(f"binance:{name_redis}:position_coin_risk", json.dumps(d))

        while True:
            now = datetime.now()
            second = now.second
            minute = now.minute
            if second > 2:
                await asyncio.sleep(1)
                continue
            if minute % 5:
                await asyncio.sleep(1)
                continue 
            try:
                position_usdt_info()
                position_usdt_risk()
                position_coin_info()
                position_coin_risk()

            except Exception as e:
                self.load_redis_connection_pool()
                log.error(f"binance_position_into_redis error: {e}")
            await asyncio.sleep(10)

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

def main():
    loop = asyncio.get_event_loop()
    account_list = [
        'account_3dots',
        'account_derong'
    ]
    cls = websocket_binance()
    cls.load_yaml()
    cls.load_redis_connection_pool()
    tasks = []
    
    for account in account_list:
        task = cls.binance_account_into_redis(account)
        tasks.append(task)
    
    for account in account_list:
        task = cls.binance_position_into_redis(account)
        tasks.append(task)
    
    loop.run_until_complete(asyncio.gather(*tasks))
    loop.close()


if __name__ == '__main__':
    
   main()

