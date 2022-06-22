
import asyncio
import aiohttp

import websockets
import json
import yaml
import time

from pprint import pprint
from datetime import datetime, timedelta
from decimal import Decimal
from copy import deepcopy
import logging
from typing import Dict, List

from crypto_gateway_python.utilities.utility_time import dt_epoch_to_china_str, dt_epoch_utz_now
from crypto_rest_python.binance.async_rest.consts import EXCHANGE_NAME
from crypto_rest_python.binance.sync_rest.usdt_api import USDTAPI as sync_rest
from crypto_rest_python.binance.async_rest.async_usdt_margin import asyncBinanceUsdtMargin as async_rest
from crypto_rest_python.async_rest_client import  Response, Request, asyncRestClient
from crypto_gateway_python.data_structure.base_gateway import baseGatewayTrade
from crypto_gateway_python.gateways.binance.public_helper import (
    bn_get_inst_id_local, 
    bn_load_usdt_margin_exchange_info, 
    bn_get_account_ccy,
    helper_get_price_usdt_margin
    )
from crypto_gateway_python.data_structure.base_data_struct import(
    depthData,
    accountData,
    fillData,
    orderStateEnum,
    orderTypeEnum,
    positionData,
    orderData,
    sendReturnData,
    orderChannelEnum,
    instTypeEnum,
    instInfoData,
    orderSideEnum,
    contractTypeEnum,
    subData
)
from crypto_gateway_python.data_structure.base_error import (
    cancelOrderError,
    exchangeError,
    orderError,
    amendOrderError
)

from crypto_gateway_python.data_structure.base_data_struct import (
    depthData, 
    orderSendData, 
    cancelOrderSendData,
    amendOrderSendData,
    wsBreakData,
    )

HOURS8 = 8
TIMEOUT = 10

