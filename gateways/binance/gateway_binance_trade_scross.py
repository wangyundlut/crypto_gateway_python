

import asyncio
import time
import websockets
import json
import hmac
import base64
from copy import deepcopy
from typing import Dict, List
from datetime import datetime, timedelta
from decimal import Decimal

from crypto_gateway_python.gateways.binance.public_helper import (
    bn_get_inst_id_local,
    bn_get_account_ccy,
    bn_load_exchange_info,
    helper_get_price_spot
)

from crypto_gateway_python.utilities.utility_decimal import round_to
from crypto_gateway_python.utilities.utility_time import dt_china_now_str, dt_epoch_to_china_str, dt_epoch_utz_now
from crypto_gateway_python.data_structure.base_gateway import baseGatewayTrade
from crypto_gateway_python.data_structure.base_data_struct import(
    orderStateEnum,
    orderTypeEnum,
    orderChannelEnum,
    instTypeEnum,
    accountData,
    fillData,
    positionData,
    orderData,
    sendReturnData,
    timeOutData,
    wsBreakData,
)
from crypto_gateway_python.data_structure.base_error import (
    cancelOrderError,
    orderError,
)

from crypto_gateway_python.data_structure.base_data_struct import (
    orderSendData, 
    cancelOrderSendData,
    amendOrderSendData,
    )
from crypto_rest_python.async_rest_client import Request

from crypto_rest_python.binance.sync_rest.spot_api import SpotAPI
from crypto_rest_python.binance.async_rest.async_spot import asyncBinanceSpot
from crypto_rest_python.binance.sync_rest.consts import EXCHANGE_NAME, WS_SPOT_URL

HOURS8=8
ZERODECIMAL = Decimal("0")


