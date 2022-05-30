

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
import urllib
import hashlib
import yaml

from crypto_gateway_python.gateways.huobi.public_helper import (
    huobi_get_inst_id_local,
    huobi_get_account_ccy,
    huobi_load_exchange_info,
    helper_get_price_spot
)

from crypto_gateway_python.utilities.utility_decimal import round_to
from crypto_gateway_python.utilities.utility_time import dt_china_now_str, dt_epoch_to_china_str, dt_epoch_utz_now
from crypto_gateway_python.data_structure.base_gateway import baseGatewayTrade
from crypto_gateway_python.data_structure.base_data_struct import(
    orderSideEnum,
    orderStateEnum,
    orderTypeEnum,
    orderChannelEnum,
    instTypeEnum,
    accountData,
    fillData,
    positionData,
    orderData,
    sendReturnData,
    subData,
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
from crypto_gateway_python.utilities.utility_yaml import load_account_file
from crypto_rest_python.async_rest_client import Request
from crypto_rest_python.huobi.sync_rest.rest_api_spot import huobiRestSpot
from crypto_rest_python.huobi.async_rest.async_spot import asyncHuobiSpot
from crypto_rest_python.huobi.sync_rest.consts import EXCHANGE_NAME, SPOT_WEBSOCKET_TRADE_HOST, SPOT_REST_HOST

HOURS8=8
ZERODECIMAL = Decimal("0")


class huobiGatewayTradeSpot(baseGatewayTrade):
    def __init__(self, gateway_name='') -> None:
        baseGatewayTrade.__init__(self, gateway_name)
        self.exchange_name = EXCHANGE_NAME
        self.order_dict: Dict[str, orderData] = {}

    ##################basic log and async function##############################
    
    def helper_get_inst_id_local(self, inst_id: str, inst_type: str=""):
        return huobi_get_inst_id_local(inst_id, inst_type)

    def helper_get_account_ccy(self, ccy: str, inst_id: str="", inst_type: str=""):
        return huobi_get_account_ccy(ccy, inst_id, inst_type)
    ##################basic log and async function##############################

    ##################load rest##############################
    
    def add_config_account(self, account_config={
        "exchange": "huobi",
        "key": "",
        "secret": "",
        "account_name": "",
    }):
        # config -> load rest
        assert account_config['exchange'] == self.exchange_name
        self.account_config = account_config
        key = account_config['key']
        secret = account_config['secret']
        self.account_name = account_config['account_name']
        
        self.sync_spot = huobiRestSpot(key, secret)
        self.async_spot = asyncHuobiSpot(key, secret, loop=self.loop, session=self.session)

        return

    def helper_load_exchange_info(self):
        self.inst_id_info = huobi_load_exchange_info()
        return

    ##################load rest##############################

    ##################exchange helper##############################
    """
    get price, 
    """
    def helper_get_price(self, inst_id: str, inst_type: str=""):
        return helper_get_price_spot(inst_id)
    
    def helper_get_order_info(self,  ord_id: str="", client_order_id: str="") -> orderData:
        if ord_id:
            result = self.sync_spot.trade_get_order_info(order_id=ord_id)
        elif client_order_id:
            result = self.sync_spot.trade_get_order_info_in_client_order_id(client_order_id=client_order_id)
        # transfer
        
        ########## get from rest ###############
        order = orderData()
        order.gateway_name = self.gateway_name
        order.account_name = self.account_name
        order.exchange = self.exchange_name
        order.inst_type = order_source_transfer(result["source"])
        order.inst_id = result["symbol"]
        order.inst_id_local = self.helper_get_inst_id_local(order.inst_id, order.inst_type)
        order.ord_id = result["id"]
        order.cl_ord_id = result["client-order-id"]
        order.state = order_state_transfer(result["state"])
        order.px = Decimal(result["price"])
        order.sz = Decimal(result["amount"])
        order.ord_type, order.side = order_type_transfer(result["type"])
        order.fill_sz = Decimal(result["field-amount"])
        order.fill_px = Decimal(result["field-cash-amount"]) / Decimal(result["field-amount"])
        order.acc_fill_sz = order.fill_sz
        order.avg_px = order.fill_px
        order.fee = Decimal(result["field-fees"])
        order.create_time_epoch = int(result["created-at"])
        order.create_time_china = dt_epoch_to_china_str(order.create_time_epoch)
        return order
        
    def helper_get_account(self, ccy, inst_id: str, inst_type: str="") -> accountData:
        inst_id_local = self.helper_get_inst_id_local(inst_id, inst_type)
        info = self.inst_id_info[inst_id_local]
        result = self.sync_spot.account_get_balance(info.inst_type)

        trade_frozen = {}
        for li in result["data"]["list"]:
            if li["currency"] == ccy:
                trade_frozen[li["type"]] = li
        
        account = accountData()
        account.gateway_name = self.gateway_name
        account.account_name = self.account_name
        account.exchange = self.exchange_name
        account.ccy = ccy.lower()
        account.ccy_local = self.helper_get_account_ccy(ccy.lower(), info.inst_id, info.inst_type)
        account.asset = Decimal(trade_frozen["trade"]["balance"])
        account.equity = Decimal(trade_frozen["trade"]["balance"])
        account.debt = Decimal("0")
        account.frozen = Decimal(trade_frozen["frozen"]["balance"])
        account.interest = Decimal("0")
        account.account_risk = Decimal("0")
        account.update_time_epoch = Decimal(int(time.time() * 1000))
        account.update_time_china = dt_epoch_to_china_str(account.update_time_epoch)
        return account
    
    def helper_get_position(self, inst_id: str, inst_type: str="") -> positionData:
        return None

    ##################exchange helper##############################
    

    ##################trade gateway ##############################
    
    def send_return_trans(self, d: dict):
        send_return = sendReturnData()
        send_return.gateway_name = self.gateway_name
        send_return.account_name = self.account_name
        send_return.ws_id = ""
        send_return.channel = orderChannelEnum.ORDER
        send_return.ord_id = ""
        send_return.cl_ord_id = d["clientOrderId"]
        # trigger error
        if "errCode" in d:
            send_return.code = d["errCode"]
            send_return.msg = d["errMessage"]
        # deletion
        else:
            send_return.code = d["eventType"]
            send_return.msg = d["eventType"]
        return send_return
    
    def order_trans(self, data):
        """
        middle engine's listener
        """
        eventType = data["eventType"]
        order = orderData()
        order.gateway_name = self.gateway_name
        order.account_name = self.account_name
        order.exchange = EXCHANGE_NAME
        
        order.inst_type = order_source_transfer(data["orderSource"])

        order.inst_id = data["symbol"]
        order.inst_id_local = self.helper_get_inst_id_local(order.inst_id, order.inst_type)
        order.ord_id = str(data["orderId"])
        order.cl_ord_id = str(data["clientOrderId"])

        order.px = Decimal(data["orderPrice"])
        order.sz = Decimal(data["orderSize"])
        order.ord_type, order.side = order_type_transfer(data["type"])

        if eventType == "creation":
            order.update_time_epoch = Decimal(int(data["orderCreateTime"]))
            order.update_time_china = dt_epoch_to_china_str(order.update_time_epoch)
            order.create_time_epoch = Decimal(int(data["orderCreateTime"]))
            order.create_time_china = dt_epoch_to_china_str(order.update_time_epoch)
            order.state = orderStateEnum.SENDSUCCEED
            # add order dict
            self.order_dict[order.ord_id] = order
            return order
        elif eventType == "cancellation":
            order.update_time_epoch = Decimal(int(data["lastActTime"]))
            order.update_time_china = dt_epoch_to_china_str(order.update_time_epoch)
            order.create_time_epoch = Decimal(int(data["lastActTime"]))
            order.create_time_china = dt_epoch_to_china_str(order.update_time_epoch)
            order.acc_fill_sz = Decimal(data["execAmt"]) # acc fill sz
            # for remainAmt, un filled sz, calculate by orderSize - acc_fill_sz
            if order.acc_fill_sz == 0:
                order.state = orderStateEnum.CANCELSUCCEED
            else: 
                order.state = orderStateEnum.PARTIALCANCELED
            return order

    def order_fill_trans(self, data):
        """
        middle engine's listener
        """
        order = orderData()
        order.gateway_name = self.gateway_name
        order.account_name = self.account_name
        order.exchange = EXCHANGE_NAME
        order.inst_type = order_source_transfer(data["orderSource"])

        order.inst_id = data["symbol"]
        order.inst_id_local = self.helper_get_inst_id_local(order.inst_id, order.inst_type)
        order.ord_id = str(data["orderId"])
        order.cl_ord_id = str(data["clientOrderId"])

        order.px = Decimal(data["orderPrice"])
        order.sz = Decimal(data["orderSize"])
        order.ord_type, order.side = order_type_transfer(data["type"])

        order.fill_px = Decimal(data["tradePrice"])
        order.fill_sz = Decimal(data["tradeVolume"])

        if order.ord_id in self.order_dict:
            order_origin = self.order_dict[order.ord_id]
            order.avg_px = (order_origin.acc_fill_sz * order_origin.avg_px + order.fill_px * order.fill_sz) / (order_origin.acc_fill_sz + order.fill_sz)
            order.acc_fill_sz = (order_origin.acc_fill_sz + order.fill_sz)

        order.update_time_epoch = Decimal(int(data["tradeTime"]))
        order.update_time_china = dt_epoch_to_china_str(order.update_time_epoch)
        order.create_time_epoch = Decimal(int(data["tradeTime"]))
        order.create_time_china = dt_epoch_to_china_str(order.update_time_epoch)
        if data["orderStatus"] == "partial-filled":
            order.state = orderStateEnum.PARTIALFILLED
        elif data["orderStatus"] == "filled":
            order.state = orderStateEnum.FILLED
        
        return order
    
    def fill_trans(self, data):
        
        fill = fillData()
        fill.gateway_name = self.gateway_name
        fill.account_name = self.account_name
        fill.exchange = EXCHANGE_NAME
        fill.inst_type = order_source_transfer(data["source"])

        fill.inst_id = data["symbol"]
        fill.inst_id_local = self.helper_get_inst_id_local(fill.inst_id, fill.inst_type)

        fill.ord_type, fill.side = order_type_transfer(data["orderType"])
        fill.ord_id = str(data["orderId"])
        fill.cl_ord_id = str(data["clientOrderId"])
        fill.trade_id = data["tradeId"]
        fill.taker_or_maker = "taker" if data["aggressor"] else "maker"
        fill.fill_px = Decimal(data["tradePrice"])
        fill.fill_sz = Decimal(data["tradeVolume"])
        
        if fill.taker_or_maker == "maker":
            fill.rebate_ccy = data["feeCurrency"]
            fill.rebate = abs(Decimal(data["transactFee"]))
        else:
            fill.fee_ccy = data["feeCurrency"]
            fill.fee = -abs(Decimal(data["transactFee"]))

        fill.time_epoch = Decimal(int(data["tradeTime"]))
        fill.time_china = dt_epoch_to_china_str(fill.time_epoch)
        return fill
    
    def account_trans(self, data):
        """
        middle engine's listener
        """
        # print(data)
        account = accountData()
        account.gateway_name = self.gateway_name
        account.account_name = self.account_name
        account.exchange = self.exchange_name
        account.ccy = data["currency"]
        inst_type = self.sync_spot.get_account_type_from_account_id(data["accountId"])
        if inst_type == "spot":
            account.ccy_local = self.helper_get_account_ccy(account.ccy, "", instTypeEnum.SPOT, )
        elif inst_type == "margin":
            account.ccy_local = self.helper_get_account_ccy(account.ccy, "", instTypeEnum.MARGINISOLATED)
        elif inst_type == "super-margin":
            account.ccy_local = self.helper_get_account_ccy(account.ccy, "", instTypeEnum.MARGINCROSS)
        account.asset = Decimal(data["balance"])
        account.equity = Decimal(data["balance"])
        account.debt = Decimal("0")
        account.frozen = Decimal(data["balance"]) - Decimal(data["available"])
        account.interest = Decimal("0")
        account.account_risk = Decimal("0")
        if data["changeTime"]:
            account.update_time_epoch = Decimal(data["changeTime"])
        else:
            account.update_time_epoch = Decimal(int(time.time() * 1000))
        account.update_time_china = dt_epoch_to_china_str(account.update_time_epoch)
        return account

    async def gateway_async(self):
        while True:
            try:
                params_sign = create_signature_v2(self.account_config['key'], "GET", SPOT_REST_HOST, "/ws/v2", self.account_config['secret'])
                login_params = {
                    "action": "req", 
                    "ch": "auth",
                    "params": params_sign
                }
                async with websockets.connect(SPOT_WEBSOCKET_TRADE_HOST) as ws:
                    await ws.send(json.dumps(login_params))
                    res = await asyncio.wait_for(ws.recv(), timeout=25)

                    topic = {
                        "action": "sub",
                        "ch": "accounts.update#2"
                        }

                    await ws.send(json.dumps(topic))

                    for sub in self.sub_data_set:
                        inst_id = sub.inst_id.lower()
                        topic = {
                            "action": "sub",
                            "ch": f"orders#{inst_id}"
                            }
                        await ws.send(json.dumps(topic))

                        topic = {
                            "action": "sub",
                            "ch": f"trade.clearing#{inst_id}#0"
                            }
                        await ws.send(json.dumps(topic))
                        

                    while True:
                        try:
                            res = await asyncio.wait_for(ws.recv(), timeout=25)
                        except (asyncio.TimeoutError, websockets.exceptions.ConnectionClosed) as e:
                            try:
                                await ws.send('ping')
                                res = await ws.recv()
                                print(str(datetime.now()) + res)
                                continue
                            except Exception as e:
                                
                                print(str(datetime.now()) + "正在重连……")
                                print(e)
                                break

                        res = json.loads(res)
                        if not self.gateway_ready:
                            self.gateway_ready = True

                        if "action" in res:
                            action = res["action"]
                            if action == "ping":
                                d = {
                                    "action": "pong",
                                    "data": {"ts": res["data"]["ts"]}
                                }
                                await ws.send(json.dumps(d))

                            elif action == "push":
                                ch = res["ch"]
                                data = res["data"]
                                if "order" in ch:
                                    if not "eventType" in data:
                                        # 
                                        self.helper_log_record(f"push channel receive message without eventType: {res}")
                                        continue

                                    eventType = data["eventType"]

                                    if eventType in ["trigger", "deletion"]:
                                        send_return = self.send_return_trans(data)

                                        if self.listener_send_return:
                                            self.listener_send_return(send_return)

                                    elif eventType in ["creation", "trade", "cancellation"]:
                                        
                                        if eventType == "trade":
                                            order = self.order_fill_trans(data)
                                            if self.listener_order:
                                                self.listener_order(order)
                                            
                                            if order.state == orderStateEnum.FILLED:
                                                if order.ord_id in self.order_dict:
                                                    del self.order_dict[order.ord_id]
                                        else:
                                            order = self.order_trans(data)
                                            if self.listener_order:
                                                self.listener_order(order)
                                            
                                            if order.state in [orderStateEnum.PARTIALCANCELED, orderStateEnum.CANCELSUCCEED]:
                                                if order.ord_id in self.order_dict:
                                                    del self.order_dict[order.ord_id]

                                elif "trade" in ch:
                                    fill = self.fill_trans(data)

                                    if self.listener_fill:
                                        self.listener_fill(fill)
                                        
                                elif "accounts.update" in ch:
                                    
                                    if not data:
                                        continue
                                    if not self.gateway_ready:
                                        self.gateway_ready = True
                                    account = self.account_trans(data)
                                    
                                    if self.listener_account:
                                        self.listener_account(account)

                            elif action == "sub":
                                
                                if str(res["code"]) == "500":
                                    raise Exception(f"connection error {res}")
                                elif str(res["code"] == "200"):
                                    self.helper_log_record("sub topic")
                                    self.helper_log_record(res)

                            else:
                                self.helper_log_record("no prepare")
                                self.helper_log_record(res)
                        else:
                            self.helper_log_record('error message ' )
                            self.helper_log_record(res)

            except Exception as e:
                if 'cannot schedule new FUTURES after shutdown' in str(e):
                    pass
                elif 'no running event loop' in str(e):
                    pass
                else:
                    self.helper_log_record(f"ws spot error: {e}")
                    
                    ws_break = wsBreakData()
                    ws_break.gateway_name = self.gateway_name
                    ws_break.exchange_name = self.exchange_name
                    ws_break.break_reason = f"spot channel break: {e}"
                    ws_break.break_time_epoch = int(time.time() * 1000)
                    ws_break.break_time_china = dt_epoch_to_china_str(ws_break.break_time_epoch)
                    if self.listener_ws_break:
                        self.listener_ws_break(ws_break)

                self.gateway_ready = False
                continue

    def send_return_receive(self, request: Request):
        # order return
        data = request.response.json()
        # print(f"request path: {request.path}")
        if "orders/place" in request.path:
            status = data["status"]
            send_return = sendReturnData()
            send_return.gateway_name = self.gateway_name
            send_return.account_name = self.account_name
            send_return.channel = orderChannelEnum.ORDER

            if "client-order-id" in request.data:
                send_return.cl_ord_id = json.loads(request.data)["client-order-id"]

            if status == "ok":
                send_return.ord_id = str(data["data"])
                send_return.msg = ""
                # send_return.ord_state = orderStateEnum.SENDSUCCEED
            else:
                send_return.code = str(data["err-code"])
                send_return.msg = str(data["err-msg"])
                send_return.ord_state = orderStateEnum.SENDFAILED
        elif ("submitcancel" in request.path) or ("submitCancelClientOrder" in request.path):
            status = data["status"]
            send_return = sendReturnData()
            send_return.gateway_name = self.gateway_name
            send_return.account_name = self.account_name
            send_return.channel = orderChannelEnum.CANCELORDER
            if "submitcancel" in request.path:
                ord_id = request.path.split("orders/")[1].split("/submit")[0]
                send_return.ord_id = ord_id
            
            if "client-order-id" in request.data:
                send_return.cl_ord_id = json.loads(request.data)["client-order-id"]
            else:
                if status == "ok":
                    if len(data["data"]) > 5:
                        send_return.ord_id = data['data']

            if status == "ok":
                send_return.msg = ""
                # send_return.ord_state = orderStateEnum.CANCELSUCCEED
            else:
                send_return.code = str(data["err-code"])
                send_return.msg = str(data["err-msg"])
                send_return.ord_state = orderStateEnum.CANCELFAILED
                if str(data["err-code"]) == "not-found" and str(data["err-msg"]) == "not.found (NT)":
                    send_return.msg = cancelOrderError.NOTEXIST
                elif str(data["err-code"]) == "base-not-found" and str(data["err-msg"]) == "The record is not found.":
                    send_return.msg = cancelOrderError.NOTEXIST
                elif str(data["err-code"]) == "order-orderstate-error" and str(data["err-msg"]) == "Incorrect order state":
                    send_return.msg = cancelOrderError.NOTEXIST
                    
        if self.listener_send_return:
            self.listener_send_return(send_return)
    
    def gateway_start(self):
        asyncio.run_coroutine_threadsafe(self.gateway_async(), self.loop)

    ##################trade engine ##############################
    

    ##################send order ##############################
    # this is async send
    def send_order(self, order: orderSendData):
        """
        rest also async, 
        """
        self.async_spot.trade_post_order(
            symbol=order.inst_id,
            type_=order_type_transfer_reverse(order.ord_type, order.side),
            amount=str(order.sz),
            price=str(order.px),
            client_order_id=order.cl_ord_id,
            account_type="spot",
            cb=self.send_return_receive
        )
        return
        
    def cancel_order(self, cancel: cancelOrderSendData):
        if cancel.ord_id:
            self.async_spot.trade_post_cancel_order(
                order_id=cancel.ord_id, 
                cb=self.send_return_receive
                )
        elif cancel.cl_ord_id:
            self.async_spot.trade_post_cancel_order_cliordId(
                client_order_id=cancel.cl_ord_id, 
                cb=self.send_return_receive
                )
        return 
    
    def cancel_batch_order(self, cancel_list: List[cancelOrderSendData]):
        return
    
    def amend_order(self, amend: amendOrderSendData):
        return

    def amend_batch_order(self, amend_list: List[amendOrderSendData]):
        return

    ##################send order ##############################

def create_signature_v2(
    api_key: str,
    method: str,
    host: str,
    path: str,
    secret_key: str,
    get_params=None
) -> Dict[str, str]:
    """
    创建WebSocket接口签名
    """
    
    sorted_params: list = [
        ("accessKey", api_key),
        ("signatureMethod", "HmacSHA256"),
        ("signatureVersion", "2.1"),
        ("timestamp", datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S"))
    ]

    if get_params:
        sorted_params.extend(list(get_params.items()))
        sorted_params = list(sorted(sorted_params))
    encode_params = urllib.parse.urlencode(sorted_params)

    host_name = urllib.parse.urlparse(host + path).hostname
    path_name = urllib.parse.urlparse(host + path).path

    payload: list = [method, host_name, path_name, encode_params]
    payload: str = "\n".join(payload)
    payload: str = payload.encode(encoding="UTF8")

    # print(payload)
    secret_key: str = secret_key.encode(encoding="UTF8")

    digest: bytes = hmac.new(secret_key, payload, digestmod=hashlib.sha256).digest()
    signature: bytes = base64.b64encode(digest)

    params = {}
    params["authType"] = "api"
    params.update(dict(sorted_params))

    params["signature"] = signature.decode("UTF8")
    
    return params

def order_source_transfer(order_source):
    if order_source == "spot-api":
        return instTypeEnum.SPOT
    elif order_source == "margin-api":
        return instTypeEnum.MARGINISOLATED
    elif order_source == "super-margin-api":
        return instTypeEnum.MARGINCROSS

def order_type_transfer(order_type):
    # buy-market, sell-market, 
    # buy-limit, sell-limit, 
    # buy-ioc, sell-ioc, 
    # buy-limit-fok, sell-limit-fok

    if order_type == "buy-market":
        return orderTypeEnum.MARKET, orderSideEnum.BUY
    elif order_type == "sell-market":
        return orderTypeEnum.MARKET, orderSideEnum.SELL
    elif order_type == "buy-limit":
        return orderTypeEnum.LIMIT, orderSideEnum.BUY
    elif order_type == "sell-limit":
        return orderTypeEnum.LIMIT, orderSideEnum.SELL
    elif order_type == "buy-limit-maker":
        return orderTypeEnum.POSTONLY, orderSideEnum.BUY
    elif order_type == "sell-limit-maker":
        return orderTypeEnum.POSTONLY, orderSideEnum.SELL
    elif order_type == "buy-ioc":
        return orderTypeEnum.IOC, orderSideEnum.BUY
    elif order_type == "sell-ioc":
        return orderTypeEnum.IOC, orderSideEnum.SELL
    elif order_type == "buy-limit-fok":
        return orderTypeEnum.FOK, orderSideEnum.BUY
    elif order_type == "sell-limit-fok":
        return orderTypeEnum.FOK, orderSideEnum.SELL

def order_type_transfer_reverse(ord_type: orderTypeEnum, ord_side: orderSideEnum):
    if ord_type == orderTypeEnum.MARKET and ord_side == orderSideEnum.BUY:
        return "buy-market"
    elif ord_type == orderTypeEnum.MARKET and ord_side == orderSideEnum.SELL:
        return "sell-market"
    elif ord_type == orderTypeEnum.LIMIT and ord_side == orderSideEnum.BUY:
        return "buy-limit"
    elif ord_type == orderTypeEnum.LIMIT and ord_side == orderSideEnum.SELL:
        return "sell-limit"
    elif ord_type == orderTypeEnum.POSTONLY and ord_side == orderSideEnum.BUY:
        return "buy-limit-maker"
    elif ord_type == orderTypeEnum.POSTONLY and ord_side == orderSideEnum.SELL:
        return "sell-limit-maker"
    elif ord_type == orderTypeEnum.IOC and ord_side == orderSideEnum.BUY:
        return "buy-ioc"
    elif ord_type == orderTypeEnum.IOC and ord_side == orderSideEnum.SELL:
        return "sell-ioc"
    elif ord_type == orderTypeEnum.FOK and ord_side == orderSideEnum.BUY:
        return "buy-limit-fok"
    elif ord_type == orderTypeEnum.FOK and ord_side == orderSideEnum.SELL:
        return "sell-limit-fok"

def order_state_transfer(order_state):
    if str(order_state) == "-1":
        return orderStateEnum.CANCELSUCCEED
    elif str(order_state) == "1":
        return orderStateEnum.SENDING
    elif str(order_state) == "3":
        return orderStateEnum.SENDSUCCEED
    elif str(order_state) == "4":
        return orderStateEnum.PARTIALFILLED
    elif str(order_state) == "5":
        return orderStateEnum.PARTIALCANCELED
    elif str(order_state) == "6":
        return orderStateEnum.FILLED
    elif str(order_state) == "7":
        return orderStateEnum.CANCELSUCCEED
    elif str(order_state) == "10":
        return orderStateEnum.CANCELING
    else:
        return order_state
    
def account_listener(account: accountData):
    print(f"account: {account.ccy} {account.equity}")

def order_listener(order: orderData):
    print(f"order: {order.cl_ord_id} {order.side} {order.px} {order.sz} {order.state} {order.ord_id} {order}")

def fill_listener(fill: fillData):
    print(f"fill: {fill.fill_px} {fill.fill_sz} {fill.rebate} {fill.rebate_ccy} {fill}")

def send_return_listener(send_return: sendReturnData):
    print(f"send return: {send_return.cl_ord_id} {send_return.ord_state} {send_return.channel} {send_return.msg}")



if __name__ == "__main__":
    from crypto_rest_python.async_rest_client import create_session, start_event_loop
    loop = asyncio.get_event_loop()
    session = loop.run_until_complete(create_session(loop))
    start_event_loop(loop)
    with open("/home/op/wangyun/account_config/huobi/test3.yaml", "r") as f:
        account = yaml.full_load(f)
    # account = load_account_file("huobi/test1")
    gateway = huobiGatewayTradeSpot('test')
    gateway.add_loop_session(loop, session)
    gateway.add_config_account(account)
    gateway.helper_load_exchange_info()
    sub = subData()
    sub.inst_id = 'btcusdt'
    gateway.add_strategy_sub(sub)

    gateway.add_listener_account(account_listener)
    gateway.add_listener_order(order_listener)
    gateway.add_listener_fill(fill_listener)
    gateway.add_listener_send_return(send_return_listener)

    gateway.gateway_start()

    time.sleep(1)

    print(gateway.sync_spot.account_get_uid())
    print(gateway.sync_spot.trade_get_fee(['btcusdt']))
    # print(gateway.sync_spot.account_post_transfer_usdt_margin("spot", "linear-swap", "usdt", 100, "usdt"))
    
    result = gateway.sync_spot.trade_get_open_order(symbol='btcusdt')
    for data in result['data']:
        print(data)
        print(f"\n")
        gateway.sync_spot.trade_post_cancel_order(order_id=data['id'])

    # print(gateway.sync_spot.trade_get_fee(['btcusdt']))
    # cancel = cancelOrderSendData()
    # cancel.cl_ord_id = "btctest"
    

    order = orderSendData()
    order.inst_id='btcusdt'
    order.ord_type=orderTypeEnum.LIMIT
    order.cl_ord_id='btctest'
    order.side="buy"
    order.px=Decimal("30400")
    order.sz=Decimal("0.003")
    # gateway.send_order(order)

    while True:
        time.sleep(100)


    