class binanceGatewayTradeUsdtMargin(baseGatewayTrade):
    # loop for async rest
    def __init__(self, gateway_name='') -> None:
        baseGatewayTrade.__init__(self, gateway_name)

        self.exchange_name = EXCHANGE_NAME
        self.rate_filters = {}
        self.instrument_info : dict[str, instInfoData]= {}
        self.inst_id_set = set()
        # 
        
        self.usdtWebsocketUrl = "wss://fstream.binance.com/ws/"
        
        self.log: logging.Logger = None

        self.listenKey = None

        self.usdt_position_account = {}
        self.yaml_data = None
        self.conn_pool = None
        self.conn_pool_aliyun = None
    ##################basic log and async function##############################
    
    def helper_get_inst_id_local(self, inst_id: str, inst_type: str=""):
        return bn_get_inst_id_local(inst_id, inst_type)

    def helper_get_account_ccy(self, ccy: str, inst_id: str="", inst_type: str=""):
        return bn_get_account_ccy(ccy, inst_id, inst_type)
    
    ##################basic log and async function##############################


    ##################load rest##############################
    def add_config_account(self, config):
        # config -> load rest
        assert config['exchange'] == self.exchange_name
        self.apiKey = config['apiKey']
        self.secretKey = config['secretKey']
        # self.passPhrase = config['passPhrase']
        self.account_name = config['account_name']
        
        self.sync_rest = sync_rest(self.apiKey, self.secretKey)
        # self.async_rest = async_rest(self.apiKey, self.secretKey, self.loop, self.session)
        self.async_rest = async_rest(self.apiKey, self.secretKey, loop=self.loop, session=self.session)
        return
    
    def helper_load_exchange_info(self):
        # load  exchange info
        rest = sync_rest()
        result = rest.market_get_exchangeInfo()
        for rateLimit in result["rateLimits"]:
            if rateLimit["rateLimitType"] == "REQUEST_WEIGHT":
                self.rate_filters["REQUEST_WEIGHT"] = rateLimit
            if rateLimit["rateLimitType"] == "ORDERS" and rateLimit["interval"] == "SECOND":
                self.rate_filters["ORDERS_SECOND"] = rateLimit
            if rateLimit["rateLimitType"] == "ORDERS" and rateLimit["interval"] == "DAY":
                self.rate_filters["ORDERS_DAY"] = rateLimit
            if rateLimit["rateLimitType"] == "RAW_REQUESTS":
                self.rate_filters["RAW_REQUESTS"] = rateLimit

        self.instrument_info = bn_load_usdt_margin_exchange_info()
        return
    
    def helper_get_price(self, inst_id: str, inst_type: str=""):
        return helper_get_price_usdt_margin(inst_id)

    ##################load rest##############################

    ##################strategy engine add##############################
    def add_inst_id_needed(self, inst_id: str, inst_type: str=""):
        # for okx, all inst_id is upper
        inst_id_local = self.helper_get_inst_id_local(inst_id, inst_type)
        self.inst_id_set.add(inst_id_local)

    ##################strategy engine add##############################

    def listen_key_call_back(self, request: Request):
        return

    async def extend_listen_key(self):
        async_est = self.async_rest
        while True:
            await asyncio.sleep(60)
            try:
                
                self.async_rest.websocket_get_listenKey_usdt_margin(cb=self.listen_key_call_back)
                
            except Exception as e:
                self.helper_log_record(f" extend listen key error: {e}")

    def helper_get_order_info(self,  symbol: str, ord_id: str="", client_order_id: str="") -> orderData:
        if ord_id:
            result = self.sync_rest.trade_get_order_info(symbol.upper(), orderId=ord_id)
        elif client_order_id:
            result = self.sync_rest.trade_get_order_info(symbol.upper(), origClientOrderId=client_order_id)
        
        order = orderData()
        order.gateway_name = self.gateway_name
        order.account_name = self.account_name
        order.exchange = EXCHANGE_NAME
        order.inst_type = instTypeEnum.USDTM
        order.inst_id = result['symbol']
        order.inst_id_local = self.helper_get_inst_id_local(order.inst_id, order.inst_type)
        order.ord_id = str(result['orderId'])
        order.cl_ord_id = str(result['clientOrderId'])
        order.state = order_state_transfer(order["status"])
        order.px = Decimal(result["price"])
        order.sz = Decimal(result["origQty"])
        order.ord_type = order_type_transfer(order["type"], order["timeInForce"])
        order.side = result["side"]
        order.update_time_epoch = result["time"]
        order.update_time_china = dt_epoch_to_china_str(order.update_time_epoch)
        return order
        
    def helper_get_account(self, ccy: str) -> accountData:
        result = self.sync_rest.trade_get_account()
        acc = accountData()
        acc.gateway_name = self.gateway_name
        acc.account_name = self.account_name
        acc.exchange = EXCHANGE_NAME
        acc.inst_type = instTypeEnum.USDTM
        for asset in result['assets']:
            if asset["asset"] == ccy.upper():
                acc.ccy = asset["asset"].lower()
                acc.ccy_local = bn_get_account_ccy(acc.ccy, "", instTypeEnum.USDTM)
                acc.asset = Decimal(asset["walletBalance"])
                acc.debt = Decimal(0)
                acc.equity = Decimal(asset["availableBalance"])
                acc.frozen = Decimal(asset["maintMargin"])
                # totalMarginBalance -> walletBalance ?
                acc.account_risk = Decimal(result["totalMaintMargin"]) / Decimal(result["totalMarginBalance"])
                acc.update_time_epoch = int(time.time() * 1000)
                acc.update_time_china = dt_epoch_to_china_str(acc.update_time_epoch)

        return acc

    def helper_get_position(self, inst_id: str, inst_type: str="") -> positionData:
        result = self.sync_rest.trade_get_account()
        pos = positionData()
        pos.gateway_name = self.gateway_name
        pos.account_name = self.account_name
        pos.exchange = EXCHANGE_NAME
        for position in result['positions']:
            if inst_id.upper() == position['symbol']:
                pos.inst_id = position['symbol']
                pos.inst_type = instTypeEnum.USDTM
                pos.inst_id_local = self.helper_get_inst_id_local(pos.inst_id, pos.inst_type)
                pos.avg_px = Decimal(position["entryPrice"])
                pos.direction = 'long' if Decimal(position['positionAmt']) > 0 else 'short'
                pos.pos = Decimal(position['positionAmt'])
                pos.update_time_epoch = int(time.time() * 1000)
                pos.update_time_china = dt_epoch_to_china_str(pos.update_time_epoch)
        return pos

    async def gateway_async(self):
        
        def getListenKey():
            result = self.sync_rest.websocket_get_listenKey()
            listenKey = result['listenKey']
            return listenKey
        
        while True:
            try:
                listenKey = getListenKey()
                self.listenKey = listenKey

                async with websockets.connect(self.usdtWebsocketUrl + listenKey) as ws:
                    
                    self.helper_log_record(f"usdt margin trade connect.. ")
                    if not self.gateway_ready:
                        self.gateway_ready = True
                        
                    while True:
                        try:
                            res = await asyncio.wait_for(ws.recv(), timeout=600)
                        except asyncio.TimeoutError as e:
                            if listenKey != getListenKey():
                                raise Exception('listenKeyExpired')
                            else:
                                continue
                        except asyncio.CancelledError as e:
                            self.helper_log_record(f"usdt margin trade CancelledError: {e}")
                            raise Exception('CancelledError')
                        except asyncio.IncompleteReadError as e:
                            self.helper_log_record(f"usdt margin trade IncompleteReadError: {e}")
                            raise Exception('IncompleteReadError')
                        except websockets.exceptions.ConnectionClosed as e:
                            self.helper_log_record(f"usdt margin trade ConnectionClosed : {e}")
                            raise Exception('ConnectionClosed')
                        
                        res = json.loads(res)
                        print(f"=====res=====")
                        print(res)

                        if res['e'] == 'ACCOUNT_UPDATE':
                            trigger_time = res['T']
                            for balance in res['a']['B']:

                                acc = accountData()
                                acc.gateway_name = self.gateway_name
                                acc.account_name = self.account_name
                                acc.exchange = self.exchange_name
                                acc.ccy = balance["a"].lower()
                                acc.ccy_local = self.helper_get_account_ccy(balance["a"], instTypeEnum.USDTM)
                                
                                acc.asset = Decimal(balance["wb"])
                                acc.debt = Decimal(0)
                                acc.equity = Decimal(balance["wb"])
                                
                                acc.frozen = Decimal(0)
                                acc.interest = Decimal(0)
                                acc.account_risk = Decimal(0)

                                acc.update_time_epoch = Decimal(trigger_time)
                                acc.update_time_china = dt_epoch_to_china_str(acc.update_time_epoch)
                                if self.listener_account:
                                    self.listener_account(acc)

                            for position in res['a']['P']:
                                pos = positionData()
                                pos.gateway_name = self.gateway_name
                                pos.account_name = self.account_name
                                pos.exchange = self.exchange_name
                                pos.inst_id = position['s']
                                pos.inst_type = instTypeEnum.USDTM
                                pos.inst_id_local = self.helper_get_inst_id_local(pos.inst_id, pos.inst_type)
                                pos.direction = 'long' if Decimal(position['pa']) > 0 else 'short'
                                pos.pos = Decimal(position['pa'])
                                pos.open_px = Decimal(position['ep'])
                                if self.listener_position:
                                    self.listener_position(pos)

                        elif res['e'] == 'ORDER_TRADE_UPDATE':
                            event_time_epoch = res['E']
                            trade_time_epoch = res['T']
                            order = res['o']
                            inst_id = order["s"]
                            inst_id_local = self.helper_get_inst_id_local(inst_id, instTypeEnum.USDTM)
                            info = self.instrument_info[inst_id_local]
                            ZERODECIMAL = Decimal(0)
                            order_data = orderData()

                            order_data.gateway_name = self.gateway_name
                            order_data.account_name = self.account_name
                            order_data.exchange = self.exchange_name
                            order_data.inst_type = info.inst_type
                            order_data.inst_id = info.inst_id
                            order_data.inst_id_local = inst_id_local

                            order_data.ord_id = str(order['i'])
                            order_data.cl_ord_id = order['c']
                            
                            order_data.state = order_state_transfer(order["X"])
                            
                            
                            order_data.px = ZERODECIMAL if not order['p'] else Decimal(order['p'])
                            order_data.sz = ZERODECIMAL if not order['q'] else Decimal(order['q'])
                            order_data.pnl = ZERODECIMAL 
                            order_data.ord_type = order_type_transfer(order["o"], order["f"])
                            
                            order_data.side = order['S'].lower()

                            order_data.fill_px = ZERODECIMAL if not order['L'] else Decimal(order['L'])
                            order_data.fill_sz = ZERODECIMAL if not order['l'] else Decimal(order['l'])
                            if 'z' in order:
                                order_data.acc_fill_sz = Decimal(order['z'])

                            if "n" in order:
                                if Decimal(order["n"]) < 0:
                                    order_data.rebate = -Decimal(order["n"])
                                    order_data.rebate_ccy = order["N"]
                                else:
                                    order_data.fee = -Decimal(order["n"])
                                    order_data.fee_ccy = order["N"]

                            order_data.update_time_epoch = Decimal(event_time_epoch)
                            order_data.update_time_china = dt_epoch_to_china_str(event_time_epoch)
                            order_data.create_time_epoch = Decimal(trade_time_epoch)
                            order_data.create_time_china = dt_epoch_to_china_str(trade_time_epoch)
                                
                            if order["x"] == "TRADE":
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
                                fill.trade_id = str(order["t"])
                                fill.tag = ""
                                fill.taker_or_maker = "maker" if order['m'] else "taker"
                                fill.fill_px = order_data.fill_px
                                fill.fill_sz = order_data.fill_sz
                                fill.fee_ccy = order_data.fee_ccy
                                fill.fee = order_data.fee
                                fill.rebate_ccy = order_data.rebate_ccy
                                fill.rebate = order_data.rebate
                                fill.time_epoch = order_data.update_time_epoch
                                fill.time_china = order_data.update_time_china
                                if self.listener_fill:
                                    self.listener_fill(fill)
                                    
                            if self.listener_order:
                                self.listener_order(order_data)
                                
                        else:
                            print(res["e"])
                            print(res)

            except Exception as e:
                ws_break = wsBreakData()
                ws_break.gateway_name = self.gateway_name
                ws_break.exchange_name = self.exchange_name
                ws_break.break_reason = f"margin channel break: {e}"
                ws_break.break_time_epoch = int(time.time() * 1000)
                ws_break.break_time_china = dt_epoch_to_china_str(ws_break.break_time_epoch)
                
                if 'cannot schedule new futures after shutdown' in str(e).lower():
                    self.helper_log_record(f"ws usdt margin error: {e}")
                elif 'no running event loop' in str(e):
                    self.helper_log_record(f"ws usdt margin error: {e}")
                else:
                    self.helper_log_record(f"ws usdt margin error: {e}")
                    
                if self.gateway_ready:
                    if self.listener_ws_break:
                        self.listener_ws_break(ws_break)
                    else:
                        self.helper_log_record(f"ws usdt margin, no! ws! break! listener!")
                else:
                    self.helper_log_record(f"usdt margin not ready!!! please check!")
                self.gateway_ready = False
                continue

    def gateway_start(self):
        asyncio.run_coroutine_threadsafe(self.gateway_async(), self.loop)

    def send_return_receive(self, request: Request):
        # self.helper_log_record(f"binance ws receive: code: {request.response.status_code}, data: {request.response.json()}")
        send_return = sendReturnData()
        send_return.gateway_name = self.gateway_name
        send_return.account_name = self.account_name
        response = request.response
        data = response.json()

        # post order
        if request.method == "post":
            for (key, value) in request.data:
                if "clientOrderId" in key:
                    send_return.cl_ord_id = value
        # cancel order
        elif request.method == "delete":
            for (key, value) in request.data:
                if "clientOrderId" in key:
                    send_return.cl_ord_id = value
        
        if request.method == "post":
            send_return.channel = orderChannelEnum.ORDER
            if response.status_code // 100 == 2:
                send_return.ord_id = str(data["orderId"])
                send_return.cl_ord_id = str(data["clientOrderId"])
                send_return.ord_state = orderStateEnum.SENDSUCCEED
            elif "code" in data:
                send_return.code = data["code"]
                send_return.msg = data["msg"]
                if send_return.code == -1013:
                    send_return.msg = orderError.MINORDERSIZE
                elif send_return.code == -2010:
                    send_return.msg = orderError.POSTONLYPRICEERROR
                elif send_return == -4164:
                    send_return.msg = orderError.MINORDERSIZE
                send_return.ord_state = orderStateEnum.SENDFAILED

        elif request.method == "delete":
            send_return.channel = orderChannelEnum.CANCELORDER
            if response.status_code // 100 == 2:
                send_return.ord_id = str(data["orderId"])
                send_return.ord_state = orderStateEnum.CANCELSUCCEED
            elif "code" in data:
                if data['code'] == -2011:
                    send_return.msg = cancelOrderError.NOTEXIST
                send_return.ord_state = orderStateEnum.CANCELFAILED
        else:
            pass

        if self.listener_send_return:
            self.listener_send_return(send_return)

    def send_order(self, order: orderSendData):
        timeInForce = "GTC"
        type_ = order.ord_type.upper()

        if order.ord_type == "ioc":
            type_ = "LIMIT"
            timeInForce = "IOC"
        elif order.ord_type == "fok":
            type_ = "LIMIT"
            timeInForce = "FOK"
        elif order.ord_type == "limit":
            type_ = "LIMIT"
            timeInForce = "GTC"
        elif order.ord_type == "market":
            type_ = "MARKET"
            
        self.async_rest.usdt_margin_post_order(
            symbol=order.inst_id, 
            side=order.side.upper(), 
            type_=type_.upper(), 
            timeInForce=timeInForce, 
            quantity=str(order.sz) if order.sz else "",  
            price=str(order.px) if order.px else "", 
            newClientOrderId=order.cl_ord_id,
            cb=self.send_return_receive
        )
        
        return 
    
    def send_batch_order(self, order_list: List[orderSendData]):
        pass
    
    def cancel_order(self, cancel: cancelOrderSendData):
        
        self.async_rest.usdt_margin_cancel_order(
            symbol=cancel.inst_id.upper(),
            orderId=cancel.ord_id,
            origClientOrderId=cancel.cl_ord_id,
            cb=self.send_return_receive
        )
        
        return 
    
    def cancel_batch_order(self, cancel_list: List[cancelOrderSendData]):
        pass
        return 

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

