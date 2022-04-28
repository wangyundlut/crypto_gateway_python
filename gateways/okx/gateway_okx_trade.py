

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

from crypto_gateway_python.gateways.okx.public_helper import (
    okx_get_inst_id_local,
    okx_get_account_ccy,
    okx_load_exchange_info,
    helper_get_price,
    okx_sign,
)
from crypto_gateway_python.utilities.utility_decimal import round_to
from crypto_gateway_python.utilities.utility_time import dt_china_now_str, dt_epoch_to_china_str
from crypto_gateway_python.data_structure.base_gateway import baseGatewayTrade
from crypto_gateway_python.data_structure.base_data_struct import(
    accountData,
    fillData,
    orderStateEnum,
    orderTypeEnum,
    positionData,
    orderData,
    sendReturnData,
    orderChannelEnum,
    instTypeEnum,
    timeOutData,
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

from crypto_rest_python.okx.sync_rest.rest_v5 import okx_api_v5
from crypto_rest_python.okx.sync_rest.consts import (
    EXCHANGE_NAME,
    WS_PRI_URL,
    WS_PRI_URL_SIMULATION,
    WS_PUB_URL,
    WS_PUB_URL_SIMULATION,
)

HOURS8=8
ZERODECIMAL = Decimal("0")




class okxGatewayTrade(baseGatewayTrade):
    def __init__(self, gateway_name='') -> None:
        super(okxGatewayTrade, self).__init__(gateway_name)
        self.exchange_name = EXCHANGE_NAME
        self.websocketPriUrl = WS_PRI_URL
    
    ##################basic log and async function##############################
    
    def helper_get_inst_id_local(self, inst_id: str, inst_type: str=""):
        return okx_get_inst_id_local(inst_id, inst_type)

    def helper_get_account_ccy(self, ccy: str, inst_id: str="", inst_type: str=""):
        return okx_get_account_ccy(ccy, inst_id, inst_type)
    ##################basic log and async function##############################

    ##################load rest##############################
    # okx market is special, depth50, must log in ..
    def add_config_account(self, account_config={
        "exchange": "okx",
        "apiKey": "",
        "passPhrase": "",
        "secretKey": "",
        "isTest": True,
        "account_name": "",
    }):
        """
        this is a json dict
        after add config account, load rest

        exchange: "okx"
        apiKey: ''
        passPhrase: ''
        secretKey: ''
        isTest: True
        account_name: ''
        """
        assert account_config['exchange'] == self.exchange_name

        self.account_config = account_config
        self.account_name = account_config["account_name"]

        isTest = self.account_config['isTest']
        if isTest:
            self.websocketPriUrl = WS_PRI_URL_SIMULATION

        self.rest = okx_api_v5(
            api_key=self.account_config['apiKey'],
            api_secret_key=self.account_config['secretKey'],
            passphrase=self.account_config['passPhrase'],
            test=isTest
        )
        return

    def helper_load_exchange_info(self):
        inst_id_info = okx_load_exchange_info(self.rest)
        self.inst_id_info = inst_id_info
        return

    ##################load rest##############################

    ##################exchange helper##############################
    """
    get price, 
    """
    def helper_get_price(self, inst_id: str, inst_type: str=""):
        return helper_get_price(inst_id, self.rest)
    
    def helper_get_order_info(self, inst_id:str = "", ordId: str="", clOrdId: str="") -> orderData:
        if ordId != "":
            for cl_ord_id, order in self.live_order_data.items():
                if str(ordId) == order.ord_id:
                    return order
        elif clOrdId != "":
            if clOrdId in self.live_order_data:
                return self.live_order_data[clOrdId]
        
        ########## get from rest ###############
        if ordId:
            result = self.rest.trade_get_order_info(instId=inst_id, ordId=ordId)
        elif clOrdId:
            result = self.rest.trade_get_order_info(instId=inst_id, clOrdId=clOrdId)

        if result["msg"] != "":
            self.helper_log_record(f"helper_get_order_info error: {result}")
            return None

        order = self.update_order(result["data"], auto_send=False)
        return order
        
    def helper_get_account(self, ccy, inst_id: str, inst_type: str="") -> accountData:
        inst_id_ccy = self.helper_get_account_ccy(ccy)
        if inst_id_ccy in self.account_data:
            return self.account_data[inst_id_ccy]
        
        ########## get from rest ###############
        result = self.rest.account_get_balance(ccy=ccy.upper())
        
        if result["msg"] != "":
            self.helper_log_record(f"helper_get_account error: {result}")
            return None

        account = self.update_account(result["data"], auto_send=False)
        return account
    
    def helper_get_position(self, inst_id: str, inst_type: str="") -> positionData:
        inst_id_local = self.helper_get_inst_id_local(inst_id, inst_type)
        if inst_id_local in self.position_data:
            return self.position_data[inst_id_local]
        
        ########## get from rest ###############
        result = self.rest.account_get_position(instId=inst_id.upper())

        if result["msg"] != "":
            self.helper_log_record(f"helper_get_position error: {result}")
            return None

        position = self.update_position(result["data"], auto_send=False)
        return position


    ##################exchange helper##############################
    

    ##################trade gateway ##############################
    async def gateway_async(self):
        time_out_max_seconds = 25
        
        def sub_data_str():
            channels_pri = []
            # account listener
            for sub in self.sub_data_set:
                inst_id = sub.inst_id
                inst_type = sub.inst_type
                inst_id_local = self.helper_get_inst_id_local(inst_id, inst_type)
                info = self.inst_id_info[inst_id_local]

                if info.inst_type == instTypeEnum.SPOT:
                    baseCcy = info.base_ccy.upper()
                    channel = {'channel': 'account', 'ccy': baseCcy}
                    channels_pri.append(channel)
                    quoteCcy = info.quote_ccy.upper()
                    channel = {'channel': 'account', 'ccy': quoteCcy}
                    channels_pri.append(channel)
                
                if info.inst_type in [instTypeEnum.FUTURES, instTypeEnum.SWAP]:
                    channel = {'channel': 'positions', 'instType': info.inst_type.upper(), 'instId': info.inst_id.upper()}
                    channels_pri.append(channel)

                channel = {'channel': 'orders', 'instType': info.inst_type.upper(), 'instId': info.inst_id.upper()}
                channels_pri.append(channel)
            
            return json.dumps({"op": "subscribe", "args": channels_pri})

        def get_time_out_data():
            todata = timeOutData()
            todata.gateway_name = self.gateway_name
            todata.exchange_name = self.exchange_name
            todata.event = "private channel not receive data long time."
            todata.send_time_china = dt_china_now_str()
            todata.time_delay = time_out_max_seconds
            return todata

        self.helper_log_record(f"{self.account_name}, private_coroutine,  start ...")
        
        while True:
            try:
                async with websockets.connect(self.websocketPriUrl) as self.ws:
                    # login

                    timestamp = str(round(int(1000 * datetime.timestamp(datetime.now()))/1000, 3))

                    sign = okx_sign(timestamp, self.account_config["secretKey"])

                    login_dict = {
                        'op': 'login', 'args': 
                        [
                            {'apiKey': self.account_config["apiKey"], 
                            'passphrase': self.account_config["passPhrase"], 
                            'timestamp': timestamp, 
                            'sign': sign
                            }
                        ]
                    }
                    self.helper_log_record(f"{self.account_name} , send login params.")
                    await self.ws.send(json.dumps(login_dict))
                    res = await self.ws.recv()
                    self.helper_log_record(f"{self.account_name} , send login receive: {res}")
                    sub_data = sub_data_str()
                    self.helper_log_record(f"{self.account_name} ,send subscribe: {sub_data}")
                    await self.ws.send(sub_data)
                    self.gateway_ready = True

                    while True:
                        try:
                            res = await asyncio.wait_for(self.ws.recv(), timeout=time_out_max_seconds)
                        except (asyncio.TimeoutError, websockets.exceptions.ConnectionClosed) as e:
                            try:
                                if self.listener_time_out:
                                    self.listener_time_out(get_time_out_data())

                                await self.ws.send('ping')
                                res = await self.ws.recv()
                                continue
                            except Exception as e:
                                # time = datetime.now()
                                self.helper_log_record(f"{datetime.now()} 正在重连…… {e}")
                                break

                        res = json.loads(res)

                        if 'event' in res.keys():
                            self.helper_log_record(f"{self.account_name} ,event : {res}")
                            continue

                        # this is ws send order/cancel order/amend order
                        elif 'id' in res.keys():
                            self.update_send_return(res)
                            
                        elif 'arg' in res.keys():
                            channel = res['arg']['channel']
                            data = res['data']
                            if channel == 'account':
                                self.update_account(data, auto_send=True)
                            elif channel == 'positions':
                                self.update_position(data, auto_send=True)
                            elif channel == 'orders':
                                self.update_fill(data, auto_send=True)
                                self.update_order(res, auto_send=True)
                            else:
                                self.helper_log_record("gateway receive other")
                                print(res) 

            except Exception as e:
                if 'cannot schedule new FUTURES after shutdown' in str(e):
                    pass
                elif 'no running event loop' in str(e):
                    pass
                else:
                    self.helper_log_record(f"{self.gateway_name}, private 连接断开,正在重连…… {e}")
                
                self.ws = None
                self.gateway_ready = False
                continue
    
    def gateway_start(self):
        asyncio.run_coroutine_threadsafe(self.gateway_async(), self.loop)
        asyncio.run_coroutine_threadsafe(self.send_data_time_pass(), self.loop)
    
    def update_account(self, data, auto_send=True):
        
        account = data[0]
        details = account['details']

        for detail in details:
    
            account_data = accountData()
            account_data.gateway_name = self.gateway_name
            account_data.account_name = self.account_name
            account_data.exchange = self.exchange_name
            account_data.ccy = detail["ccy"].lower()
            account_data.ccy_local = self.helper_get_account_ccy(detail["ccy"])
            # TODO
            account_data.asset = Decimal(detail["eq"])
            account_data.debt = Decimal(detail["liab"])
            account_data.equity = Decimal(detail["cashBal"])
            account_data.frozen = Decimal(detail["frozenBal"])
            account_data.interest = Decimal(detail["interest"])

            if not detail["mgnRatio"]:
                account_data.account_risk = Decimal("0")
            else:
                account_data.account_risk = Decimal(1) / Decimal(detail["mgnRatio"])

            account_data.update_time_epoch = Decimal(account['uTime'])
            account_data.update_time_china = dt_epoch_to_china_str(account['uTime'])

            self.account_data[account_data.ccy_local] = account_data
            
            if auto_send:
                if self.listener_account:
                    self.listener_account(account_data)

            return account_data

    def update_position(self, data, auto_send=True):
        
        for position in data:
            instId = position["instId"]
        
            inst_id_local = self.helper_get_inst_id_local(instId)
            info = self.inst_id_info[inst_id_local]
        
            position_data = positionData()
            position_data.gateway_name = self.gateway_name
            position_data.account_name = self.account_name
            position_data.exchange = self.exchange_name
            position_data.inst_type = info.inst_type
            position_data.inst_id = info.inst_id
            position_data.inst_id_local = inst_id_local
            position_data.avg_px = ZERODECIMAL if not position['avgPx'] else Decimal(position['avgPx'])
            position_data.last_price = ZERODECIMAL if not position['last'] else Decimal(position['last'])
            position_data.pos = ZERODECIMAL if not position['pos'] else Decimal(position['pos'])

            position_data.update_time_epoch = Decimal(position['uTime'])
            position_data.update_time_china = dt_epoch_to_china_str(position['uTime'])

            self.position_data[position_data.inst_id_local] = position_data
            if auto_send:
                if self.listener_position:
                    self.listener_position(position_data)
        return position_data

    def update_order(self, data, auto_send=True):
        
        for order in data:
            instId = order['instId']
            inst_id_local = self.helper_get_inst_id_local(instId)
            info = self.inst_id_info[inst_id_local]

            order_data = orderData()
            order_data.gateway_name = self.gateway_name
            order_data.account_name = self.account_name
            order_data.exchange = self.exchange_name
            order_data.inst_type = info.inst_type
            order_data.inst_id = info.inst_id
            order_data.inst_id_local = inst_id_local

            order_data.ord_id = order['ordId']
            order_data.cl_ord_id = order['clOrdId']
            
            if order['state'] == "live":
                order_data.state = orderStateEnum.SENDSUCCEED
            elif order['state'] == "partially_filled":
                order_data.state = orderStateEnum.PARTIALFILLED
            elif order['state'] == "filled":
                order_data.state = orderStateEnum.FILLED
            elif order['state'] == "canceled":
                order_data.state = orderStateEnum.CANCELSUCCEED
            
            order_data.px = ZERODECIMAL if not order['px'] else Decimal(order['px'])
            order_data.sz = ZERODECIMAL if not order['sz'] else Decimal(order['sz'])
            order_data.pnl = ZERODECIMAL if not order['pnl'] else Decimal(order['pnl'])
            order_data.ord_type = order['ordType']
            order_data.side = order['side']
            order_data.fill_px = ZERODECIMAL if not order['fillPx'] else Decimal(order['fillPx'])
            order_data.fill_sz = ZERODECIMAL if not order['fillSz'] else Decimal(order['fillSz'])
            order_data.acc_fill_sz = ZERODECIMAL if not order['accFillSz'] else Decimal(order['accFillSz'])
            
            order_data.avg_px = ZERODECIMAL if not order['avgPx'] else Decimal(order['avgPx'])
            order_data.fee_ccy = order['feeCcy'].lower()
            order_data.fee = ZERODECIMAL if not order['fee'] else Decimal(order['fee'])
            order_data.rebate_ccy = order['rebateCcy'].lower()
            order_data.rebate = ZERODECIMAL if not order['rebate'] else Decimal(order['rebate'])
            order_data.update_time_epoch = Decimal(order['uTime'])
            order_data.update_time_china = dt_epoch_to_china_str(order['uTime'])
            order_data.create_time_epoch = Decimal(order['cTime'])
            order_data.create_time_china = dt_epoch_to_china_str(order['cTime'])
            
            if order_data.state in [orderStateEnum.CANCELSUCCEED, orderStateEnum.FILLED]:
                if order_data.cl_ord_id in self.live_order_data:
                    del self.live_order_data[order_data.cl_ord_id]
            else:
                self.live_order_data[order_data.cl_ord_id] = order_data

            if auto_send:
                if self.listener_order:
                    self.listener_order(order_data)

        return order_data

    def update_send_return(self, res):
        #### process send time out ####
        ws_id = res["id"]
        if ws_id in self.check_time_out_data:
            time_now = int(time.time() * 1000)
            time_delay = time_now - self.check_time_out_data[ws_id]
            if time_delay < 1000:
                del self.check_time_out_data[ws_id]
        #### process send time out ####

        send_return = sendReturnData()
        send_return.gateway_name = self.gateway_name
        send_return.exchange_name = self.exchange_name
        send_return.account_name = self.account_name
        send_return.ws_id = res["id"]

        if res["op"] in  ["order", "cancel-order", "amend-order"]:
            if res["op"] == "order":
                send_return.channel = orderChannelEnum.ORDER
            elif res["op"] == "cancel-order":
                send_return.channel = orderChannelEnum.CANCELORDER
            elif res["op"] == "amend-order":
                send_return.channel = orderChannelEnum.AMENDORDER
            send_return.ord_id = res["data"][0]["ordId"]
            send_return.cl_ord_id = res["data"][0]["clOrdId"]
            send_return.code = res["data"][0]["sCode"]

            if res["data"][0]["sMsg"] == "Cancellation failed as the order does not exist.":
                send_return.msg = cancelOrderError.NOTEXIST
            elif res["data"][0]["sMsg"] == "Duplicated client order ID":
                send_return.msg = orderError.DUPLICATECLIORDID
            else:
                send_return.msg = res["data"][0]["sMsg"]

            if self.listener_send_return:
                self.listener_send_return(send_return)
            return

        if res["op"] in ["batch-orders", "batch-cancel-orders", "batch-amend-orders"]:
            for data in res["data"]:
                send_return_copy = deepcopy(send_return)
                if res["op"] == "batch-orders":
                    send_return_copy.channel = orderChannelEnum.BATCHORDERS
                elif res["op"] == "batch-cancel-orders":
                    send_return_copy.channel = orderChannelEnum.BATCHCANCELORDERS
                elif res["op"] == "batch-amend-orders":
                    send_return_copy.channel = orderChannelEnum.BATCHAMENDORDERS
                send_return_copy.ord_id = data["ordId"]
                send_return_copy.cl_ord_id = data["clOrdId"]
                send_return_copy.code = data["sCode"]
                
                if res["data"][0]["sMsg"] == "Cancellation failed as the order does not exist.":
                    send_return_copy.msg = cancelOrderError.NOTEXIST
                elif res["data"][0]["sMsg"] == "Duplicated client order ID":
                    send_return_copy.msg = orderError.DUPLICATECLIORDID
                else:
                    send_return_copy.msg = res["data"][0]["sMsg"]

                if self.listener_send_return:
                    self.listener_send_return(send_return_copy)
            
        return

    def update_fill(self, data, auto_send=True):
        for order in data:

            if not order['fillSz']:
                continue

            if Decimal(order['fillSz']) == Decimal(0):
                continue
            
            instId = order['instId']
            inst_id_local = self.helper_get_inst_id_local(instId)
            info = self.inst_id_info[inst_id_local]

            fill = fillData()
            fill.gateway_name = self.gateway_name
            fill.account_name = self.account_name
            fill.exchange = self.exchange_name
            fill.inst_type = info.inst_type
            fill.inst_id = info.inst_id
            fill.inst_id_local = inst_id_local

            fill.ord_type = order['ordType']
            fill.side = order["side"]
            fill.ord_id = order["ordId"]
            fill.cl_ord_id = order["clOrdId"]
            fill.bill_id = ""
            fill.trade_id = order["tradeId"] if "tradeId" in order else ""
            fill.tag = order['tag']
            fill.taker_or_maker = "maker" if order['rebate'] else "taker"
            fill.fill_px = Decimal(order['fillPx'])
            fill.fill_sz = Decimal(order['fillSz'])
            fill.fee_ccy = order['feeCcy'].lower()
            fill.fee = ZERODECIMAL if not order['fee'] else Decimal(order['fee'])
            fill.rebate_ccy = order['rebateCcy'].lower()
            fill.rebate = ZERODECIMAL if not order['rebate'] else Decimal(order['rebate'])
            fill.time_epoch = Decimal(order['uTime'])
            fill.time_china = dt_epoch_to_china_str(order['uTime'])
            
            if auto_send:
                if self.listener_fill:
                    self.listener_order(fill)
            return


    ##################trade engine ##############################
    

    ##################send order ##############################
    # this is async send
    # for okx check time out, base on ws_id not clOrdId
    def send_order(self, order: orderSendData):
        async def send():
            args = {
                "clOrdId": order.cl_ord_id,
                "side": order.side,
                "instId": order.inst_id.upper(),
                "tdMode": "cross",
                "ordType": order.ord_type,
                "sz": str(order.sz),
                "px": str(order.px)
            }

            if order.ord_type == orderTypeEnum.MARKET:
                del args["px"]

            d = {
                "id": str(order.ws_id),
                "op": "order",
                "args": [args]
                }

            if not self.ws:
                self.helper_log_record(f"not have ws_private, return!")
                return

            self.check_time_out_data[order.ws_id] = int(time.time() * 1000)
            await self.ws.send(json.dumps(d))
            

            return

        asyncio.run_coroutine_threadsafe(send(), self.loop)

    def send_batch_order(self, order_list: List[orderSendData]):
        async def send():
            li = []
            ws_id = ""
            for order in order_list:
                if (not ws_id) and (order.ws_id != ""):
                    ws_id = order.ws_id
                    self.check_time_out_data[order.ws_id] = int(time.time() * 1000)

                args = {
                    "clOrdId": order.cl_ord_id,
                    "side": order.side,
                    "instId": order.inst_id.upper(),
                    "tdMode": "cross",
                    "ordType": order.ord_type,
                    "sz": str(order.sz),
                    "px": str(order.px)
                }

                if order.ord_type == orderTypeEnum.MARKET:
                    del args["px"]

                li.append(args)

            if not self.ws:
                self.helper_log_record(f"not have ws_private, return, send_batch_ioc_order return!")
                return

            d = {
                "id": ws_id,
                "op": "batch-orders",
                "args": li
                }
            
            await self.ws.send(json.dumps(d))
            
            return

        asyncio.run_coroutine_threadsafe(send(), self.loop)

    def cancel_order(self, cancel: cancelOrderSendData):
        async def send():
            args = {}
            args["instId"] = cancel.inst_id.upper()
            if cancel.ord_id:
                args["ordId"] = cancel.ord_id
            elif cancel.cl_ord_id:
                args["clOrdId"] = cancel.cl_ord_id
            d = {
                "id": cancel.ws_id,
                "op": "cancel-order",
                "args": [args]}
            
            self.check_time_out_data[cancel.ws_id] = int(time.time() * 1000)
            await self.ws.send(json.dumps(d))
            return
        asyncio.run_coroutine_threadsafe(send, self.loop)

    def cancel_batch_order(self, cancel_list: List[cancelOrderSendData]):
        async def send():
            args = {}
            args_list = []
            ws_id: str = ""
            for cancel in cancel_list:
                if (not ws_id) and (cancel.ws_id != ""):
                    ws_id = cancel.ws_id
                    self.check_time_out_data[cancel.ws_id] = int(time.time() * 1000)

                args = {}
                args["instId"] = cancel.inst_id.upper()
                if cancel.ord_id:
                    args["ordId"] = cancel.ord_id
                elif cancel.cl_ord_id:
                    args["clOrdId"] = cancel.cl_ord_id
                args_list.append(args)

            d = {
                "id": ws_id,
                "op": "batch-cancel-orders",
                "args": args_list
            }
            await self.ws.send(json.dumps(d))
            return

        asyncio.run_coroutine_threadsafe(send, self.loop)
    
    def amend_order(self, amend: amendOrderSendData):
        async def send():
            args = {}
            args["instId"] = amend.inst_id.upper()
            if amend.new_sz:
                args["newSz"] = str(amend.new_sz)
            if amend.new_px:
                args["newPx"] = str(amend.new_px)
            if amend.ord_id:
                args["ordId"] = str(amend.ord_id)
            elif amend.cl_ord_id:
                args["clOrdId"] = str(amend.cl_ord_id)
            d = {
                "id": amend.ws_id,
                "op": "amend-order",
                "args": [args]
            }
            self.check_time_out_data[amend.ws_id] = int(time.time() * 1000)
            await self.ws.send(json.dumps(d))
            return

        asyncio.run_coroutine_threadsafe(send, self.loop)

    def amend_batch_order(self, amend_list: List[amendOrderSendData]):
        async def send():
            args = {}
            args_list = []
            ws_id: str = ""
            for amend in amend_list:
                if (not ws_id) and (amend.ws_id != ""):
                    ws_id = amend.ws_id
                    self.check_time_out_data[amend.ws_id] = int(time.time() * 1000)

                args["instId"] = amend.inst_id.upper()
                if amend.new_sz:
                    args["newSz"] = str(amend.new_sz)
                if amend.new_px:
                    args["newPx"] = str(amend.new_px)

                if amend.ord_id:
                    args["ordId"] = str(amend.ord_id)
                elif amend.cl_ord_id:
                    args["clOrdId"] = str(amend.cl_ord_id)

                args_list.append(args)
                
            d = {
                "id": ws_id,
                "op": "batch-amend-orders",
                "args": args_list
            }
            await self.ws.send(json.dumps(d))     
            return

        asyncio.run_coroutine_threadsafe(send, self.loop)
    # this is async send

    # this is sync send
    def send_order_sync(self, order: orderSendData) -> sendReturnData:
        """
        rest also async, 
        """

        result = self.rest.trade_post_order(
            instId=order.inst_id,
            side=order.side,
            ordType=order.ord_type,
            sz=order.sz,
            px=order.px
        )

        send_return = sendReturnData()
        send_return.gateway_name = self.gateway_name
        send_return.exchange_name = self.exchange_name
        send_return.account_name = self.account_name
        send_return.channel = orderChannelEnum.ORDER

        send_return.receive_time_epoch = int(time.time() * 1000)
        send_return.receive_time_china = dt_epoch_to_china_str(send_return.receive_time_epoch)

        data = data = result["data"][0]

        if data["sMsg"] != "":
            send_return.ord_state = orderStateEnum.SENDFAILED
            send_return.code = data["sCode"]
            send_return.msg = data["sMsg"]
            return send_return
        
        send_return.ord_id = data["ordId"]
        send_return.cl_ord_id = data["clOrdId"]
        return send_return

    def send_batch_order_sync(self, order_list: List[orderSendData]) -> sendReturnData:
        pass

    def cancel_order_sync(self, cancel: cancelOrderSendData) -> sendReturnData:
        if cancel.ord_id:
            orderId = cancel.ord_id
        else:
            orderId = None
            
        if cancel.cl_ord_id:
            clOrdId = cancel.cl_ord_id
        else:
            clOrdId = None
        
        result = self.rest.trade_post_cancel_order(
            instId=cancel.inst_id,
            ordId=orderId,
            clOrdId=clOrdId
        )

        send_return = sendReturnData()
        send_return.gateway_name = self.gateway_name
        send_return.exchange_name = self.exchange_name
        send_return.account_name = self.account_name
        send_return.channel = orderChannelEnum.CANCELORDER

        send_return.receive_time_epoch = int(time.time() * 1000)
        send_return.receive_time_china = dt_epoch_to_china_str(send_return.receive_time_epoch)

        data = data = result["data"][0]

        if data["sMsg"] != "":
            send_return.ord_state = orderStateEnum.SENDFAILED
            send_return.code = data["sCode"]
            send_return.msg = data["sMsg"]
            return send_return
        
        send_return.ord_id = data["ordId"]
        send_return.cl_ord_id = data["clOrdId"]
        return send_return

    def cancel_batch_orders_sync(self, cancel_list: List[cancelOrderSendData]) -> sendReturnData:
        pass
    
    def amend_order_sync(self, amend: amendOrderSendData) -> sendReturnData:
        pass

    def amend_batch_order_sync(self, amend_list: List[amendOrderSendData]) -> sendReturnData:
        pass
    # this is sync send
    ##################send order ##############################









    