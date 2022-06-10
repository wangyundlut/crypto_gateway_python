

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
import gzip
import sys

from crypto_gateway_python.gateways.huobi.public_helper import (
    huobi_get_inst_id_local,
    huobi_get_account_ccy,
    huobi_load_usdt_margin_info,
    helper_get_price_usdt_margin
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
from crypto_rest_python.huobi.sync_rest.rest_api_usdt import huobiRestUSDT 
from crypto_rest_python.huobi.async_rest.async_usdt_margin import asyncHuobiUSDTMargin
from crypto_rest_python.huobi.sync_rest.consts import EXCHANGE_NAME, USDT_WEBSOCKET_TRADE_HOST, SPOT_REST_HOST, COIN_FUTURES_HOST

HOURS8=8
ZERODECIMAL = Decimal("0")


class huobiGatewayTradeUsdtMargin(baseGatewayTrade):
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
        
        self.sync_usdt_margin = huobiRestUSDT(key, secret)
        self.async_usdt_margin = asyncHuobiUSDTMargin(key, secret, loop=self.loop, session=self.session)

        return

    def helper_load_exchange_info(self):
        self.inst_id_info = huobi_load_usdt_margin_info()
        return

    ##################load rest##############################

    ##################exchange helper##############################
    """
    get price, 
    """
    def helper_get_price(self, inst_id: str, inst_type: str=""):
        return helper_get_price_usdt_margin(inst_id)
    
    def helper_get_order_info(self,  ord_id: str="", client_order_id: str="") -> orderData:
        if ord_id:
            res = self.sync_usdt_margin.trade_get_order_info(order_id=ord_id)
        elif client_order_id:
            res = self.sync_usdt_margin.trade_get_order_info(client_order_id=client_order_id)

        # transfer
        if res["status"] == "ok":
            result = res["data"][0]
        else:
            self.helper_log_record(f"get order info error: {res}")
            sys.exit()
            
        ########## get from rest ###############
        order = orderData()
        order.gateway_name = self.gateway_name
        order.account_name = self.account_name
        order.exchange = self.exchange_name
        order.inst_type = instTypeEnum.USDTM
        order.inst_id = result["symbol"]
        order.inst_id_local = self.helper_get_inst_id_local(order.inst_id, order.inst_type)
        order.ord_id = result["order_id"]
        order.cl_ord_id = result["client_order_id"]
        order.state = order_state_transfer(result["status"])
        order.px = Decimal(result["price"])
        order.sz = Decimal(result["volume"])
        order.ord_type = order_type_transfer(result["order_price_type"])
        order.side = result["direction"]
        order.fill_sz = Decimal(result["trade_volume"])
        order.fill_px = Decimal(result["trade_turnover"]) / Decimal(result["trade_volume"])
        order.acc_fill_sz = Decimal(0)
        order.avg_px = Decimal(result["trade_avg_price"])
        order.fee = Decimal(result["fee"])
        order.fee_ccy = result["fee_asset"]
        order.create_time_epoch = int(result["created_at"])
        order.create_time_china = dt_epoch_to_china_str(order.create_time_epoch)
        return order
        
    def helper_get_account(self, ccy, inst_id: str, inst_type: str="") -> accountData:
        
        return 
    
    def helper_get_position(self, inst_id: str, inst_type: str="") -> positionData:
        inst_id_local = self.helper_get_inst_id_local(inst_id, inst_type)
        info = self.inst_id_info[inst_id_local]

        pos = positionData()
        pos.gateway_name = self.gateway_name
        pos.account_name = self.account_name
        pos.exchange = self.exchange_name
        pos.inst_type = info.inst_type
        pos.inst_id = inst_id
        pos.inst_id_local = info.inst_id_local
        pos.pos = 0

        res = self.sync_usdt_margin.asset_position(inst_id.upper())
        if res['status'] == "ok":
            if not res["data"]:
                return pos
            res = res["data"][0]
        else:
            self.helper_log_record(f"get position error: {res}")
            sys.exit()

        info = self.inst_id_info[self.helper_get_inst_id_local(inst_id, inst_type)]
        pos = positionData()
        pos.gateway_name = self.gateway_name
        pos.account_name = self.account_name
        pos.exchange = self.exchange_name
        pos.inst_type = info.inst_type
        pos.inst_id = inst_id
        pos.inst_id_local = info.inst_id_local
        pos.open_px = Decimal(str(res["cost_open"]))
        pos.hold_px = Decimal(str(res["cost_hold"]))
        pos.last_price = Decimal(str(res["last_price"]))
        pos.pos = Decimal(str(res["volume"])) if res["direction"] == "buy" else -Decimal(str(res["volume"]))
        pos.direction = res['direction']
        pos.available = Decimal(str(res["available"]))
        pos.frozen = Decimal(str(res["frozen"]))
        pos.update_time_epoch = int(time.time())
        pos.update_time_china = dt_epoch_to_china_str(pos.update_time_epoch)
        return pos

    ##################exchange helper##############################
    def position_trans(self, data):
        contract_code = data["contract_code"]
        inst_id_locl = self.helper_get_inst_id_local(contract_code, instTypeEnum.USDTM)
        info = self.inst_id_info[inst_id_locl]
        pos = positionData()
        pos.gateway_name = self.gateway_name
        pos.account_name = self.account_name
        pos.exchange = self.exchange_name
        pos.inst_type = info.inst_type
        pos.inst_id = contract_code
        pos.inst_id_local = info.inst_id_local
        pos.open_px = Decimal(str(data["cost_open"]))
        pos.hold_px = Decimal(str(data["cost_hold"]))
        pos.last_price = Decimal(str(data["last_price"]))
        pos.pos = Decimal(str(data["volume"])) if data["direction"] == "buy" else -Decimal(str(data["volume"]))
        pos.direction = data['direction']
        pos.available = Decimal(str(data["available"]))
        pos.frozen = Decimal(str(data["frozen"]))
        pos.update_time_epoch = int(data["ts"])
        pos.update_time_china = dt_epoch_to_china_str(pos.update_time_epoch)
        return pos

    ##################trade gateway ##############################
    
    def order_trans(self, data):
        """
        middle engine's listener
        """
        order = orderData()
        order.gateway_name = self.gateway_name
        order.account_name = self.account_name
        order.exchange = self.exchange_name
        order.inst_type = instTypeEnum.USDTM
        order.inst_id = data["contract_code"]
        order.inst_id_local = self.helper_get_inst_id_local(order.inst_id, order.inst_type)
        order.ord_id = str(data["order_id"])
        order.cl_ord_id = str(data["client_order_id"])
        order.state = order_state_transfer(data["status"])
        order.px = Decimal(str(data["price"]))
        order.sz = Decimal(str(data["volume"]))
        order.ord_type = order_type_transfer(data["order_price_type"])
        order.side = data["direction"]
        trades = data['trade']
        if trades:
            trade = trades[-1]
            order.fill_sz = Decimal(str(trade["trade_volume"]))
            order.fill_px = Decimal(str(trade["trade_price"]))
            
        order.acc_fill_sz = Decimal(str(data["trade_volume"]))
        if not data["trade_avg_price"]:
            order.avg_px = None
        else:
            order.avg_px = Decimal(str(data["trade_avg_price"]))
        
        order.fee = Decimal(str(data["fee"]))
        order.fee_ccy = data["fee_asset"]
        order.create_time_epoch = int(data["created_at"])
        order.create_time_china = dt_epoch_to_china_str(order.create_time_epoch)
        return order

    def fill_trans(self, data, res):
        fill = fillData()
        fill.gateway_name = self.gateway_name
        fill.account_name = self.account_name
        fill.exchange = self.exchange_name
        fill.inst_type = instTypeEnum.USDTM
        fill.inst_id = res["contract_code"]
        fill.inst_id_local = self.helper_get_inst_id_local(fill.inst_id, fill.inst_type)
        fill.ord_type = order_type_transfer(res["order_price_type"])
        fill.side = res["direction"]
        fill.ord_id = str(res["order_id"])
        fill.cl_ord_id = str(res["client_order_id"])
        fill.trade_id = str(data["trade_id"])
        fill.taker_or_maker = data["role"]
        fill.fill_px = Decimal(str(data["trade_price"]))
        fill.fill_sz = Decimal(str(data["trade_volume"]))
        return fill

    def account_trans(self, data):
        account = accountData()
        account.gateway_name = self.gateway_name
        account.account_name = self.account_name
        account.exchange = self.exchange_name
        account.ccy = data["margin_asset"]
        account.equity = Decimal(str(data["margin_balance"]))
        account.frozen = Decimal(str(data["margin_frozen"]))
        if not data["risk_rate"]:
            account.account_risk = Decimal(0)
        else:
            account.account_risk = Decimal(str(data["risk_rate"]))
        return account
    
    async def gateway_async(self):
        while True:
            try:
                params_sign = create_signature_v2(self.account_config['key'], "GET", "wss://api.hbdm.com", "/linear-swap-notification", self.account_config['secret'])
                login_params = {
                    "op": "auth",
                    "type": "api",
                    "Signature": params_sign["Signature"],

                    "AccessKeyId": params_sign["AccessKeyId"],
                    "SignatureMethod": "HmacSHA256",
                    "SignatureVersion": "2",
                    "Timestamp": params_sign["Timestamp"],
                }
                async with websockets.connect(USDT_WEBSOCKET_TRADE_HOST) as ws:
                    
                    await ws.send(json.dumps(login_params))

                    res = await asyncio.wait_for(ws.recv(), timeout=25)

                    for sub in self.sub_data_set:
                        inst_id = sub.inst_id.lower()
                        topic = {
                            "op": "sub",
                            "topic": f"orders_cross.{inst_id.upper()}"
                            }
                        self.helper_log_record(topic)
                        await ws.send(json.dumps(topic))
                        topic = {
                            "op": "sub",
                            "topic": f"positions_cross.{inst_id.upper()}",
                            }
                        await ws.send(json.dumps(topic))
                        self.helper_log_record(topic)
                        topic = {                                   
                                "op": "sub",
                                "topic": "accounts_cross.USDT"       
                            } 
                        await ws.send(json.dumps(topic))
                        self.helper_log_record(topic)     

                    while True:
                        try:
                            res = await asyncio.wait_for(ws.recv(), timeout=25)
                        except (asyncio.TimeoutError, websockets.exceptions.ConnectionClosed) as e:
                            try:
                                await ws.send('ping')
                                res = await ws.recv()
                                self.helper_log_record(str(datetime.now()) + res)
                                continue
                            except Exception as e:
                                
                                self.helper_log_record(str(datetime.now()) + "正在重连……")
                                self.helper_log_record(e)
                                break

                        res = json.loads(gzip.decompress(res).decode("utf-8"))
                        
                        op = res["op"]

                        if op == "ping":
                            d = {
                                "op": "pong",
                                "ts": res["ts"]
                            }
                            await ws.send(json.dumps(d))
                            continue
                        elif op == "error":
                            self.helper_log_record(f"sub error: {res}")
                            continue
                        elif op == "sub":
                            self.helper_log_record(f"sub {res}")
                            continue

                        topic = res["topic"]
                        
                        if "positions_cross" in topic:
                            # print(f"{'=' * 50} pos")
                            # print(res)
                            positions = res['data']
                            event = res['event']
                            ts = res["ts"]
                            # if event == "init":
                            for position in positions:
                                position["ts"] = ts
                                pos = self.position_trans(position)
                                if self.listener_position:
                                    self.listener_position(pos)

                        elif "orders_cross" in topic:
                            # print(f"{'=' * 50} order")
                            # self.helper_log_record(f"usdt margin trades")
                            # self.helper_log_record(res["trade"])

                            trades = res['trade']
                            if trades:
                                # order will return only one fill, not all fill.
                                fill = self.fill_trans(trades[-1], res)
                                if self.listener_fill:
                                    self.listener_fill(fill)

                            order = self.order_trans(res)
                            if self.listener_order:
                                self.listener_order(order)
                        elif "accounts_cross" in topic:
                            if not self.gateway_ready:
                                self.gateway_ready = True

                            data = res["data"][0]
                            account = self.account_trans(data)
                            if self.listener_account:
                                self.listener_account(account)
                            
            except Exception as e:
                
                if 'cannot schedule new futures after shutdown' in str(e).lower():
                    self.helper_log_record(f"ws usdt margin error: {e}")
                elif 'no running event loop' in str(e):
                    self.helper_log_record(f"ws usdt margin error: {e}")
                else:
                    self.helper_log_record(f"ws usdt margin error: {e}")
                    
                    ws_break = wsBreakData()
                    ws_break.gateway_name = self.gateway_name
                    ws_break.exchange_name = self.exchange_name
                    ws_break.break_reason = f"margin channel break: {e}"
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
        # print(f"request result: {request.response.json()}")
        # print(f"request data: {request.data}")
        if "/linear-swap-api/v1/swap_cross_order" in request.path:
            status = data["status"]
            send_return = sendReturnData()
            send_return.gateway_name = self.gateway_name
            send_return.account_name = self.account_name
            send_return.channel = orderChannelEnum.ORDER

            if "client_order_id" in request.data:
                send_return.cl_ord_id = json.loads(request.data)["client_order_id"]

            if status == "ok":
                send_return.ord_id = str(data["data"]["order_id"])
                send_return.msg = ""
                # send_return.ord_state = orderStateEnum.SENDSUCCEED
            else:
                if str(data["err_msg"]) == orderError.INSETTLEMENT:
                    send_return.msg = orderError.INSETTLEMENT
                elif str(data["err_msg"]) == orderError.SYSTEMEBUSY:
                    send_return.msg = orderError.SYSTEMEBUSY
                else:
                    send_return.msg = str(data["err_msg"])
                send_return.code = str(data["err_code"])
                send_return.ord_state = orderStateEnum.SENDFAILED
        elif "/linear-swap-api/v1/swap_cross_cancel" in request.path:
            status = data["status"]
            send_return = sendReturnData()
            send_return.gateway_name = self.gateway_name
            send_return.account_name = self.account_name
            send_return.channel = orderChannelEnum.CANCELORDER

            if "order_id" in request.data:
                send_return.ord_id = json.loads(request.data)["order_id"]
            
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
                send_return.code = str(data["err_code"])
                send_return.msg = str(data["err_msg"])
                send_return.ord_state = orderStateEnum.CANCELFAILED

                if str(data['err_code']) == str(1014) and str(data['err_msg']) == "This contract doesnt exist.":
                    self.helper_log_record(f"please confirm the contract {request.data}, sys exit")
                    sys.exit()
                elif str(data["err_code"]) == str(1071) and str(data["err_msg"]) == "Repeated cancellation. Your order has been canceled.":
                    send_return.msg = cancelOrderError.NOTEXIST
                elif str(data["err_code"]) == str(1061) and str(data["err_msg"]) == "This order doesnt exist.":
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
        # self.helper_log_record(f"{'=' * 50}")
        # self.helper_log_record(f"{order}")
        # self.helper_log_record(f"{'=' * 50}")
        self.async_usdt_margin.trade_post_order(
            contract_code=order.inst_id.upper(),
            price=str(order.px),
            volume=int(round(order.sz)),
            direction=order.side,
            order_price_type=order_type_transfer_reverse(order.ord_type),
            client_order_id=order.cl_ord_id,
            cb=self.send_return_receive
        )
        return
        
    def cancel_order(self, cancel: cancelOrderSendData):
        if cancel.ord_id:
            self.async_usdt_margin.trade_post_cancel_order(
                contract_code=cancel.inst_id.upper(),
                order_id=cancel.ord_id,
                cb=self.send_return_receive
            )
        elif cancel.cl_ord_id:
            self.async_usdt_margin.trade_post_cancel_order(
                contract_code=cancel.inst_id.upper(),
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
    
    def get_order_info(self, inst_id: str="", ord_id: str="", cl_ord_id: str="None") -> orderData:
        result = self.sync_usdt_margin.trade_get_order_info(contract_code=inst_id, order_id=ord_id, client_order_id=cl_ord_id)
        if result['status'] != 'ok':
            return None

        data = result['data'][0]
        order = orderData()
        order.gateway_name = self.gateway_name
        order.account_name = self.account_name
        order.exchange = self.exchange_name
        order.inst_type = instTypeEnum.USDTM
        order.inst_id = data["contract_code"]
        order.inst_id_local = self.helper_get_inst_id_local(order.inst_id, order.inst_type)
        order.ord_id = str(data["order_id"])
        order.cl_ord_id = str(data["client_order_id"])
        order.state = order_state_transfer(data["status"])
        order.px = Decimal(str(data["price"]))
        order.sz = Decimal(str(data["volume"]))
        order.ord_type = order_type_transfer(data["order_price_type"])
        order.side = data["direction"]
        order.fill_sz = Decimal(str(data["trade_volume"]))
        if order.fill_sz != Decimal(0):
            order.fill_px = Decimal(str(data["trade_turnover"])) / Decimal(str(data["trade_volume"]))
        else:
            order.fill_px = Decimal(0)
        order.acc_fill_sz = Decimal(0)
        if not data["trade_avg_price"]:
            order.avg_px = None
        else:
            order.avg_px = Decimal(str(data["trade_avg_price"]))
        order.fee = Decimal(str(data["fee"]))
        order.fee_ccy = data["fee_asset"]
        order.create_time_epoch = int(data["created_at"])
        order.create_time_china = dt_epoch_to_china_str(order.create_time_epoch)
        return order
        
    def get_pending_orders(self, contract_code: str, ):
        pass

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
        ("AccessKeyId", api_key),
        ("SignatureMethod", "HmacSHA256"),
        ("SignatureVersion", "2"),
        ("Timestamp", datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S"))
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

    params["Signature"] = signature.decode("UTF8")
    
    return params

def order_source_transfer(order_source):
    if order_source == "spot-api":
        return instTypeEnum.SPOT
    elif order_source == "margin-api":
        return instTypeEnum.MARGINISOLATED
    elif order_source == "super-margin-api":
        return instTypeEnum.MARGINCROSS

def order_type_transfer(order_type):
    # 
    if order_type == "limit":
        return orderTypeEnum.LIMIT
    elif order_type == "opponent":
        return orderTypeEnum.MARKET
    elif order_type == "post_only":
        return orderTypeEnum.POSTONLY
    elif order_type == "fok":
        return orderTypeEnum.FOK
    elif order_type == "ioc":
        return orderTypeEnum.IOC
   
def order_type_transfer_reverse(ord_type):
    if ord_type == orderTypeEnum.MARKET:
        return "opponent"
    elif ord_type == orderTypeEnum.LIMIT:
        return "limit"
    elif ord_type == orderTypeEnum.POSTONLY:
        return "post_only"
    elif ord_type == orderTypeEnum.FOK:
        return "fok"
    elif ord_type == orderTypeEnum.IOC:
        return "ioc"

def order_state_transfer(order_state):
    
    if str(order_state) == "1":
        return orderStateEnum.SENDING
    elif str(order_state) == "2":
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
    elif str(order_state) == "11":
        return orderStateEnum.CANCELING
    else:
        return order_state
    
def account_listener(account: accountData):
    print(f"account: {account.ccy} {account.equity}")

def order_listener(order: orderData):
    print(f"order: {order.cl_ord_id} {order.side} {order.px} {order.sz} {order.state} {order.ord_id} {order}")

def position_listener(pos: positionData):
    print(f"{datetime.now()} :: pos: {pos.inst_id} {pos.account_name} {pos.pos} {pos.direction} {pos.hold_px}")

def send_return_listener(send_return: sendReturnData):
    print(f"send return: {send_return.cl_ord_id} {send_return.ord_state} {send_return.channel} {send_return.msg}")



if __name__ == "__main__":
    from crypto_rest_python.async_rest_client import create_session, start_event_loop
    loop = asyncio.get_event_loop()
    session = loop.run_until_complete(create_session(loop))
    start_event_loop(loop)
    with open("/home/op/wangyun/account_config/huobi/spread1.yaml", "r") as f:
        account = yaml.full_load(f)
    # account = load_account_file("huobi/test1")
    gateway = huobiGatewayTradeUsdtMargin('test')
    gateway.add_loop_session(loop, session)
    gateway.add_config_account(account)
    gateway.helper_load_exchange_info()
    sub = subData()
    sub.inst_id = 'BTC-USDT'
    gateway.add_strategy_sub(sub)

    gateway.add_listener_account(account_listener)
    gateway.add_listener_order(order_listener)
    gateway.add_listener_position(position_listener)
    gateway.add_listener_send_return(send_return_listener)

    gateway.gateway_start()

    time.sleep(1)
    # result = gateway.sync_usdt_margin.asset_fee()
    # for data in result["data"]:
    #     print(data)
    # result = gateway.sync_usdt_margin.trade_switch_position_mode("single_side")
    # cancel = cancelOrderSendData()
    # cancel.inst_id='BTC-USDT'
    # cancel.ord_id=str(979028418916450304)
    # gateway.cancel_order(cancel)
    
    # order = orderSendData()
    # order.inst_id='BTC-USDT'
    # order.px='29780'
    # order.sz=1
    # order.side="buy"
    # order.ord_type=orderTypeEnum.POSTONLY
    # gateway.send_order(order)
    # gateway.get_order_info(contract_code="BTC-USDT", ord_id="979028418916450304")
    # print(gateway.sync_usdt_margin.trade_cancel_all(contract_code="DOGE-USDT"))
    # print(gateway.get_order_info("BTC-USDT", ord_id="979684719081889794"))

    order = orderSendData()
    order.inst_id='btc-usdt'
    order.px='27000'
    order.sz=1
    order.side="buy"
    order.ord_type=orderTypeEnum.POSTONLY
    gateway.send_order(order)
    print(gateway.sync_usdt_margin.asset_balance_valuation())
    
    while True:
        time.sleep(1)
    
    print(gateway.sync_usdt_margin.asset_position())
    print(gateway.sync_usdt_margin.trade_get_openorders())
    print(gateway.sync_usdt_margin.trade_get_openorders("BTC-USDT"))

    # result = gateway.sync_usdt_margin.trade_post_order(
    #     contract_code="BTC-USDT",
    #     price = "28500",
    #     volume="1",
    #     direction="buy",
    #     order_price_type="post_only",
    #     client_order_id="12345"
    # )
    # print(result)
    time.sleep(1)
    result = gateway.sync_usdt_margin.trade_post_cancel_order(
        contract_code="BTC-USDT",
        # order_id="978705392462888960"
        client_order_id="12345"
    )
    print(result)

    
    print()
    print(gateway.sync_usdt_margin.asset_balance_valuation())
    

    # print(gateway.sync_spot.trade_get_fee(['btcusdt']))
    # cancel = cancelOrderSendData()
    # cancel.cl_ord_id = "btctest"
    

    order = orderSendData()
    order.inst_id='BTC-USDT'
    order.ord_type=orderTypeEnum.LIMIT
    order.cl_ord_id='1234'
    order.side="buy"
    order.px=Decimal("30400")
    order.sz=Decimal("0.003")
    # gateway.send_order(order)

    while True:
        time.sleep(100)


    