def order_state_transfer(status) -> orderStateEnum:
    if status == "NEW":
        return orderStateEnum.SENDSUCCEED
    elif status == "PARTIALLY_FILLED":
        return orderStateEnum.PARTIALFILLED
    elif status == "FILLED":
        return orderStateEnum.FILLED
    elif status == "CANCELED":
        return orderStateEnum.CANCELSUCCEED
    elif status == "REJECTED":
        return orderStateEnum.SENDFAILED
    elif status == "EXPIRED":
        return orderStateEnum.CANCELSUCCEED
    return

def order_type_transfer(type_, timeInforce) -> orderTypeEnum:
    if type_ == "LIMIT":
        return orderTypeEnum.LIMIT
    elif type_ == "MARKET":
        return orderTypeEnum.MARKET
    elif timeInforce == "IOC":
        return orderTypeEnum.IOC
    elif timeInforce == "FOK":
        return orderTypeEnum.FOK


##########################
def listener_order_test(order: orderData): 
    print(f"=====order=====")
    print(order)

def listener_account_test(account: accountData):
    print(f"=====account=====")
    print(account)

def listener_position_test(position: positionData):
    print(f"=====position=====")
    print(position)

def listener_fill_test(fill: fillData):
    print(f"=====fill=====")
    print(fill)

