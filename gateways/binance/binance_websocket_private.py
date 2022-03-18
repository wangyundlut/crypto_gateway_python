
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
from pprint import pprint
from datetime import datetime, timedelta

HOURS8 = 8
log = logtool().addHandler()
TIMEOUT = 10

class websocket_binance():

    def __init__(self):
        # spot lever common url
        self.spotWebsocketUrl = "wss://stream.binance.com:9443/ws/"
        self.leverWebsocketUrl = "wss://stream.binance.com:9443/ws/"
        self.usdtWebsocketUrl = "wss://fstream.binance.com/ws/"
        self.coinWebsocketUrl = "wss://dstream.binance.com/ws/"
        self.account_info = {}
        # 存储所有的listenKey
        # {spot:key, usdt:key, margin:key, margin_isolated:{'BTCUSDT': key}, futures: key}
        self.listenKeys = {}
        self.listenKeysNeedUpdate = {}
        self.usdt_position_account = {}
        self.yaml_data = None
        self.conn_pool = None
        self.conn_pool_aliyun = None
        self.loop = None

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

    async def extend_listen_key(self):
        await asyncio.sleep(30 * 60)
        
        for name_redis, listenKey_dict in self.listenKeys.items():
            key = self.yaml_data[name_redis]['key']
            secret = self.yaml_data[name_redis]['secret']
            spot_api = SpotAPI(key, secret)
            usdt_api = USDTAPI(key, secret)
            futures_api = FuturesAPI(key, secret)

            result = spot_api.websocket_extend_listenKey_spot(listenKey_dict['spot'])
            # print(f"extend spot listenKey: {result}")
            result = spot_api.websocket_extend_listenKey_lever(listenKey_dict['lever'])
            # print(f"extend lever listenKey: {result}")
            result = usdt_api.websocket_extend_listenKey()
            # print(f"extend usdt listenKey: {result}")
            result = futures_api.websocket_extend_listenKey()
            # print(f"extend futures listenKey: {result}")
            
    async def spot_websocket_with_login(self, account):
        binance_account = self.yaml_data[account]['binance']
        key = self.yaml_data[binance_account]['key']
        secret = self.yaml_data[binance_account]['secret']
        name_redis = self.yaml_data[binance_account]['name_redis']
        spot_api = SpotAPI(key, secret)
        usdt_api = USDTAPI(key, secret)
        futures_api = FuturesAPI(key, secret)
        
        def getListenKey():
            result = spot_api.websocket_get_listenKey_spot()
            listenKey = result['listenKey']
            return listenKey
        
        def getAccountFromRest():
            result = spot_api.spot_get_account()
            balances = result['balances']
            account_dict = {}
            for balance in balances:
                if (float(balance['free']) != 0) or (float(balance['locked']) != 0):
                    d = {}
                    d['asset'] = balance['asset']
                    d['free'] = float(balance['free'])
                    d['locked'] = float(balance['locked'])
                    account_dict[d['asset']] = d
            rc = self.get_redis_connection()
            rc_aliyun = self.get_redis_connection_aliyun()
            d = {
                "3dots_time": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                "data": account_dict
            }
            rc.set(f"binance:{name_redis}:websocket:account_spot", json.dumps(d))
            rc_aliyun.set(f"binance:{name_redis}:websocket:account_spot", json.dumps(d))
            return account_dict
        
        while True:
            try:
                listenKey = getListenKey()
                async with websockets.connect(self.spotWebsocketUrl + listenKey) as ws:
                    account_dict = getAccountFromRest()
                    
                    log.info(f"spot_websocket_with_login {name_redis} connect.. ")
                    while True:
                        try:
                            res = await asyncio.wait_for(ws.recv(), timeout=TIMEOUT)
                        except asyncio.TimeoutError as e:
                            key = getListenKey()
                            if listenKey != key:
                                raise Exception('listenKeyExpired')
                            else:
                                continue
                        except asyncio.CancelledError as e:
                            log.error(f"spot_websocket_with_login CancelledError: {e}")
                            raise Exception('CancelledError')
                        except asyncio.IncompleteReadError as e:
                            log.error(f"spot_websocket_with_login IncompleteReadError: {e}")
                            raise Exception('IncompleteReadError')
                        except websockets.exceptions.ConnectionClosed as e:
                            log.error(f"spot_websocket_with_login ConnectionClosed : {e}")
                            raise Exception('ConnectionClosed')
                        
                        res = json.loads(res)
                        
                        if res['e'] == 'outboundAccountPosition':
                            for balance in res['B']:
                                d = {}
                                d['asset'] = balance['a']
                                d['free'] = float(balance['f'])
                                d['lock'] = float(balance['l'])
                                account_dict[d['asset']] = d
                            rc = self.get_redis_connection()
                            rc_aliyun = self.get_redis_connection_aliyun()
                            d = {
                                "3dots_time": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                                "data": account_dict
                            }
                            rc.set(f"binance:{name_redis}:websocket:account_spot", json.dumps(d))
                            rc_aliyun.set(f"binance:{name_redis}:websocket:account_spot", json.dumps(d))
                        if res['e'] == 'balanceUpdate':
                            pass
                        if res['e'] == 'executionReport':
                            pass

            except Exception as e:
                timestamp = local_time()
                log.error(timestamp + " spot_websocket_with_login 连接断开，正在重连……" + str(e))
                continue
    
    async def lever_websocket_with_login(self, account):
        binance_account = self.yaml_data[account]['binance']
        key = self.yaml_data[binance_account]['key']
        secret = self.yaml_data[binance_account]['secret']
        name_redis = self.yaml_data[binance_account]['name_redis']
        spot_api = SpotAPI(key, secret)
        usdt_api = USDTAPI(key, secret)
        futures_api = FuturesAPI(key, secret)
        
        def getListenKey():
            result = spot_api.websocket_get_listenKey_lever()
            listenKey = result['listenKey']
            return listenKey
        
        def getAccountFromRest():
            result = spot_api.level_get_account()
            userAssets = result['userAssets']
            account_dict = {}
            for userAsset in userAssets:
                if (float(userAsset['free']) != 0) or (float(userAsset['locked']) != 0):
                    d = {}
                    d['asset'] = userAsset['asset']
                    d['free'] = float(userAsset['free'])
                    d['locked'] = float(userAsset['locked'])
                    account_dict[d['asset']] = d
            rc = self.get_redis_connection()
            rc_aliyun = self.get_redis_connection_aliyun()
            d = {
                "3dots_time": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                "data": account_dict
            }
            rc.set(f"binance:{name_redis}:websocket:account_lever", json.dumps(d))
            rc_aliyun.set(f"binance:{name_redis}:websocket:account_lever", json.dumps(d))
            return account_dict
        
        while True:
            try:
                listenKey = getListenKey()
                async with websockets.connect(self.spotWebsocketUrl + listenKey) as ws:
                    account_dict = getAccountFromRest()
                    log.info(f"lever_websocket_with_login {name_redis} connect.. ")
                    while True:
                        try:
                            res = await asyncio.wait_for(ws.recv(), timeout=TIMEOUT)
                        except asyncio.TimeoutError as e:
                            key = getListenKey()
                            if listenKey != key:
                                raise Exception('listenKeyExpired')
                            else:
                                continue
                        except asyncio.CancelledError as e:
                            log.error(f"lever_websocket_with_login CancelledError: {e}")
                            raise Exception('CancelledError')
                        except asyncio.IncompleteReadError as e:
                            log.error(f"lever_websocket_with_login IncompleteReadError: {e}")
                            raise Exception('IncompleteReadError')
                        except websockets.exceptions.ConnectionClosed as e:
                            log.error(f"lever_websocket_with_login ConnectionClosed : {e}")
                            raise Exception('ConnectionClosed')
                        
                        res = json.loads(res)
                        
                        if res['e'] == 'outboundAccountPosition':
                            for balance in res['B']:
                                d = {}
                                d['asset'] = balance['a']
                                d['free'] = float(balance['f'])
                                d['lock'] = float(balance['l'])
                                account_dict[d['asset']] = d
                            rc = self.get_redis_connection()
                            rc_aliyun = self.get_redis_connection_aliyun()
                            d = {
                                "3dots_time": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                                "data": account_dict
                            }
                            rc.set(f"binance:{name_redis}:websocket:account_lever", json.dumps(d))
                            rc_aliyun.set(f"binance:{name_redis}:websocket:account_lever", json.dumps(d))
                        if res['e'] == 'balanceUpdate':
                            pass
                        if res['e'] == 'executionReport':
                            pass

            except Exception as e:
                timestamp = local_time()
                log.error(timestamp + " lever_websocket_with_login 连接断开，正在重连……" + str(e))
                continue
    
    async def lever_isolated_websocket_with_login(self, account):
        binance_account = self.yaml_data[account]['binance']
        key = self.yaml_data[binance_account]['key']
        secret = self.yaml_data[binance_account]['secret']
        name_redis = self.yaml_data[binance_account]['name_redis']

        isolated_symbols = []
        while True:
            rc = self.get_redis_connection()
            # or changed to rest
            result = rc.get(f"binance:{name_redis}:account_lever_isolated")
            result = json.loads(result)
            assets = result['data']['assets']
            for asset in assets:
                symbol = asset['symbol']
                if not (symbol in isolated_symbols):
                    task = self.lever_isolated_websocket_symbol(account, symbol)
                    self.loop.create_task(task)
                    isolated_symbols.append(symbol)
            await asyncio.sleep(60)

    async def lever_isolated_websocket_symbol(self, account, symbol):
        binance_account = self.yaml_data[account]['binance']
        key = self.yaml_data[binance_account]['key']
        secret = self.yaml_data[binance_account]['secret']
        name_redis = self.yaml_data[binance_account]['name_redis']
        spot_api = SpotAPI(key, secret)
        usdt_api = USDTAPI(key, secret)
        futures_api = FuturesAPI(key, secret)
        
        def getListenKey():
            result = spot_api.websocket_get_listenKey_lever_isolated(symbol)
            listenKey = result['listenKey']
            return listenKey
        
        def getAccountFromRest():
            result = spot_api.level_get_isolated_account(symbol)
            assets = result['assets']
            account_dict = {}
            for asset in assets:
                baseAsset = asset['baseAsset']
                quoteAsset = asset['quoteAsset']
                d = {}
                d['asset'] = baseAsset['asset']
                d['free'] = float(baseAsset['free'])
                d['locked'] = float(baseAsset['locked'])
                account_dict[d['asset']] = d
                d = {}
                d['asset'] = quoteAsset['asset']
                d['free'] = float(quoteAsset['free'])
                d['locked'] = float(quoteAsset['locked'])
                account_dict[d['asset']] = d

            rc = self.get_redis_connection()
            rc_aliyun = self.get_redis_connection_aliyun()
            d = {
                "3dots_time": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                "data": account_dict
            }
            rc.set(f"binance:{name_redis}:websocket:account_lever_isolated:{symbol}", json.dumps(d))
            rc_aliyun.set(f"binance:{name_redis}:websocket:account_lever_isolated:{symbol}", json.dumps(d))
            return account_dict
        
        while True:
            try:
                listenKey = getListenKey()
                async with websockets.connect(self.spotWebsocketUrl + listenKey) as ws:
                    account_dict = getAccountFromRest()
                    log.info(f"lever_isolated_websocket_symbol {name_redis} {symbol} connect.. ")
                    while True:
                        try:
                            res = await asyncio.wait_for(ws.recv(), timeout=TIMEOUT)
                        except asyncio.TimeoutError as e:
                            key = getListenKey()
                            if listenKey != key:
                                raise Exception('listenKeyExpired')
                            else:
                                continue
                        except asyncio.CancelledError as e:
                            log.error(f"lever_isolated_websocket_symbol CancelledError: {e}")
                            raise Exception('CancelledError')
                        except asyncio.IncompleteReadError as e:
                            log.error(f"lever_isolated_websocket_symbol IncompleteReadError: {e}")
                            raise Exception('IncompleteReadError')
                        except websockets.exceptions.ConnectionClosed as e:
                            log.error(f"lever_isolated_websocket_symbol ConnectionClosed : {e}")
                            raise Exception('ConnectionClosed')
                        
                        res = json.loads(res)
                        
                        if res['e'] == 'outboundAccountPosition':
                            for balance in res['B']:
                                d = {}
                                d['asset'] = balance['a']
                                d['free'] = float(balance['f'])
                                d['lock'] = float(balance['l'])
                                account_dict[d['asset']] = d
                            rc = self.get_redis_connection()
                            rc_aliyun = self.get_redis_connection_aliyun()
                            d = {
                                "3dots_time": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                                "data": account_dict
                            }
                            rc.set(f"binance:{name_redis}:websocket:account_lever_isolated:{symbol}", json.dumps(d))
                            rc_aliyun.set(f"binance:{name_redis}:websocket:account_lever_isolated:{symbol}", json.dumps(d))
                        if res['e'] == 'balanceUpdate':
                            pass
                        if res['e'] == 'executionReport':
                            pass

            except Exception as e:
                timestamp = local_time()
                log.error(timestamp + " lever_isolated_websocket_symbol 连接断开，正在重连……" + str(e))
                continue
    
    async def usdt_websocket_with_login(self, account):
        binance_account = self.yaml_data[account]['binance']
        key = self.yaml_data[binance_account]['key']
        secret = self.yaml_data[binance_account]['secret']
        name_redis = self.yaml_data[binance_account]['name_redis']
        spot_api = SpotAPI(key, secret)
        usdt_api = USDTAPI(key, secret)
        futures_api = FuturesAPI(key, secret)
        
        def getListenKey():
            result = usdt_api.websocket_get_listenKey()
            listenKey = result['listenKey']
            return listenKey
        
        def getAccountFromRest():
            result = usdt_api.trade_get_account()
            assets = result['assets']
            positions = result['positions']

            position_dict = {}
            for position in positions:
                if float(position['positionAmt']) != 0:
                    d = {}
                    d['symbol'] = position['symbol']
                    d['positionAmt'] = float(position['positionAmt'])
                    d['entryPrice'] = float(position['entryPrice'])
                    d['accumulatedProfit'] = 0.0
                    d['unrealizedProfit'] = float(position['unrealizedProfit'])
                    d['marginType'] = 'isolated' if position['isolated'] else 'cross'
                    d['positionInitialMargin'] = float(position['positionInitialMargin'])
                    d['positionSide'] = position['positionSide']
                    position_dict[d['symbol']] = d
            rc = self.get_redis_connection()
            rc_aliyun = self.get_redis_connection_aliyun()
            d = {
                "3dots_time": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                "data": position_dict
            }
            rc.set(f"binance:{name_redis}:websocket:position_usdt", json.dumps(d))
            rc_aliyun.set(f"binance:{name_redis}:websocket:position_usdt", json.dumps(d))
            return position_dict
        
        while True:
            try:
                listenKey = getListenKey()
                async with websockets.connect(self.usdtWebsocketUrl + listenKey) as ws:
                    position_dict = getAccountFromRest()
                    
                    log.info(f"usdt_websocket_with_login {name_redis}  connect.. ")
                    while True:
                        try:
                            res = await asyncio.wait_for(ws.recv(), timeout=TIMEOUT)
                        except asyncio.TimeoutError as e:
                            key = getListenKey()
                            if listenKey != key:
                                raise Exception('listenKeyExpired')
                            else:
                                continue
                        except asyncio.CancelledError as e:
                            log.error(f"usdt_websocket_with_login CancelledError: {e}")
                            raise Exception('CancelledError')
                        except asyncio.IncompleteReadError as e:
                            log.error(f"usdt_websocket_with_login IncompleteReadError: {e}")
                            raise Exception('IncompleteReadError')
                        except websockets.exceptions.ConnectionClosed as e:
                            log.error(f"usdt_websocket_with_login ConnectionClosed : {e}")
                            raise Exception('ConnectionClosed')

                        log.info(f"usdt_websocket_with_login: {res}")
                        res = json.loads(res)
                        log.info(f"usdt_websocket_with_login: {res}")
                        if res['e'] == 'listenKeyExpired':
                            raise Exception('listenKeyExpired')
                        # need notice
                        if res['e'] == 'MARGIN_CALL':
                            log.error(f"usdt MARGIN_CALL!!!! {res}")
                        # 
                        if res['e'] == 'ACCOUNT_UPDATE':
                            account_update = res['a']
                            balances = account_update['B']
                            positions = account_update['P']
                            for position in positions:
                                d = {}
                                d['symbol'] = position['s']
                                d['positionAmt'] = float(position['pa'])
                                d['entryPrice'] = float(position['ep'])
                                d['accumulatedProfit'] = float(position['cr'])
                                d['unrealizedProfit'] = float(position['up'])
                                d['marginType'] = position['mt']
                                d['positionInitialMargin'] = float(position['iw'])
                                d['positionSide'] = position['ps']
                                position_dict[d['symbol']] = d
                            rc = self.get_redis_connection()
                            rc_aliyun = self.get_redis_connection_aliyun()
                            d = {
                                "3dots_time": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                                "data": position_dict
                            }
                            rc.set(f"binance:{name_redis}:websocket:position_usdt", json.dumps(d))
                            rc_aliyun.set(f"binance:{name_redis}:websocket:position_usdt", json.dumps(d))
                            log.info(d)
                        if res['e'] == 'ORDER_TRADE_UPDATE':
                            pass
                        if res['e'] == 'ACCOUNT_CONFIG_UPDATE':
                            pass
                        

            except Exception as e:
                timestamp = local_time()
                log.error(timestamp + " usdt_websocket_with_login 连接断开，正在重连……" + str(e))
                continue
    

    def main_loop(self):
        loop = asyncio.get_event_loop()
        self.load_yaml()
        self.load_redis_connection_pool()
        self.loop = loop
        account_list = [
            'account_derong',
            'account_3dots',
        ]

        tasks = []
        for account in account_list:
            spot_private = self.spot_websocket_with_login(account)
            tasks.append(spot_private)
            lever_private = self.lever_websocket_with_login(account)
            tasks.append(lever_private)
            lever_private = self.lever_isolated_websocket_with_login(account)
            tasks.append(lever_private)
            usdt_private = self.usdt_websocket_with_login(account)
            tasks.append(usdt_private)
            

        tasks.append(self.extend_listen_key())
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

def round_float(num):
    return round(float(num), 8)

if __name__ == '__main__':
    
    mytest = websocket_binance()

    mytest.main_loop()