
import asyncio
import aiohttp
from sympy import N
import websockets
import json
import yaml
from pprint import pprint
from datetime import datetime, timedelta
from decimal import Decimal
from copy import deepcopy
import logging
from typing import Dict, List

from crypto_gateway_python.utilities.utility_time import dt_epoch_to_china_str, dt_epoch_utz_now
from crypto_rest_python.binance.sync_rest.spot_api import SpotAPI as sync_spot
from crypto_rest_python.binance.async_rest.async_spot import asyncBinanceSpot as async_spot
from crypto_rest_python.binance.async_rest.client import RestClient, Response, Request
from crypto_gateway_python.data_structure.base_gateway import baseGateway
from crypto_gateway_python.data_structure.base_data_struct import(
    depthData,
    accountData,
    fillData,
    orderStateData,
    orderTypeData,
    positionData,
    orderData,
    sendReturnData,
    orderChannelData,
    instTypeData,
    instInfoData,
    orderSideData,
    contractTypeData
)
from crypto_gateway_python.data_structure.base_error import (
    cancelOrderError,
    orderError,
    amendOrderError
)

from crypto_gateway_python.data_structure.base_data_struct import (
    depthData, 
    orderSendData, 
    cancelOrderSendData,
    amendOrderSendData,
    )

HOURS8 = 8
TIMEOUT = 10