def listener_send_return_test(send_return: sendReturnData):
    print(f"=====send return=====")
    print(send_return)


if __name__ == '__main__':
    from crypto_rest_python.async_rest_client import create_session, start_event_loop
    loop = asyncio.get_event_loop()
    session = loop.run_until_complete(create_session(loop))
    start_event_loop(loop)

    gateway = binanceGatewayTradeUsdtMargin("test")
    gateway.add_loop_session(loop, session)
    with open(f"/home/op/wangyun/account_config/binance/test1.yaml", "r") as f:
        config_file = yaml.full_load(f)
    gateway.add_config_account(config_file)
    gateway.helper_load_exchange_info()

    gateway.add_listener_account(listener_account_test)
    gateway.add_listener_order(listener_order_test)
    gateway.add_listener_fill(listener_fill_test)
    gateway.add_listener_position(listener_position_test)
    gateway.add_listener_send_return(listener_send_return_test)
    gateway.gateway_start()
    time.sleep(2)

    print(gateway.helper_get_price('BTCUSDT'))
    print(gateway.helper_get_account('USDT'))
    print(gateway.helper_get_position('BTCUSDT'))
    print(gateway.sync_rest.trade_get_balance())
    sub = subData()
    sub.inst_id = "BTCUSDT"
    gateway.add_strategy_sub(sub)
    print(f"=====cancel all =====")
    print(gateway.sync_rest.trade_cancel_order_all('BTCUSDT'))
    # cancel = cancelOrderSendData()
    # cancel.inst_id = "BTCUSDT"
    # cancel.ord_id = "59048207315"
    # gateway.cancel_order(cancel)

    order = orderSendData()
    order.inst_id='BTCUSDT'
    order.px='20830'
    order.sz=0.001
    order.side="sell"
    order.ord_type=orderTypeEnum.LIMIT
    # gateway.send_order(order)
    
    while True:
        time.sleep(10)