class binanceGatewayTrade(baseGatewayTrade):
    def __init__(self, gateway_name='') -> None:
        super(binanceGatewayTrade, self).__init__(gateway_name)
        self.exchange_name = EXCHANGE_NAME
        self.rate_filters = {}
        self.listenKey = None

        """
        /api/ 与 /sapi/ 接口限频说明
        /api/*接口和 /sapi/*接口采用两套不同的访问限频规则, 两者互相独立。

        /api/*的接口相关：

        按IP和按UID(account)两种模式分别统计, 两者互相独立。
        以 /api/*开头的接口按IP限频，且所有接口共用每分钟1200限制。
        每个请求将包含一个 X-MBX-USED-WEIGHT-(intervalNum)(intervalLetter)的头，包含当前IP所有请求的已使用权重。
        每个成功的下单回报将包含一个X-MBX-ORDER-COUNT-(intervalNum)(intervalLetter)的头，其中包含当前账户已用的下单限制数量。
        /sapi/*的接口相关：

        按IP和按UID(account)两种模式分别统计, 两者互相独立。
        以/sapi/*开头的接口采用单接口限频模式。按IP统计的权重单接口权重总额为每分钟12000；按照UID统计的单接口权重总额是每分钟180000。
        每个接口会标明是按照IP或者按照UID统计, 以及相应请求一次的权重值。
        按照IP统计的接口, 请求返回头里面会包含X-SAPI-USED-IP-WEIGHT-1M=<value>, 包含当前IP所有请求已使用权重。
        按照UID统计的接口, 请求返回头里面会包含X-SAPI-USED-UID-WEIGHT-1M=<value>, 包含当前账户所有已用的UID权重。
        """

        self.orders_max_10seconds = 50
        self.ip_limit_1m = 0
        self.uid_limit_1m = 0
        self.ip_limit_1m_max = 12000
        self.uid_limit_1m_max = 180000

    
    ##################basic log and async function##############################
    
    def helper_get_inst_id_local(self, inst_id: str, inst_type: str=""):
        return bn_get_inst_id_local(inst_id, inst_type)

    def helper_get_account_ccy(self, ccy: str, inst_id: str="", inst_type: str=""):
        return bn_get_account_ccy(ccy, inst_id, inst_type)
    ##################basic log and async function##############################

    ##################load rest##############################
    
    def add_config_account(self, account_config={
        "exchange": "okx",
        "apiKey": "",
        "passPhrase": "",
        "secretKey": "",
        "isTest": True,
        "account_name": "",
    }):
        # config -> load rest
        assert account_config['exchange'] == self.exchange_name
        self.apiKey = account_config['apiKey']
        self.secretKey = account_config['secretKey']
        self.account_name = account_config['account_name']
        
        self.sync_scross = SpotAPI(self.apiKey, self.secretKey)
        self.async_scross = asyncBinanceSpot(self.apiKey, self.secretKey, self.loop, self.session)

        return

    def helper_load_exchange_info(self):
        spot = SpotAPI('', '')

        result = spot.market_exchangeInfo()
        for rateLimit in result["rateLimits"]:
            if rateLimit["rateLimitType"] == "REQUEST_WEIGHT":
                self.rate_filters["REQUEST_WEIGHT"] = rateLimit
            if rateLimit["rateLimitType"] == "ORDERS" and rateLimit["interval"] == "SECOND":
                self.rate_filters["ORDERS_SECOND"] = rateLimit
            if rateLimit["rateLimitType"] == "ORDERS" and rateLimit["interval"] == "DAY":
                self.rate_filters["ORDERS_DAY"] = rateLimit
            if rateLimit["rateLimitType"] == "RAW_REQUESTS":
                self.rate_filters["RAW_REQUESTS"] = rateLimit

        inst_id_info = bn_load_exchange_info()
        self.inst_id_info = inst_id_info
        return

    ##################load rest##############################

    ##################exchange helper##############################
    """
    get price, 
    """
    def helper_get_price(self, inst_id: str, inst_type: str=""):
        return helper_get_price_spot(inst_id)
    
    def helper_get_order_info(self, inst_id:str = "", ordId: str="", clOrdId: str="") -> orderData:
        if ordId != "":
            for cl_ord_id, order in self.live_order_data.items():
                if str(ordId) == order.ord_id:
                    return order
        elif clOrdId != "":
            if clOrdId in self.live_order_data:
                return self.live_order_data[clOrdId]
        
        ########## get from rest ###############
        # TODO:

        return order
        
    def helper_get_account(self, ccy, inst_id: str, inst_type: str="") -> accountData:
        inst_id_ccy = self.helper_get_account_ccy(ccy, inst_id, inst_type)
        if inst_id_ccy in self.account_data:
            return self.account_data[inst_id_ccy]
        
        ########## get from rest ###############
        acc = accountData()
        acc.gateway_name = self.gateway_name
        acc.account_name = self.account_name
        acc.exchange = self.exchange_name
        
        result = self.sync_scross.lever_get_account()
        balances  = result['userAssets']
        inst_id_local = self.helper_get_inst_id_local(inst_id, instTypeEnum.MARGINCROSS)
        info = self.inst_id_info[inst_id_local]
        for balance in balances:
            if balance["asset"].lower() == ccy.lower():
                acc.ccy = balance["asset"]
                acc.ccy_local = self.helper_get_account_ccy(balance["asset"], inst_id, instTypeEnum.MARGINCROSS)

                acc.asset = Decimal(balance["borrowed"]) + Decimal(balance["netAsset"])
                acc.debt = Decimal(balance["borrowed"])
                acc.equity = Decimal(balance["netAsset"])

                acc.frozen = Decimal(balance["locked"])
                acc.interest = Decimal(balance["interest"])

                acc.account_risk = 1 / Decimal(result["marginLevel"])

                acc.update_time_epoch = Decimal(dt_epoch_utz_now())
                acc.update_time_china = dt_epoch_to_china_str(acc.update_time_epoch)
                return acc
        return None
    
    def helper_get_position(self, inst_id: str, inst_type: str="") -> positionData:
        return None

    ##################exchange helper##############################
    def listen_key_call_back(self, request: Request):
        listenKey = request.response.json()["listenKey"]
        if listenKey != self.listenKey:
            self.helper_log_record(f"listen key diff, re connect ws..")
            self.gateway_ready = False
            self.ws = None
        
        return

    async def extend_listen_key(self):
        spot_api = self.async_scross
        while True:
            await asyncio.sleep(60)
            try:
                spot_api.websocket_get_listenKey_lever(cb=self.listen_key_call_back)
            except Exception as e:
                self.helper_log_record(f" extend listen key error: {e}")

    ##################trade gateway ##############################
    async def gateway_async(self):
        
        def getListenKey():
            result = self.sync_scross.websocket_get_listenKey_lever()
            listenKey = result['listenKey']
            return listenKey
        
        def getAccountFromRest():
            result = self.sync_scross.lever_get_account()
            balances  = result['userAssets']
            inst_id_local = self.helper_get_inst_id_local(inst_id, instTypeEnum.MARGINCROSS)
            info = self.inst_id_info[inst_id_local]
            for balance in balances:
                if Decimal(balance["netAsset"]) != Decimal(0):
                    acc.ccy = balance["asset"]
                    acc.ccy_local = self.helper_get_account_ccy(balance["asset"], instTypeEnum.MARGINCROSS)

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
                self.listenKey = listenKey
                self.helper_log_record(f"scross listenKey: {listenKey}")
                async with websockets.connect(WS_SPOT_URL + "/stream?streams=" + listenKey) as ws:
                    self.ws = ws
                    self.helper_log_record(f"cross_websocket_with_login connect.. ")
                    if not self.gateway_ready:
                        self.gateway_ready = True
                        self.helper_log_record(f"cross_websocket_with_login connect succeed!")

                    while True:
                        try:
                            # res = await asyncio.wait_for(ws.recv(), timeout=600)
                            res = await asyncio.wait_for(ws.recv(), timeout=30)
                        except asyncio.TimeoutError as e:
                            if listenKey != getListenKey():
                                raise Exception('listenKeyExpired')
                            else:
                                continue
                        except asyncio.CancelledError as e:
                            self.helper_log_record(f"scross_websocket_with_login CancelledError: {e}")
                            raise Exception('CancelledError')
                        except asyncio.IncompleteReadError as e:
                            self.helper_log_record(f"scross_websocket_with_login IncompleteReadError: {e}")
                            raise Exception('IncompleteReadError')
                        except websockets.exceptions.ConnectionClosed as e:
                            self.helper_log_record(f"scross_websocket_with_login ConnectionClosed : {e}")
                            raise Exception('ConnectionClosed')
                        
                        res = json.loads(res)
                    
                        if "stream" in res:
                            res = res["data"]

                        if res['e'] == 'outboundAccountPosition':
                            
                            for balance in res["B"]:
                                acc = accountData()
                                acc.gateway_name = self.gateway_name
                                acc.account_name = self.account_name
                                acc.exchange = self.exchange_name
                                acc.ccy = balance["a"]
                                acc.ccy_local = self.helper_get_account_ccy(balance["a"], instTypeEnum.MARGINCROSS)

                                acc.asset = Decimal(balance["f"]) + Decimal(balance["l"])
                                acc.debt = Decimal(0)
                                acc.equity = Decimal(balance["f"]) + Decimal(balance["l"])

                                acc.frozen = Decimal(balance["l"])
                                acc.interest = Decimal(0)
                                acc.account_risk = Decimal(0)

                                acc.update_time_epoch = Decimal(res["u"])
                                acc.update_time_china = dt_epoch_to_china_str(acc.update_time_epoch)
                                if self.listener_account:
                                    self.listener_account(acc)

                        elif res['e'] == 'balanceUpdate':
                            print(res["e"])
                            print(res)
                        elif res['e'] == 'executionReport':
                            # self.helper_log_record(f"order: {res['X']} {res}")
                            inst_id = res["s"]
                            inst_id_local = self.helper_get_inst_id_local(inst_id, instTypeEnum.MARGINCROSS)
                            info = self.inst_id_info[inst_id_local]
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
                                order_data.state = orderStateEnum.SENDSUCCEED
                            elif res["X"] == "PARTIALLY_FILLED":
                                order_data.state = orderStateEnum.PARTIALFILLED
                            elif res["X"] == "FILLED":
                                order_data.state = orderStateEnum.FILLED
                            elif res["X"] == "CANCELED":
                                order_data.state = orderStateEnum.CANCELSUCCEED
                                order_data.cl_ord_id = res["C"]
                            elif res["X"] == "REJECTED":
                                order_data.state = orderStateEnum.SENDFAILED
                            elif res["X"] == "EXPIRED":
                                order_data.state = orderStateEnum.CANCELSUCCEED
                            
                            if order_data.cl_ord_id in self.check_time_out_data.keys():
                                del self.check_time_out_data[order_data.cl_ord_id]

                            order_data.px = ZERODECIMAL if not res['p'] else Decimal(res['p'])
                            order_data.sz = ZERODECIMAL if not res['q'] else Decimal(res['q'])
                            order_data.pnl = ZERODECIMAL 
                            if res["o"] == "LIMIT":
                                order_data.ord_type = orderTypeEnum.LIMIT
                            elif res["o"] == "MARKET":
                                order_data.ord_type = orderTypeEnum.MARKET
                            elif res["o"] == "LIMIT_MAKER":
                                order_data.ord_type = orderTypeEnum.POSTONLY
                            elif res["f"] == "IOC":
                                order_data.ord_type = orderTypeEnum.IOC
                            elif res["f"] == "FOK":
                                order_data.ord_type = orderTypeEnum.FOK
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
                                    self.listener_fill(fill)

                            if self.listener_order:
                                self.listener_order(order_data)

                        else:
                            print(res["e"])
                            print(res)

            except Exception as e:
                if 'cannot schedule new FUTURES after shutdown' in str(e):
                    pass
                elif 'no running event loop' in str(e):
                    pass
                else:
                    self.helper_log_record(f"ws scross error: {e}")
                    ws_break = wsBreakData()
                    ws_break.gateway_name = self.gateway_name
                    ws_break.exchange_name = self.exchange_name
                    ws_break.break_reason = f"scross channel break: {e}"
                    ws_break.break_time_epoch = int(time.time() * 1000)
                    ws_break.break_time_china = dt_epoch_to_china_str(ws_break.break_time_epoch)
                    self.helper_log_record("send ws_break info to listener!")
                    if self.listener_ws_break:
                        self.listener_ws_break(ws_break)
                self.helper_log_record(f"now we restart websocket!")
                self.gateway_ready = False
                self.ws = None
                continue

    async def ws_receive(self, request: Request):
        # self.log_record(f"binance ws receive: code: {request.response.status_code}, data: {request.response.json()}")
        send_return = sendReturnData()
        send_return.gateway_name = self.gateway_name
        send_return.account_name = self.account_name
        response = request.response
        data = response.json()

        # self.helper_log_record(response.header)

        if "X-SAPI-USED-IP-WEIGHT-1M" in response.header:
            self.ip_limit_1m = int(response.header["X-SAPI-USED-IP-WEIGHT-1M"])

        if "X-SAPI-USED-UID-WEIGHT-1M" in response.header:
            self.uid_limit_1m = int(response.header["X-SAPI-USED-UID-WEIGHT-1M"])

        self.orders_10seconds = 0
        self.orders_1day = 0
        self.request_weight = 0

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
            send_return.channel = orderChannelEnum.ORDER
            if response.status_code // 100 == 2:
                send_return.ord_id = str(data["orderId"])
                send_return.ord_state = orderStateEnum.SENDSUCCEED
            elif "code" in data:
                send_return.code = data["code"]
                send_return.msg = data["msg"]
                if send_return.code == -1013:
                    send_return.msg = orderError.MINORDERSIZE
                elif send_return.code == -2010 and send_return.msg == "Order would immediately match and take.":
                    send_return.msg = orderError.POSTONLYPRICEERROR
                elif send_return.code == -1015:
                    send_return.msg= orderError.FREQUENT
                elif send_return.code == -2010 and send_return.msg == "Duplicate order sent.":
                    send_return.msg = orderError.DUPLICATECLIORDID
                elif send_return.code == -1021 and send_return.msg == "Timestamp for this request is outside of the recvWindow.":
                    send_return.msg = orderError.TIMEOUT
                
                send_return.ord_state = orderStateEnum.SENDFAILED

        elif request.method == "delete":
            send_return.channel = orderChannelEnum.CANCELORDER
            if response.status_code // 100 == 2:
                send_return.ord_id = str(data["orderId"])
                send_return.ord_state = orderStateEnum.CANCELSUCCEED
            elif "code" in data:
                if send_return.code == -2011:
                    send_return.msg = cancelOrderError.NOTEXIST
                send_return.ord_state = orderStateEnum.CANCELFAILED
        else:
            pass
        
        if send_return.cl_ord_id in self.check_time_out_data.keys():
            del self.check_time_out_data[send_return.cl_ord_id]

        if self.listener_send_return:
            self.listener_send_return(send_return)

    def gateway_start(self):
        asyncio.run_coroutine_threadsafe(self.gateway_async(), self.loop)
        asyncio.run_coroutine_threadsafe(self.send_data_time_pass(), self.loop)
        asyncio.run_coroutine_threadsafe(self.extend_listen_key(), self.loop)

    ##################trade engine ##############################
    

    ##################send order ##############################
    # this is async send
    def send_order(self, order: orderSendData):
        if order.cl_ord_id:
            self.check_time_out_data[order.cl_ord_id] = int(time.time() * 1000)

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
        
        self.async_scross.lever_post_order(
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
            if order.cl_ord_id:
                self.check_time_out_data[order.cl_ord_id] = int(time.time() * 1000)

            timeInForce = "GTC"
            type_ = order.ord_type.upper()

            if order.ord_type == "ioc":
                type_ = "LIMIT"
                timeInForce = "IOC"
            elif order.ord_type == "fok":
                type_ = "LIMIT"
                timeInForce = "FOK"
            if order.inst_type.lower() == instTypeEnum.MARGINCROSS:
                self.async_scross.lever_post_order(
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
        if cancel.cl_ord_id:
            self.check_time_out_data[cancel.cl_ord_id] = int(time.time() * 1000)

        if cancel.ord_id:
            self.async_scross.lever_cancel_order(cancel.inst_id.upper(), orderId=cancel.ord_id, cb=self.ws_receive, callback_method="async")
        elif cancel.cl_ord_id:
            self.async_scross.lever_cancel_order(cancel.inst_id.upper(), origClientOrderId=cancel.cl_ord_id, cb=self.ws_receive, callback_method="async")

        return 
    
    def cancel_batch_order(self, cancel_list: List[cancelOrderSendData]):
        for cancel in cancel_list:
            if cancel.cl_ord_id:
                self.check_time_out_data[cancel.cl_ord_id] = int(time.time() * 1000)

            if cancel.ord_id:
                self.async_scross.lever_cancel_order(cancel.inst_id.upper(), orderId=cancel.ord_id, cb=self.ws_receive, callback_method="async")
            elif cancel.cl_ord_id:
                self.async_scross.lever_cancel_order(cancel.inst_id.upper(), origClientOrderId=cancel.cl_ord_id, cb=self.ws_receive, callback_method="async")
        return 

    def cancel_batch_orders_sync(self, cancel_list: List[cancelOrderSendData]):
        result_list = []
        for cancel in cancel_list:
            # binance can cancel order base on symbol
            if cancel.side:
                result = self.sync_scross.lever_cancel_symbol_order(cancel.inst_id.upper())
                result_list.append(result)
                continue
                
            if cancel.ord_id:
                result = self.sync_scross.lever_cancel_order(cancel.inst_id.upper(), orderId=cancel.ord_id)
            elif cancel.cl_ord_id:
                result = self.sync_scross.lever_cancel_order(cancel.inst_id.upper(), origClientOrderId=cancel.cl_ord_id)
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
        
        result = self.sync_scross.lever_post_order(
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
            
        
        result = self.sync_scross.lever_cancel_order(cancel.inst_id.upper(), orderId=orderId, origClientOrderId=clOrderId)
        
        if "code" in result:
            send_return.code = result["code"]
        if "msg" in result:
            send_return.msg = result["msg"]
        return send_return

    ##################send order ##############################









    