class binanceGateway(baseGateway):
    # loop for async rest
    def __init__(self, gateway_name='', loop: asyncio.AbstractEventLoop = None) -> None:
        super(binanceGateway, self).__init__(gateway_name)
        
        ##################### listener #####################
        self.listener_depth = None
        self.listener_account = None
        self.listener_position = None
        self.listener_order = None
        self.listener_fill = None
        self.listener_send = None
        self.listener_ws_break = None
        ##################### listener #####################
        self.exchange_name = "binance"
        self.rate_filters = {}
        self.instrument_info : dict[str, instInfoData]= {}
        self.inst_id_set = set()
        # spot lever common url
        self.spotWebsocketUrl = "wss://stream.binance.com:9443/ws/"
        self.leverWebsocketUrl = "wss://stream.binance.com:9443/ws/"
        self.usdtWebsocketUrl = "wss://fstream.binance.com/ws/"
        self.coinWebsocketUrl = "wss://dstream.binance.com/ws/"
        self.account_info = {}
        self.log: logging.Logger = None
        # 存储所有的listenKey
        # {spot:key, usdt:key, margin:key, margin_isolated:{'BTCUSDT': key}, futures: key}
        self.listenKeys = {}
        self.listenKeysNeedUpdate = {}
        self.usdt_position_account = {}
        self.yaml_data = None
        self.conn_pool = None
        self.conn_pool_aliyun = None

        self.loop:asyncio.AbstractEventLoop = None
        self.session: aiohttp.ClientSession = None
        
        self.spot_public_ready = False
        self.spot_private_ready = False

    ##################load rest##############################
    def add_config_account(self, config):
        # config -> load rest
        assert config['exchange'] == self.exchange_name
        self.apiKey = config['apiKey']
        self.secretKey = config['secretKey']
        # self.passPhrase = config['passPhrase']
        self.account_name = config['account_name']
        self.isTest = config['isTest']
        if self.isTest:
            # self.websocketPubUrl = WS_PUB_URL_SIMULATION
            # self.websocketPriUrl = WS_PRI_URL_SIMULATION
            pass
        
        self.sync_spot = sync_spot(self.apiKey, self.secretKey)
        # self.async_spot = async_spot(self.apiKey, self.secretKey, self.loop, self.session)
        self.async_spot = async_spot(self.apiKey, self.secretKey)
        self.async_spot.start()

        self.load_exchange_info()
    
    def load_exchange_info(self):
        # load spot exchange info
        result = self.sync_spot.market_exchangeInfo()
        for rateLimit in result["rateLimits"]:
            if rateLimit["rateLimitType"] == "REQUEST_WEIGHT":
                self.rate_filters["REQUEST_WEIGHT"] = rateLimit
            if rateLimit["rateLimitType"] == "ORDERS" and rateLimit["interval"] == "SECOND":
                self.rate_filters["ORDERS_SECOND"] = rateLimit
            if rateLimit["rateLimitType"] == "ORDERS" and rateLimit["interval"] == "DAY":
                self.rate_filters["ORDERS_DAY"] = rateLimit
            if rateLimit["rateLimitType"] == "RAW_REQUESTS":
                self.rate_filters["RAW_REQUESTS"] = rateLimit

        for data in result["symbols"]:
            self.exchange_info_transfer(data)

    def exchange_info_transfer(self, data) -> instInfoData:
        info = instInfoData()
        info.exchange = self.exchange_name
        

        info.base_ccy = data["baseAsset"].lower()
        info.quote_ccy = data["quoteAsset"].lower()

        info.underlying = ""
        filters_ = data["filters"]

        info.con_val = Decimal("1")

        for filterType in filters_:
            if filterType["filterType"] == "PRICE_FILTER":
                info.price_tick = Decimal(filterType["minPrice"])
            if filterType["filterType"] == "LOT_SIZE":
                info.min_order_sz = Decimal(filterType["minQty"])

        for inst_type in [instTypeData.SPOT, instTypeData.MARGINCROSS, instTypeData.MARGINISOLATED]:
            info_ = deepcopy(info)
            info_.inst_type = inst_type
            info_.inst_id = data["symbol"]
            info_.inst_id_local = self.get_inst_id_local(info_.inst_id, inst_type)
            self.instrument_info[info_.inst_id_local] = info_
        
    def get_inst_id_local(self, inst_id: str, inst_type: str = ""):
        # for all products can be distinct by inst_id
        return f"{self.exchange_name}_{inst_type.lower()}_{inst_id.lower()}"
    
    def get_ccy_local(self, ccy: str, inst_type: str = ""):
        # for all products can be distinct by inst_id
        return f"{self.exchange_name}_{inst_type.lower()}_{ccy.lower()}"

    def get_account(self, inst_id: str, inst_type: str, ccy: str) -> accountData:
        acc = accountData()
        acc.gateway_name = self.gateway_name
        acc.account_name = self.account_name
        acc.exchange = self.exchange_name
        if inst_type == instTypeData.SPOT:

            result = self.sync_spot.spot_get_account()
            balances = result['balances']
            inst_id_local = self.get_inst_id_local(inst_id, inst_type)
            info = self.instrument_info[inst_id_local]

            for balance in balances:
                if balance["asset"].lower() == ccy.lower():
                    
                    acc.ccy = balance["asset"]
                    acc.ccy_local = self.get_ccy_local(balance["asset"], instTypeData.SPOT)
                    
                    acc.asset = Decimal(balance["free"]) + Decimal(balance["locked"])
                    acc.debt = Decimal(0)
                    acc.equity = acc.asset

                    acc.frozen = Decimal(balance["locked"])
                    acc.interest = Decimal(0)

                    acc.account_risk = Decimal(0)

                    acc.update_time_epoch = Decimal(dt_epoch_utz_now())
                    acc.update_time_china = dt_epoch_to_china_str(acc.update_time_epoch)
                    return acc
        elif inst_type == instTypeData.MARGINCROSS:
            result = self.sync_spot.lever_get_account()
            balances  = result['userAssets']
            inst_id_local = self.get_inst_id_local(inst_id, instTypeData.MARGINCROSS)
            info = self.instrument_info[inst_id_local]
            for balance in balances:
                if balance["asset"].lower() == ccy.lower():
                    acc.ccy = balance["asset"]
                    acc.ccy_local = self.get_ccy_local(balance["asset"], instTypeData.MARGINCROSS)

                    acc.asset = Decimal(balance["borrowed"]) + Decimal(balance["netAsset"])
                    acc.debt = Decimal(balance["borrowed"])
                    acc.equity = Decimal(balance["netAsset"])

                    acc.frozen = Decimal(balance["locked"])
                    acc.interest = Decimal(balance["interest"])

                    acc.account_risk = 1 / Decimal(result["marginLevel"])

                    acc.update_time_epoch = Decimal(dt_epoch_utz_now())
                    acc.update_time_china = dt_epoch_to_china_str(acc.update_time_epoch)
                    return acc
    
    def get_info(self, inst_id: str, inst_type: str=""):
        inst_id_local = self.get_inst_id_local(inst_id, inst_type)
        return self.instrument_info[inst_id_local]

    ##################load rest##############################

    ##################strategy engine add##############################
    def add_inst_id_needed(self, inst_id: str, inst_type: str=""):
        # for okx, all inst_id is upper
        inst_id_local = self.get_inst_id_local(inst_id, inst_type)
        self.inst_id_set.add(inst_id_local)

    def add_log(self, log: logging.Logger):
        self.log = log
    
    def log_record(self, msg):
        if self.log:
            self.log.info(f"{self.exchange_name}. {self.gateway_name}. : {msg}")
        else:
            print(f"{datetime.now()} {self.exchange_name}. {self.gateway_name}: {msg}")
    ##################strategy engine add##############################

    def listen_key_call_back(self, request: Request):
        return

    async def extend_listen_key(self):
        spot_api = self.async_spot
        while True:
            await asyncio.sleep(60)
            try:
                # usdt_api = USDTAPI(key, secret)
                # futures_api = FuturesAPI(key, secret)
                
                for instType, listenKey in self.listenKeys.items():
                    spot_api.websocket_get_listenKey_spot(cb=self.listen_key_call_back)
                    spot_api.websocket_get_listenKey_lever(cb=self.listen_key_call_back)
                    
                    # # print(f"extend spot listenKey: {result}")
                    # result = spot_api.websocket_extend_listenKey_lever(listenKey_dict['lever'])
                    # # print(f"extend lever listenKey: {result}")
                    # result = usdt_api.websocket_extend_listenKey()
                    # # print(f"extend usdt listenKey: {result}")
                    # result = futures_api.websocket_extend_listenKey()
                    # # print(f"extend futures listenKey: {result}")
            except Exception as e:
                self.log_record(f" extend listen key error: {e}")

    def start_coroutine_market(self):
        asyncio.run_coroutine_threadsafe(self.spot_market(), self.loop)
        
    def start_coroutine_trade(self):
        asyncio.run_coroutine_threadsafe(self.extend_listen_key(), self.loop)
        spot_start = False
        scross_start = False
        for inst_id_local in self.inst_id_set:
            info = self.instrument_info[inst_id_local]
            if info.inst_type == instTypeData.SPOT and spot_start == False:
                asyncio.run_coroutine_threadsafe(self.spot_websocket_with_login(), self.loop)
                spot_start = True
            if info.inst_type == instTypeData.MARGINCROSS and scross_start == False:
                asyncio.run_coroutine_threadsafe(self.cross_websocket_with_login(), self.loop)
                scross_start = True
                
    async def spot_market(self):
        url = "wss://stream.binance.com:9443/stream?streams="
        """
         /stream?streams=<streamName1>/<streamName2>/<streamName3>
        """
        # url += "/stream?streams=ltcusdt@bookTicker/ltcbtc@bookTicker"
        book_url = ""
        for inst_id_local in self.inst_id_set:
            info = self.instrument_info[inst_id_local]
            book_url += f"{info.inst_id.lower()}@bookTicker/"
        book_url = book_url[:-1]

        while True:
            try:

                async with websockets.connect(url + book_url) as self.ws_public:
                    
                    while True:
                        try:
                            res = await asyncio.wait_for(self.ws_public.recv(), timeout=60)
                        except (asyncio.TimeoutError, websockets.exceptions.ConnectionClosed) as e:
                            print(f"{datetime.now()} {self.exchange_name} market channel not receive for 60 seconds, 正在重连…… error: {e}")
                            raise Exception(f"long time no receive")

                        res = json.loads(res)
                        if 'stream' in res:
                            if not self.spot_public_ready:
                                self.spot_public_ready = True
                            stream = res['stream']
                            if 'bookTicker' in stream:
                                data = res['data']
                                depth = depthData()
                                depth.gateway_name = self.gateway_name
                                depth.exchange = self.exchange_name
                                depth.inst_type = "spot"
                                depth.inst_id = data['s']
                                depth.inst_id_local = self.get_inst_id_local(depth.inst_id, depth.inst_type)
                                depth.time_epoch = dt_epoch_utz_now()
                                depth.time_china = dt_epoch_to_china_str(depth.time_epoch)
                                depth.bid_price_1 = Decimal(data['b'])
                                depth.bid_volume_1 = Decimal(data['B'])
                                depth.ask_price_1 = Decimal(data['a'])
                                depth.ask_volume_1 = Decimal(data['A'])
                                depth.asks_list = []
                                depth.bids_list = []
                                if self.listener_depth:
                                    await self.listener_depth(depth)

                                # print(f"depth: {depth.ask_price_1} {depth.bid_price_1}")
                            else:
                                print(f"stream {stream}")
                        else:
                            print(res)
                        
            except Exception as e:

                if 'cannot schedule new FUTURES after shutdown' in str(e):
                    pass
                elif 'no running event loop' in str(e):
                    pass
                else:
                    self.log_record(f"{self.exchange_name}, {self.gateway_name}, subscribe_market_data error: {e}")
                # print(timestamp + f" subscribe_market_data error: {e}")
                self.spot_public_ready = False
                continue

    async def spot_websocket_with_login(self):
        # binance_account = self.yaml_data[account]['binance']
        # key = self.yaml_data[binance_account]['key']
        # secret = self.yaml_data[binance_account]['secret']
        # name_redis = self.yaml_data[binance_account]['name_redis']
        # spot_api = SpotAPI(key, secret)
        # usdt_api = USDTAPI(key, secret)
        # futures_api = FuturesAPI(key, secret)
        
        def getListenKey():
            result = self.sync_spot.websocket_get_listenKey_spot()
            listenKey = result['listenKey']
            return listenKey
        
        def getAccountFromRest():
            result = self.sync_spot.spot_get_account()
            balances = result['balances']
            account_dict = {}
            for balance in balances:
                if (float(balance['free']) != 0) or (float(balance['locked']) != 0):
                    acc = accountData()
                    acc.gateway_name = self.gateway_name
                    acc.account_name = self.account_name
                    acc.exchange = self.exchange_name
                    acc.ccy = balance["asset"]
                    acc.ccy_local = self.get_ccy_local(balance["asset"], "spot")
                    
                    acc.asset = Decimal(balance["free"]) + Decimal(balance["locked"])
                    acc.debt = Decimal(0)
                    acc.equity = Decimal(balance["free"]) + Decimal(balance["locked"])
                    
                    acc.frozen = Decimal(balance["locked"])
                    acc.interest = Decimal(0)

                    acc.account_risk = Decimal(0)

                    acc.update_time_epoch = Decimal(dt_epoch_utz_now())
                    acc.update_time_china = dt_epoch_to_china_str(acc.update_time_epoch)

                    # print(acc)

            return account_dict
        
        while True:
            try:
                listenKey = getListenKey()
                self.listenKeys["spot"] = listenKey

                async with websockets.connect(self.spotWebsocketUrl + listenKey) as ws:
                    account_dict = getAccountFromRest()
                    
                    self.log_record(f"spot_websocket_with_login connect.. ")
                    if not self.spot_private_ready:
                        self.spot_private_ready = True
                        
                    while True:
                        try:
                            res = await asyncio.wait_for(ws.recv(), timeout=600)
                        except asyncio.TimeoutError as e:
                            if listenKey != getListenKey():
                                raise Exception('listenKeyExpired')
                            else:
                                continue
                        except asyncio.CancelledError as e:
                            self.log_record(f"spot_websocket_with_login CancelledError: {e}")
                            raise Exception('CancelledError')
                        except asyncio.IncompleteReadError as e:
                            self.log_record(f"spot_websocket_with_login IncompleteReadError: {e}")
                            raise Exception('IncompleteReadError')
                        except websockets.exceptions.ConnectionClosed as e:
                            self.log_record(f"spot_websocket_with_login ConnectionClosed : {e}")
                            raise Exception('ConnectionClosed')
                        
                        res = json.loads(res)

                        if res['e'] == 'outboundAccountPosition':
                            # print(res["e"])
                            # print(res)
                            for balance in res["B"]:
                                acc = accountData()
                                acc.gateway_name = self.gateway_name
                                acc.account_name = self.account_name
                                acc.exchange = self.exchange_name
                                acc.ccy = balance["a"]
                                acc.ccy_local = self.get_ccy_local(balance["a"], "spot")
                                
                                acc.asset = Decimal(balance["f"]) + Decimal(balance["l"])
                                acc.debt = Decimal(0)
                                acc.equity = Decimal(balance["f"]) + Decimal(balance["l"])
                                
                                acc.frozen = Decimal(balance["l"])
                                acc.interest = Decimal(0)
                                acc.account_risk = Decimal(0)

                                acc.update_time_epoch = Decimal(res["u"])
                                acc.update_time_china = dt_epoch_to_china_str(acc.update_time_epoch)
                                if self.listener_account:
                                    await self.listener_account(acc)

                        elif res['e'] == 'balanceUpdate':
                            print(res["e"])
                            print(res)
                        elif res['e'] == 'executionReport':
                            inst_id = res["s"]
                            inst_id_local = self.get_inst_id_local(inst_id, "spot")
                            info = self.instrument_info[inst_id_local]
                            ZERODECIMAL = Decimal(0)
                            order_data = orderData()

                            order_data.gateway_name = self.gateway_name
                            order_data.account_name = self.account_name
                            order_data.exchange = self.exchange_name
                            order_data.inst_type = info.inst_type
                            order_data.inst_id = info.inst_id
                            order_data.inst_id_local = inst_id_local

                            order_data.ord_id = str(res['i'])
                            order_data.cl_ord_id = res['c']
                            
                            if res["X"] == "NEW":
                                order_data.state = orderStateData.SENDSUCCEED
                            elif res["X"] == "PARTIALLY_FILLED":
                                order_data.state = orderStateData.PARTIALFILLED
                            elif res["X"] == "FILLED":
                                order_data.state = orderStateData.FILLED
                            elif res["X"] == "CANCELED":
                                order_data.state = orderStateData.CANCELSUCCEED
                            elif res["X"] == "REJECTED":
                                order_data.state = orderStateData.SENDFAILED
                            elif res["X"] == "EXPIRED":
                                order_data.state = orderStateData.CANCELSUCCEED
                            
                            order_data.px = ZERODECIMAL if not res['p'] else Decimal(res['p'])
                            order_data.sz = ZERODECIMAL if not res['q'] else Decimal(res['q'])
                            order_data.pnl = ZERODECIMAL 
                            if res["o"] == "LIMIT":
                                order_data.ord_type = orderTypeData.LIMIT
                            elif res["o"] == "MARKET":
                                order_data.ord_type = orderTypeData.MARKET
                            elif res["o"] == "LIMIT_MAKER":
                                order_data.ord_type = orderTypeData.POSTONLY
                            elif res["f"] == "IOC":
                                order_data.ord_type = orderTypeData.IOC
                            elif res["f"] == "FOK":
                                order_data.ord_type = orderTypeData.FOK
                            order_data.side = res['S'].lower()

                            order_data.fill_px = ZERODECIMAL if not res['L'] else Decimal(res['L'])
                            order_data.fill_sz = ZERODECIMAL if not res['l'] else Decimal(res['l'])
                            order_data.acc_fill_sz = ZERODECIMAL if not res['z'] else Decimal(res['z'])
                            if order_data.acc_fill_sz > 0:
                                order_data.avg_px = Decimal(res["Z"]) / Decimal(res["z"])
                            else:
                                order_data.avg_px = ZERODECIMAL    

                            if Decimal(res["n"]) >= 0:
                                order_data.fee_ccy = res['N'].lower() if res['N'] else ""
                                order_data.fee = ZERODECIMAL if not res['n'] else -Decimal(res['n'])
                                order_data.rebate_ccy = ""
                                order_data.rebate = ZERODECIMAL 
                            else:
                                order_data.fee_ccy = ""
                                order_data.fee = ZERODECIMAL
                                order_data.rebate_ccy = res['N'].lower() if res['N'] else ""
                                order_data.rebate = ZERODECIMAL if not res['n'] else -Decimal(res['n'])

                            order_data.update_time_epoch = Decimal(res['E'])
                            order_data.update_time_china = dt_epoch_to_china_str(res['E'])
                            order_data.create_time_epoch = Decimal(res['O'])
                            order_data.create_time_china = dt_epoch_to_china_str(res['O'])
                                
                            if res["x"] == "TRADE":
                                fill = fillData()

                                fill.gateway_name = self.gateway_name
                                fill.account_name = self.account_name
                                fill.exchange = self.exchange_name
                                fill.inst_type = info.inst_type
                                fill.inst_id = info.inst_id
                                fill.inst_id_local = inst_id_local

                                fill.ord_type = order_data.ord_type
                                fill.side = order_data.side
                                fill.ord_id = order_data.ord_id
                                fill.cl_ord_id = order_data.cl_ord_id
                                fill.bill_id = ""
                                fill.trade_id = str(res["t"])
                                fill.tag = ""
                                fill.taker_or_maker = "maker" if res['m'] else "taker"
                                fill.fill_px = order_data.fill_px
                                fill.fill_sz = order_data.fill_sz
                                fill.fee_ccy = order_data.fee_ccy
                                fill.fee = order_data.fee
                                fill.rebate_ccy = order_data.rebate_ccy
                                fill.rebate = order_data.rebate
                                fill.time_epoch = order_data.update_time_epoch
                                fill.time_china = order_data.update_time_china
                                if self.listener_fill:
                                    await self.listener_fill(fill)
                                    
                            if self.listener_order:
                                await self.listener_order(order_data)
                                
                        else:
                            print(res["e"])
                            print(res)

            except Exception as e:
                self.spot_private_ready = False
                timestamp = local_time()
                self.log_record(timestamp + " spot_websocket_with_login 连接断开，正在重连……" + str(e))
                continue
    
    async def cross_websocket_with_login(self):
        # binance_account = self.yaml_data[account]['binance']
        # key = self.yaml_data[binance_account]['key']
        # secret = self.yaml_data[binance_account]['secret']
        # name_redis = self.yaml_data[binance_account]['name_redis']
        # spot_api = SpotAPI(key, secret)
        # usdt_api = USDTAPI(key, secret)
        # futures_api = FuturesAPI(key, secret)
        
        def getListenKey():
            result = self.sync_spot.websocket_get_listenKey_lever()
            listenKey = result['listenKey']
            return listenKey
        
        def getAccountFromRest():
            result = self.sync_spot.lever_get_account()
            balances  = result['userAssets']
            inst_id_local = self.get_inst_id_local(inst_id, instTypeData.MARGINCROSS)
            info = self.instrument_info[inst_id_local]
            for balance in balances:
                if Decimal(balance["netAsset"]) != Decimal(0):
                    acc.ccy = balance["asset"]
                    acc.ccy_local = self.get_ccy_local(balance["asset"], instTypeData.MARGINCROSS)

                    acc.asset = Decimal(balance["borrowed"]) + Decimal(balance["netAsset"])
                    acc.debt = Decimal(balance["borrowed"])
                    acc.equity = Decimal(balance["netAsset"])

                    acc.frozen = Decimal(balance["locked"])
                    acc.interest = Decimal(balance["interest"])

                    acc.account_risk = 1 / Decimal(result["marginLevel"])

                    acc.update_time_epoch = Decimal(dt_epoch_utz_now())
                    acc.update_time_china = dt_epoch_to_china_str(acc.update_time_epoch)
            return acc
        
        while True:
            try:
                listenKey = getListenKey()
                self.listenKeys["cross"] = listenKey

                async with websockets.connect(self.spotWebsocketUrl + listenKey) as ws:
                    # account_dict = getAccountFromRest()
                    
                    self.log_record(f"cross_websocket_with_login connect.. ")
                    if not self.spot_private_ready:
                        self.spot_private_ready = True
                        
                    while True:
                        try:
                            res = await asyncio.wait_for(ws.recv(), timeout=600)
                        except asyncio.TimeoutError as e:
                            if listenKey != getListenKey():
                                raise Exception('listenKeyExpired')
                            else:
                                continue
                        except asyncio.CancelledError as e:
                            self.log_record(f"spot_websocket_with_login CancelledError: {e}")
                            raise Exception('CancelledError')
                        except asyncio.IncompleteReadError as e:
                            self.log_record(f"spot_websocket_with_login IncompleteReadError: {e}")
                            raise Exception('IncompleteReadError')
                        except websockets.exceptions.ConnectionClosed as e:
                            self.log_record(f"spot_websocket_with_login ConnectionClosed : {e}")
                            raise Exception('ConnectionClosed')
                        
                        res = json.loads(res)

                        if res['e'] == 'outboundAccountPosition':
                            # print(res["e"])
                            # print(res)
                            for balance in res["B"]:
                                acc = accountData()
                                acc.gateway_name = self.gateway_name
                                acc.account_name = self.account_name
                                acc.exchange = self.exchange_name
                                acc.ccy = balance["a"]
                                acc.ccy_local = self.get_ccy_local(balance["a"], instTypeData.MARGINCROSS)
                                
                                acc.asset = Decimal(balance["f"]) + Decimal(balance["l"])
                                acc.debt = Decimal(0)
                                acc.equity = Decimal(balance["f"]) + Decimal(balance["l"])
                                
                                acc.frozen = Decimal(balance["l"])
                                acc.interest = Decimal(0)
                                acc.account_risk = Decimal(0)

                                acc.update_time_epoch = Decimal(res["u"])
                                acc.update_time_china = dt_epoch_to_china_str(acc.update_time_epoch)
                                if self.listener_account:
                                    await self.listener_account(acc)

                        elif res['e'] == 'balanceUpdate':
                            print(res["e"])
                            print(res)
                        elif res['e'] == 'executionReport':
                            inst_id = res["s"]
                            inst_id_local = self.get_inst_id_local(inst_id, instTypeData.MARGINCROSS)
                            info = self.instrument_info[inst_id_local]
                            ZERODECIMAL = Decimal(0)
                            order_data = orderData()

                            order_data.gateway_name = self.gateway_name
                            order_data.account_name = self.account_name
                            order_data.exchange = self.exchange_name
                            order_data.inst_type = info.inst_type
                            order_data.inst_id = info.inst_id
                            order_data.inst_id_local = inst_id_local

                            order_data.ord_id = str(res['i'])
                            order_data.cl_ord_id = res['c']
                            
                            if res["X"] == "NEW":
                                order_data.state = orderStateData.SENDSUCCEED
                            elif res["X"] == "PARTIALLY_FILLED":
                                order_data.state = orderStateData.PARTIALFILLED
                            elif res["X"] == "FILLED":
                                order_data.state = orderStateData.FILLED
                            elif res["X"] == "CANCELED":
                                order_data.state = orderStateData.CANCELSUCCEED
                            elif res["X"] == "REJECTED":
                                order_data.state = orderStateData.SENDFAILED
                            elif res["X"] == "EXPIRED":
                                order_data.state = orderStateData.CANCELSUCCEED
                            
                            order_data.px = ZERODECIMAL if not res['p'] else Decimal(res['p'])
                            order_data.sz = ZERODECIMAL if not res['q'] else Decimal(res['q'])
                            order_data.pnl = ZERODECIMAL 
                            if res["o"] == "LIMIT":
                                order_data.ord_type = orderTypeData.LIMIT
                            elif res["o"] == "MARKET":
                                order_data.ord_type = orderTypeData.MARKET
                            elif res["o"] == "LIMIT_MAKER":
                                order_data.ord_type = orderTypeData.POSTONLY
                            elif res["f"] == "IOC":
                                order_data.ord_type = orderTypeData.IOC
                            elif res["f"] == "FOK":
                                order_data.ord_type = orderTypeData.FOK
                            order_data.side = res['S'].lower()

                            order_data.fill_px = ZERODECIMAL if not res['L'] else Decimal(res['L'])
                            order_data.fill_sz = ZERODECIMAL if not res['l'] else Decimal(res['l'])
                            order_data.acc_fill_sz = ZERODECIMAL if not res['z'] else Decimal(res['z'])
                            if order_data.acc_fill_sz > 0:
                                order_data.avg_px = Decimal(res["Z"]) / Decimal(res["z"])
                            else:
                                order_data.avg_px = ZERODECIMAL    

                            if Decimal(res["n"]) >= 0:
                                order_data.fee_ccy = res['N'].lower() if res['N'] else ""
                                order_data.fee = ZERODECIMAL if not res['n'] else -Decimal(res['n'])
                                order_data.rebate_ccy = ""
                                order_data.rebate = ZERODECIMAL 
                            else:
                                order_data.fee_ccy = ""
                                order_data.fee = ZERODECIMAL
                                order_data.rebate_ccy = res['N'].lower() if res['N'] else ""
                                order_data.rebate = ZERODECIMAL if not res['n'] else -Decimal(res['n'])

                            order_data.update_time_epoch = Decimal(res['E'])
                            order_data.update_time_china = dt_epoch_to_china_str(res['E'])
                            order_data.create_time_epoch = Decimal(res['O'])
                            order_data.create_time_china = dt_epoch_to_china_str(res['O'])
                                
                            if res["x"] == "TRADE":
                                fill = fillData()

                                fill.gateway_name = self.gateway_name
                                fill.account_name = self.account_name
                                fill.exchange = self.exchange_name
                                fill.inst_type = info.inst_type
                                fill.inst_id = info.inst_id
                                fill.inst_id_local = inst_id_local

                                fill.ord_type = order_data.ord_type
                                fill.side = order_data.side
                                fill.ord_id = order_data.ord_id
                                fill.cl_ord_id = order_data.cl_ord_id
                                fill.bill_id = ""
                                fill.trade_id = str(res["t"])
                                fill.tag = ""
                                fill.taker_or_maker = "maker" if res['m'] else "taker"
                                fill.fill_px = order_data.fill_px
                                fill.fill_sz = order_data.fill_sz
                                fill.fee_ccy = order_data.fee_ccy
                                fill.fee = order_data.fee
                                fill.rebate_ccy = order_data.rebate_ccy
                                fill.rebate = order_data.rebate
                                fill.time_epoch = order_data.update_time_epoch
                                fill.time_china = order_data.update_time_china
                                if self.listener_fill:
                                    await self.listener_fill(fill)
                                    
                            if self.listener_order:
                                await self.listener_order(order_data)
                                
                        else:
                            print(res["e"])
                            print(res)

            except Exception as e:
                self.spot_private_ready = False
                timestamp = local_time()
                self.log_record(timestamp + " lever_websocket_with_login 连接断开，正在重连……" + str(e))
                continue

    async def ws_receive(self, request: Request):
        # self.log_record(f"binance ws receive: code: {request.response.status_code}, data: {request.response.json()}")
        send_return = sendReturnData()
        send_return.gateway_name = self.gateway_name
        send_return.account_name = self.account_name
        response = request.response
        data = response.json()

        # post order
        if request.method == "post":
            for (key, value) in request.data:
                if "newClientOrderId" in key:
                    send_return.cl_ord_id = value
        # cancel order
        elif request.method == "delete":
            for (key, value) in request.data:
                if "origClientOrderId" in key:
                    send_return.cl_ord_id = value
        
        if request.method == "post":
            send_return.channel = orderChannelData.ORDER
            if response.status_code // 100 == 2:
                send_return.ord_id = str(data["orderId"])
                send_return.ord_state = orderStateData.SENDSUCCEED
            elif "code" in data:
                send_return.code = data["code"]
                send_return.msg = data["msg"]
                if send_return.code == -1013:
                    send_return.msg = orderError.MINORDERSIZE
                elif send_return.code == -2010:
                    send_return.msg = orderError.POSTONLYPRICEERROR
                send_return.ord_state = orderStateData.SENDFAILED

        elif request.method == "delete":
            send_return.channel = orderChannelData.CANCELORDER
            if response.status_code // 100 == 2:
                send_return.ord_id = str(data["orderId"])
                send_return.ord_state = orderStateData.CANCELSUCCEED
            elif "code" in data:
                if send_return.code == -2011:
                    send_return.msg = cancelOrderError.NOTEXIST
                send_return.ord_state = orderStateData.CANCELFAILED
        else:
            pass
        if self.listener_send:
            await self.listener_send(send_return)

    def send_order(self, order: orderSendData):
        timeInForce = "GTC"
        type_ = order.ord_type.upper()

        if order.ord_type == "ioc":
            type_ = "LIMIT"
            timeInForce = "IOC"
        elif order.ord_type == "fok":
            type_ = "LIMIT"
            timeInForce = "FOK"
        elif order.ord_type == "post_only":
            type_ = "LIMIT_MAKER"
            timeInForce = None
        if order.inst_type.lower() == instTypeData.SPOT:
            self.async_spot.spot_post_order(
                symbol=order.inst_id, 
                side=order.side.upper(), 
                type_=type_.upper(), 
                timeInForce=timeInForce, 
                quantity=str(order.sz) if order.sz else "",  
                price=str(order.px) if order.px else "", 
                newClientOrderId=order.cl_ord_id,
                cb=self.ws_receive,
                callback_method="async"
            )
        elif order.inst_type.lower() == instTypeData.MARGINCROSS:
            self.async_spot.lever_post_order(
                symbol=order.inst_id, 
                side=order.side.upper(), 
                type_=type_.upper(), 
                timeInForce=timeInForce, 
                quantity=str(order.sz) if order.sz else "",  
                price=str(order.px) if order.px else "", 
                newClientOrderId=order.cl_ord_id,
                cb=self.ws_receive,
                callback_method="async"
            )
        return 
    
    def send_batch_order(self, order_list: List[orderSendData]):
        for order in order_list:
            timeInForce = "GTC"
            type_ = order.ord_type.upper()

            if order.ord_type == "ioc":
                type_ = "LIMIT"
                timeInForce = "IOC"
            elif order.ord_type == "fok":
                type_ = "LIMIT"
                timeInForce = "FOK"
            if order.inst_type.lower() == instTypeData.SPOT:

                self.async_spot.spot_post_order(
                    symbol=order.inst_id, 
                    side=order.side.upper(), 
                    type_=type_.upper(), 
                    timeInForce=timeInForce, 
                    quantity=str(order.sz) if order.sz else "",  
                    price=str(order.px) if order.px else "", 
                    newClientOrderId=order.cl_ord_id,
                    cb=self.ws_receive,
                    callback_method="async"
                )
            elif order.inst_type.lower() == instTypeData.MARGINCROSS:
                self.async_spot.lever_post_order(
                    symbol=order.inst_id, 
                    side=order.side.upper(), 
                    type_=type_.upper(), 
                    timeInForce=timeInForce, 
                    quantity=str(order.sz) if order.sz else "",  
                    price=str(order.px) if order.px else "", 
                    newClientOrderId=order.cl_ord_id,
                    cb=self.ws_receive,
                    callback_method="async"
                )
        
    def cancel_order(self, cancel: cancelOrderSendData):
        if cancel.inst_type.lower() == instTypeData.SPOT:
            if cancel.ord_id:
                self.async_spot.spot_cancel_order(cancel.inst_id.upper(), orderId=cancel.ord_id, cb=self.ws_receive, callback_method="async")
            elif cancel.cl_ord_id:
                self.async_spot.spot_cancel_order(cancel.inst_id.upper(), origClientOrderId=cancel.cl_ord_id, cb=self.ws_receive, callback_method="async")
        elif cancel.inst_type.lower() == instTypeData.MARGINCROSS:
            if cancel.ord_id:
                self.async_spot.lever_cancel_order(cancel.inst_id.upper(), orderId=cancel.ord_id, cb=self.ws_receive, callback_method="async")
            elif cancel.cl_ord_id:
                self.async_spot.lever_cancel_order(cancel.inst_id.upper(), origClientOrderId=cancel.cl_ord_id, cb=self.ws_receive, callback_method="async")

        return 
    
    def cancel_batch_order(self, cancel_list: List[cancelOrderSendData]):
        for cancel in cancel_list:
            if cancel.inst_type.lower() == instTypeData.SPOT:
                if cancel.ord_id:
                    self.async_spot.spot_cancel_order(cancel.inst_id.upper(), orderId=cancel.ord_id, cb=self.ws_receive, callback_method="async")
                elif cancel.cl_ord_id:
                    self.async_spot.spot_cancel_order(cancel.inst_id.upper(), origClientOrderId=cancel.cl_ord_id, cb=self.ws_receive, callback_method="async")
            elif cancel.inst_type.lower() == instTypeData.MARGINCROSS:
                if cancel.ord_id:
                    self.async_spot.lever_cancel_order(cancel.inst_id.upper(), orderId=cancel.ord_id, cb=self.ws_receive, callback_method="async")
                elif cancel.cl_ord_id:
                    self.async_spot.lever_cancel_order(cancel.inst_id.upper(), origClientOrderId=cancel.cl_ord_id, cb=self.ws_receive, callback_method="async")
        return 

    def cancel_batch_orders_sync(self, cancel_list: List[cancelOrderSendData]):
        result_list = []
        for cancel in cancel_list:
            if cancel.inst_type.lower() == instTypeData.SPOT:
                if cancel.ord_id:
                    result = self.sync_spot.spot_cancel_order(cancel.inst_id.upper(), orderId=cancel.ord_id)
                elif cancel.cl_ord_id:
                    result = self.sync_spot.spot_cancel_order(cancel.inst_id.upper(), origClientOrderId=cancel.cl_ord_id)
                result_list.append(result)
            elif cancel.inst_type.lower() == instTypeData.MARGINCROSS:
                if cancel.ord_id:
                    result = self.sync_spot.lever_cancel_order(cancel.inst_id.upper(), orderId=cancel.ord_id)
                elif cancel.cl_ord_id:
                    result = self.sync_spot.lever_cancel_order(cancel.inst_id.upper(), origClientOrderId=cancel.cl_ord_id)
                result_list.append(result)
        return result_list

    def send_order_sync(self, order: orderSendData):
        timeInForce = "GTC"
        type_ = order.ord_type.upper()

        if order.ord_type == "ioc":
            type_ = "LIMIT"
            timeInForce = "IOC"
        elif order.ord_type == "fok":
            type_ = "LIMIT"
            timeInForce = "FOK"
        if order.inst_type.lower() == instTypeData.SPOT:
            result = self.sync_spot.spot_post_order(
                symbol=order.inst_id, 
                side=order.side.upper(), 
                type_=type_.upper(), 
                timeInForce=timeInForce, 
                quantity=str(order.sz) if order.sz else "",  
                price=str(order.px) if order.px else "", 
                newClientOrderId=order.cl_ord_id,
            )
        elif order.inst_type.lower() == instTypeData.MARGINCROSS:
            result = self.sync_spot.lever_post_order(
                symbol=order.inst_id, 
                side=order.side.upper(), 
                type_=type_.upper(), 
                timeInForce=timeInForce, 
                quantity=str(order.sz) if order.sz else "",  
                price=str(order.px) if order.px else "", 
                newClientOrderId=order.cl_ord_id,
            )
    
        return 

    def cancel_order_sync(self, cancel: cancelOrderSendData):
        send_return = sendReturnData()
        send_return.gateway_name = self.gateway_name
        send_return.account_name = self.account_name

        orderId = None
        clOrderId = None
        if cancel.ord_id:
            orderId = cancel.ord_id
            send_return.ord_id = cancel.ord_id
        if cancel.cl_ord_id:
            clOrderId = cancel.cl_ord_id
            send_return.cl_ord_id = cancel.cl_ord_id
            
        if cancel.inst_type.lower() == instTypeData.SPOT:
            result = self.sync_spot.spot_cancel_order(cancel.inst_id.upper(), orderId=orderId, origClientOrderId=clOrderId)
        elif cancel.inst_type.lower() == instTypeData.MARGINCROSS:
            result = self.sync_spot.lever_cancel_order(cancel.inst_id.upper(), orderId=orderId, origClientOrderId=clOrderId)
        
        if "code" in result:
            send_return.code = result["code"]
        if "msg" in result:
            send_return.msg = result["msg"]
        return send_return

    def get_engine_status(self):
        return self.spot_private_ready and self.spot_public_ready
    
    def get_inst_id_price(self, inst_id:str, inst_type:str):
        result = self.sync_spot.market_bookTicker(inst_id.upper())
        return Decimal(result["bidPrice"])

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

# if __name__ == '__main__':
    
#     gateway = binanceGateway("test")
#     with open(f"/app/account_config/binance/sub00.yml", "r") as f:
#         config_file = yaml.load(f, Loader=yaml.FullLoader)
#     gateway.add_config_account(config_file)
#     gateway.add_inst_id_needed("LTCBTC", "SPOT")
#     loop = asyncio.get_event_loop()

#     tasks = []
    
#     task = gateway.spot_market()
#     tasks.append(task)
#     task = gateway.spot_websocket_with_login()
#     tasks.append(task)
#     task = gateway.extend_listen_key()
#     tasks.append(task)
#     loop.run_until_complete(asyncio.gather(*tasks))

#     loop.close()