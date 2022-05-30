

import asyncio
import json
import websockets
import gzip
from datetime import datetime, timedelta
import urllib
import hmac
import base64
import hashlib

import time
from decimal import Decimal
from typing import Dict, List 

from crypto_gateway_python.data_structure.base_gateway import baseGateway
from crypto_gateway_python.data_structure.base_data_struct import (
    accountData,
    depthData,
    instInfoData,
    instTypeEnum,
    orderChannelEnum,
    orderData,
    orderSendData, 
    cancelOrderSendData,
    amendOrderSendData,
    orderSideEnum,
    orderStateEnum,
    orderTypeEnum,
    positionData,
    fillData,
    sendReturnData)

from crypto_rest_python.huobi.sync_rest.rest_api_spot import huobiRestSpot, SPOT_REST_HOST

from crypto_rest_python.huobi.sync_rest.rest_api_spot import huobiRestSpot, SPOT_REST_HOST
from crypto_rest_python.huobi.sync_rest.consts import EXCHANGE_NAME, SPOT_WEBSOCKET_TRADE_HOST, SPOT_WEBSOCKET_DATA_HOST, SPOT_WEBSOCKET_MBP_DATA_HOST
from crypto_gateway_python.utilities.utility_decimal import round_to
from crypto_gateway_python.utilities.utility_time import dt_epoch_to_china_str

class huobiGateway:

    def __init__(self, gateway_name='') -> None:        
        self.gateway_name = gateway_name
        self.listener_depth = None
        self.listener_account = None
        self.listener_position = None
        self.listener_order = None
        self.listener_fill = None
        self.listener_ws = None

        self.rest = None
        self.account_name = ""
        self.symbols_info:Dict[str, instInfoData] = {}
        self.exchange_name = ""
        self.subscribe_symbols = set() # local id
        self.log = None

        self.depth_dict = {} # "btcusdt": {tick}
        self.depth_increase_list = {} # "btcusdt": []}
        self.depth_seq_num = {} # "btcusdt": {tick}
        self.market_ready = False
        self.trade_ready = False

        self.order_dict: Dict[str, orderData] = {} # orderId: order, del if filled, canceled, partial-canceled
        self.account_dict: Dict[str, accountData] = {}

    ##################load rest##############################
    def add_config_account(self, api_key: str="", secret_key: str="", passphrase: str="", account_name: str="test"):
        """
        this is a json or dict
        after add config account, load rest
        """
        self.__api_key = api_key
        self.__secret_key = secret_key
        self.account_name = account_name
        self.load_rest()

    def load_rest(self):
        """
        after load rest, load exchange info
        """
        self.rest = huobiRestSpot(self.__api_key, self.__secret_key)
        self.exchange_name = self.rest.exchange_name

        self.load_exchange_info()

    def load_exchange_info(self):
        result = self.rest.common_symbols()
        for info in result["data"]:
            self.exchange_info_transfer(info)

    def exchange_info_transfer(self, data):
        info = instInfoData()
        info.exchange = self.exchange_name
        info.inst_type = instTypeEnum.SPOT
        info.inst_id = data["sc"]
        info.inst_id_local = self.get_inst_id_local(info.inst_id, info.inst_type)
        info.price_tick = Decimal(str(10 ** (-data["tpp"])))
        info.min_order_sz = Decimal(str(10 ** (-data["tap"])))

        info.base_ccy = data["bc"]
        info.quote_ccy = data["qc"]

        info.con_val = Decimal(1)
        self.symbols_info[info.inst_id_local] = info

    def get_inst_id_local(self, inst_id, inst_type):
        return f"{self.exchange_name}_{inst_type}_{inst_id}"

    def get_inst_ccy_local(self, inst_id, inst_type, ccy, pair: str=""):
        if pair:
            return f"{self.exchange_name}_{inst_type}_{pair}_{ccy}"
        return f"{self.exchange_name}_{inst_type}_{ccy}"

    ##################load rest##############################

    ##################strategy engine add##############################
    def add_inst_id_needed(self, inst_id: str, inst_type: str=""):
        """
        this is a inst_id list need to be listen, maybe one
        """
        inst_id_local = self.get_inst_id_local(inst_id, inst_type)
        self.subscribe_symbols.add(inst_id_local)

        info = self.symbols_info[inst_id_local]
        self.depth_dict[info.inst_id] = {}
        self.depth_increase_list[info.inst_id] = []
        self.depth_seq_num[info.inst_id] = 0

    def add_log(self, log):
        self.log = log

    def log_record(self, msg):
        if self.log:
            # self.log.info(f"gateway: {self.gateway_name}, exchange: {self.exchange_name}, msg:")
            self.log.info(msg)

        else:
            print(f"gateway: {self.gateway_name}, exchange: {self.exchange_name}, msg: {msg}")
    
    ##################exchange helper##############################
    def get_inst_id_price(self, inst_id: str, inst_type: str):
        inst_id_local = self.get_inst_id_local(inst_id, inst_type)
        info = self.symbols_info[inst_id_local]
        result = self.rest.market_ticker(symbol=info.inst_id)
        
        return Decimal(str(result["tick"]["close"]))

    def get_account(self, inst_id: str, inst_type: str, ccy: str, pair: str="") -> accountData:
        inst_id_local = self.get_inst_id_local(inst_id, inst_type)
        info = self.symbols_info[inst_id_local]
        result = self.rest.account_get_balance(info.inst_type)

        trade_frozen = {}
        for li in result["data"]["list"]:
            if li["currency"] == ccy:
                trade_frozen[li["type"]] = li
        
        account = accountData()
        account.gateway_name = self.gateway_name
        account.account_name = self.account_name
        account.exchange = self.exchange_name
        account.ccy = ccy.lower()
        account.ccy_local = self.get_inst_ccy_local(info.inst_id, info.inst_type, ccy.lower())
        account.equity = Decimal(trade_frozen["trade"]["balance"])
        account.debt = Decimal("0")
        account.frozen = Decimal(trade_frozen["frozen"]["balance"])
        account.cash_balance = account.equity
        account.account_risk = Decimal("0")
        account.update_time_epoch = Decimal(int(time.time() * 1000))
        account.update_time_china = dt_epoch_to_china_str(account.update_time_epoch)
        return account

    def get_position(self, inst_id: str, inst_type: str="") -> positionData:
        """
        for spot, it will return 
        """
        pass
    
    def get_info(self, inst_id: str, inst_type: str="") -> instInfoData:
        inst_id_local = self.get_inst_id_local(inst_id, inst_type)
        info = self.symbols_info[inst_id_local]
        return info

    async def send_order(self, order: orderSendData):
        """
        rest also async, 
        """
        pass

    async def send_batch_order(self, order_list: List[orderSendData]):
        pass

    async def cancel_order(self, cancel: cancelOrderSendData):
        pass

    async def cancel_batch_orders(self, cancel_list: List[cancelOrderSendData]):
        pass
    
    async def amend_order(self, amend: amendOrderSendData):
        pass

    async def amend_batch_order(self, amend_list: List[amendOrderSendData]):
        pass
    
    def send_order_rest(self, order: orderSendData) -> sendReturnData:
        """
        rest also async, 
        """
        
        result = self.rest.trade_post_order(
            symbol=order.inst_id,
            type_=order_type_transfer_reverse(order.ord_type, order.side),
            amount=str(order.sz),
            price=str(order.px),
            client_order_id=order.cl_ord_id,
            account_type=order.inst_type
        )
        
        status = result["status"]
        ws_info = sendReturnData()
        ws_info.gateway_name = self.gateway_name
        ws_info.account_name = self.account_name
        ws_info.channel = orderChannelEnum.ORDER

        if status == "ok":
            ws_info.ord_id = str(result["data"])
            ws_info.cl_ord_id = order.cl_ord_id
            ws_info.msg = ""
            ws_info.ord_state = orderStateEnum.SUBMITTED
        else:
            ws_info.code = str(result["err-code"])
            ws_info.msg = str(result["err-msg"])
                
        return ws_info

    def send_batch_order_rest(self, order_list: List[orderSendData]) -> List[sendReturnData]:
        post_list = []
        for order in order_list:
            d = {}
            d["symbol"]=order.inst_id
            d["type"]=order_type_transfer_reverse(order.ord_type, order.side)
            d["amount"]=str(order.sz)
            d["price"]=str(order.px)
            d["client-order-id"]=order.cl_ord_id
            d["account_type"]=order.inst_type
            post_list.append(d)

        result = self.rest.trade_post_batch_order(post_list)

        li = []
        
        for order in result["data"]:
            ws_info = sendReturnData()
            ws_info.gateway_name = self.gateway_name
            ws_info.account_name = self.account_name
            ws_info.channel = orderChannelEnum.BATCHORDERS

            if "order-id" in order:
                ws_info.ord_id = str(order["order-id"])
                ws_info.msg = ""
                ws_info.ord_state = orderStateEnum.SUBMITTED

            if "client-order-id" in order:
                ws_info.cl_ord_id = str(order["client-order-id"])
            
            if "err-code" in order:
                ws_info.code = str(order["err-code"])
                ws_info.msg = str(order["err-msg"])
            
            li.append(ws_info)

        return li

    def cancel_order_rest(self, cancel: cancelOrderSendData) -> sendReturnData:
        if cancel.ord_id:
            result = self.rest.trade_post_cancel_order(cancel.ord_id)
        else:
            result = self.rest.trade_post_cancel_order_cliordId(cancel.cl_ord_id)
        
        ws_info = sendReturnData()
        ws_info.gateway_name = self.gateway_name
        ws_info.account_name = self.account_name
        ws_info.channel = orderChannelEnum.CANCELORDER

        status = result["status"]
        if status == "ok":
            if cancel.ord_id:
                ws_info.ord_id = str(result["data"])
            else:
                ws_info.cl_ord_id = str(result["data"])
        else:
            ws_info.code = str(result["err-code"])
            ws_info.msg = str(result["err-msg"])
        
        return ws_info

    def cancel_batch_orders_rest(self, cancel_list: List[cancelOrderSendData]) -> List[sendReturnData]:
        cancel_ord_list = []
        if cancel_list[0].ord_id != "":
            for cancel_order in cancel_list:
                cancel_ord_list.append(cancel_order.ord_id)

            result = self.rest.trade_post_batch_cancel(order_ids=cancel_ord_list)
        else:
            for cancel_order in cancel_list:
                cancel_ord_list.append(cancel_order.cl_ord_id)

            result = self.rest.trade_post_batch_cancel(client_order_ids=cancel_ord_list)
        li = []
        
        # print(result)
        
        result = result["data"]["success"] + result["data"]["failed"]

        for data in result:
            
            ws_info = sendReturnData()
            ws_info.gateway_name = self.gateway_name
            ws_info.account_name = self.account_name
            ws_info.channel = orderChannelEnum.CANCELORDER
            if "err-code" in data:
                ws_info.code = str(data["err-code"])
                ws_info.msg = str(data["err-msg"])

            if "order-id" in data:
                if data["order-id"]:
                    ws_info.ord_id = str(data["order-id"])
            if "client-order-id" in data:
                if data["client-order-id"]:
                    ws_info.cl_ord_id = str(data["client-order-id"])
            li.append(ws_info)
        return li

    def amend_order_rest(self, amend: amendOrderSendData):
        pass

    def amend_batch_order_rest(self, amend_list: List[amendOrderSendData]):
        pass

    def get_order_info(self, ord_id="", client_order_id="") -> orderData:
        if ord_id:
            result = self.rest.trade_get_order_info(order_id=ord_id)
        elif client_order_id:
            result = self.rest.trade_get_order_info_in_client_order_id(client_order_id=client_order_id)
        # transfer
        
        order = orderData()
        order.gateway_name = self.gateway_name
        order.account_name = self.account_name
        order.exchange = self.exchange_name
        order.inst_type = order_source_transfer(result["source"])
        order.inst_id = result["symbol"]
        order.inst_id_local = self.get_inst_id_local(order.inst_id, order.inst_type)
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

    
    ##################exchange helper##############################

    def get_coroutine_market(self):
        """
        get all gateway coroutines 
        when start gateway ,upper app will start this by different ways
        """
        pass

    def get_coroutine_trade(self):
        pass
    
    def get_engine_status(self):

        return self.market_ready and self.trade_ready

    ##################strategy engine add##############################

    ############## transfer ##############

    def listener_depth_add(self, func):
        self.listener_depth = func

    def listener_account_add(self, func):
        self.listener_account = func
    
    def listener_position_add(self, func):
        self.listener_position = func
    
    def listener_order_add(self, func):
        self.listener_order = func
    
    def listener_fill_add(self, func):
        self.listener_fill = func
    
    def listener_ws_add(self, func):
        self.listener_ws = func
    
    def depth_transfer(self, inst_id: str, inst_type: str=""):
        data = self.depth_dict[inst_id]
        inst_id_local = self.get_inst_id_local(inst_id, inst_type)
        info = self.symbols_info[inst_id_local]

        ts = data["ts"]
        asks = data["asks"]
        bids = data["bids"]
        if not asks or not bids:
            return

        depth = depthData()
        depth.gateway_name = self.gateway_name
        depth.exchange = self.exchange_name
        depth.inst_type = info.inst_type
        depth.inst_id = info.inst_id
        depth.inst_id_local = info.inst_id_local
        depth.time_epoch = Decimal(ts)
        depth.time_china = dt_epoch_to_china_str(ts)
        depth.bid_price_1 = Decimal(str(bids[0][0]))
        depth.bid_volume_1 = Decimal(str(bids[0][1]))
        depth.ask_price_1 = Decimal(str(asks[0][0]))
        depth.ask_volume_1 = Decimal(str(asks[0][1]))
        depth.asks_list = asks
        depth.bids_list = bids
        return depth
        
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
        inst_type = self.rest.get_account_type_from_account_id(data["accountId"])
        if inst_type == "spot":
            account.ccy_local = self.get_inst_ccy_local("", instTypeEnum.SPOT, account.ccy)
        elif inst_type == "margin":
            account.ccy_local = self.get_inst_ccy_local("", instTypeEnum.MARGINISOLATED, account.ccy)
        elif inst_type == "super-margin":
            account.ccy_local = self.get_inst_ccy_local("", instTypeEnum.MARGINCROSS, account.ccy)
        account.equity = Decimal(data["balance"])
        account.debt = Decimal("0")
        account.frozen = Decimal(data["balance"]) - Decimal(data["available"])
        account.cash_balance = Decimal(data["balance"])
        account.account_risk = Decimal("1000")
        if data["changeTime"]:
            account.update_time_epoch = Decimal(data["changeTime"])
        else:
            account.update_time_epoch = Decimal(int(time.time() * 1000))
        account.update_time_china = dt_epoch_to_china_str(account.update_time_epoch)
        return account

    def position_trans(self, position):
        """
        middle engine's listener
        """
        pass

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
        order.inst_id_local = self.get_inst_id_local(order.inst_id, order.inst_type)
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
            order.state = orderStateEnum.SUBMITTED
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
                order.state = orderStateEnum.CANCELED
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
        order.inst_id_local = self.get_inst_id_local(order.inst_id, order.inst_type)
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
        fill.inst_id_local = self.get_inst_id_local(fill.inst_id, fill.inst_type)

        fill.ord_type, fill.side = order_type_transfer(data["orderType"])
        fill.ord_id = data["orderId"]
        fill.cl_ord_id = data["clientOrderId"]
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
        
    def ws_info_trans(self, d: dict):
        ws_info = sendReturnData()
        ws_info.gateway_name = self.gateway_name
        ws_info.account_name = self.account_name
        ws_info.ws_id = ""
        ws_info.channel = orderChannelEnum.ORDER
        ws_info.ord_id = ""
        ws_info.cl_ord_id = d["clientOrderId"]
        # trigger error
        if "errCode" in d:
            ws_info.code = d["errCode"]
            ws_info.msg = d["errMessage"]
        # deletion
        else:
            ws_info.code = d["eventType"]
            ws_info.msg = d["eventType"]
        return ws_info

    async def ws_info_trans(self, d: dict):
        pass

    async def coroutine_market_increase(self):
        """
        depth_dict: save the newest
        depth_dict_refresh: save the fresh 
        depth_dict_increase: save the increase
        1 start depth_dict_increase, save increase
        2 start depth_dict_refresh, save refresh as the newest depth_dict
        3 when found depth_dict, update depth_dict from refresh + increase
        4 update depth_dict if refresh is the newest
        5 update depth_dict if increase is the newest
        6 when market server break down, clear depth_dict
        """
        def update_bids(data, bids_p):
            # 获取增量bids数据
            bids_u = data['bids']
            # print(timestamp + '增量数据bids为：' + str(bids_u))
            # print('档数为：' + str(len(bids_u)))
            # bids合并
            for i in bids_u:
                bid_price = i[0]
                for j in bids_p:
                    if bid_price == j[0]:
                        if i[1] == 0.0:
                            bids_p.remove(j)
                            break
                        else:
                            del j[1]
                            j.insert(1, i[1])
                            break
                else:
                    if i[1] != 0.0:
                        bids_p.append(i)
            else:
                bids_p.sort(key=lambda price: Decimal(str(price[0])), reverse=True)
                # print(timestamp + '合并后的bids为：' + str(bids_p) + '，档数为：' + str(len(bids_p)))
            return bids_p

        def update_asks(data, asks_p):
            # 获取增量asks数据
            asks_u = data['asks']
            # print(timestamp + '增量数据asks为：' + str(asks_u))
            # print('档数为：' + str(len(asks_u)))
            # asks合并
            for i in asks_u:
                ask_price = i[0]
                for j in asks_p:
                    if ask_price == j[0]:
                        if i[1] == 0.0:
                            asks_p.remove(j)
                            break
                        else:
                            del j[1]
                            j.insert(1, i[1])
                            break
                else:
                    if i[1] != 0.0:
                        asks_p.append(i)
            else:
                asks_p.sort(key=lambda price: Decimal(str(price[0])))
                # print(timestamp + '合并后的asks为：' + str(asks_p) + '，档数为：' + str(len(asks_p)))
            return asks_p

        def sort_num(n: str):
            if n.isdigit():
                return int(n)
            else:
                return Decimal(n)

        while True:
            try:
                
                async with websockets.connect(SPOT_WEBSOCKET_MBP_DATA_HOST) as ws:
                    for inst_id_local in self.subscribe_symbols:
                        info = self.symbols_info[inst_id_local]
                        sub_str = {
                            "sub": f"market.{info.inst_id}.mbp.5",
                            "id": "id5"
                        }
                        await ws.send(json.dumps(sub_str))
                        # sub_str = {
                        #     "req": f"market.{info.inst_id}.mbp.150",
                        #     "id": "id6"
                        # }
                        # await ws.send(json.dumps(sub_str))

                    while True:
                        try:
                            res_b = await asyncio.wait_for(ws.recv(), timeout=25)
                        except (asyncio.TimeoutError, websockets.exceptions.ConnectionClosed) as e:
                            try:
                                await ws.send('ping')
                                res = await ws.recv()
                                res = json.loads(gzip.decompress(res_b).decode("utf-8"))
                                
                                continue
                            except Exception as e:
                                break

                        res = json.loads(gzip.decompress(res_b).decode("utf-8"))
                        # self.log_record(f"increase: {res}")
                        if 'tick' in res:
                            if not self.market_ready:
                                self.market_ready = True
                            ch = res['ch']
                            ts = res['ts']
                            tick_symbol = ch.split(".mbp")[0].split("market.")[1]

                            tick_new = res["tick"]
                            tick_new["ts"] = ts
                            # self.log_record(f"increase: {ts}, {tick_symbol}, {tick_new['prevSeqNum']} -> {tick_new['seqNum']}")
                            # not have refresh, or disconnecte
                            
                            if not self.depth_seq_num[tick_symbol]:
                                # self.log_record(f"update by increase, append: {tick_symbol} {tick_new}")
                                self.depth_increase_list[tick_symbol].append(tick_new)
                                continue

                            # update by MBP, continue
                            
                            if self.depth_seq_num[tick_symbol] == tick_new["prevSeqNum"]:
                                self.depth_dict[tick_symbol]["seqNum"] = tick_new["seqNum"]
                                self.depth_dict[tick_symbol]["prevSeqNum"] = tick_new["prevSeqNum"]
                                self.depth_dict[tick_symbol]["ts"] = tick_new["ts"]

                                if "asks" in tick_new:
                                    asks = update_asks(tick_new, self.depth_dict[tick_symbol]["asks"])
                                    self.depth_dict[tick_symbol]["asks"] = asks
                                if "bids" in tick_new:
                                    bids = update_bids(tick_new, self.depth_dict[tick_symbol]["bids"])
                                    self.depth_dict[tick_symbol]["bids"] = bids

                                self.depth_seq_num[tick_symbol] = tick_new["seqNum"]
                                #
                                
                                depth = self.depth_transfer(f"{tick_symbol}", instTypeEnum.SPOT)
                                if not depth:
                                    continue

                                # self.log_record(f"=====update by increase,  {tick_symbol} continue start")
                                # self.log_record(f"{tick_new}")
                                # self.log_record(f"{self.depth_dict[tick_symbol]}")
                                if self.listener_depth:
                                    await self.listener_depth(depth)
                                continue
                            else:
                                self.depth_increase_list[tick_symbol].append(tick_new)
                            # update by MBP, increase + depth
                            for tick_increase in self.depth_increase_list[tick_symbol]:
                                if tick_increase["seqNum"] > self.depth_seq_num[tick_symbol]:
                                    # update
                                    self.depth_dict[tick_symbol]["seqNum"] = tick_increase["seqNum"]
                                    self.depth_dict[tick_symbol]["prevSeqNum"] = tick_increase["prevSeqNum"]
                                    self.depth_dict[tick_symbol]["ts"] = tick_increase["ts"]

                                    if "asks" in tick_increase:
                                        asks = update_asks(tick_increase, self.depth_dict[tick_symbol]["asks"])
                                        self.depth_dict[tick_symbol]["asks"] = asks
                                    if "bids" in tick_increase:
                                        bids = update_bids(tick_increase, self.depth_dict[tick_symbol]["bids"])
                                        self.depth_dict[tick_symbol]["bids"] = bids
                                    self.depth_seq_num[tick_symbol] = tick_increase["seqNum"]

                                    # self.log_record(f"=====update by increase,  {tick_symbol} first time: tick new ")
                                    # self.log_record(f"{tick_increase}")
                                    # self.log_record(f"{self.depth_dict[tick_symbol]}")

                            self.depth_increase_list[tick_symbol] = []

                            # change and push

                            depth = self.depth_transfer(f"{tick_symbol}", instTypeEnum.SPOT)
                            if not depth:
                                continue
                            
                            if self.listener_depth:
                                await self.listener_depth(depth)

                        elif "ping" in res:
                            d = {"pong": res["ping"]}
                            await ws.send(json.dumps(d))
                            # self.log.info(res)
                        else:
                            print(res)
                            # self.log.info(res)

            except Exception as e:
                for key, value in self.depth_dict.items():
                    value = {}
                for key, value in self.depth_increase_list.items():
                    value = []
                for key, value in self.depth_seq_num.items():
                    value = 0
                self.market_ready = False
                self.log_record(f"coroutine_market_increase error: {e}")
                # self.log.info(get_timestmap() + "连接断开，正在重连……" + str(e))
                continue
    
    async def coroutine_market_refresh(self):
        while True:
            try:
                await asyncio.sleep(1)
                async with websockets.connect(SPOT_WEBSOCKET_DATA_HOST) as ws:
                    
                    for inst_id_local in self.subscribe_symbols:
                        info = self.symbols_info[inst_id_local]
                        sub_str = {
                            "sub": f"market.{info.inst_id}.mbp.refresh.5",
                            "id": "id5"
                        }
                        # print(f"send: refresh: {sub_str}")
                        await ws.send(json.dumps(sub_str))

                    while True:
                        try:
                            res_b = await asyncio.wait_for(ws.recv(), timeout=25)
                        except (asyncio.TimeoutError, websockets.exceptions.ConnectionClosed) as e:
                            try:
                                await ws.send('ping')
                                res = await ws.recv()
                                res = json.loads(gzip.decompress(res_b).decode("utf-8"))
                                
                                continue
                            except Exception as e:
                                break

                        res = json.loads(gzip.decompress(res_b).decode("utf-8"))
                        # self.log_record(res)

                        if 'tick' in res:
                            if not self.market_ready:
                                self.market_ready = True
                            ch = res['ch']
                            ts = res['ts']
                            tick = res['tick']
                            tick_symbol = ch.split(".mbp")[0].split("market.")[1]
                            tick["ts"] = ts
                            seqNum = tick["seqNum"]
                            
                            if not self.depth_seq_num[tick_symbol]:
                                self.depth_dict[tick_symbol] = tick
                                self.depth_seq_num[tick_symbol] = seqNum
                                
                                continue
                            else:
                                if seqNum >= self.depth_seq_num[tick_symbol]:

                                    self.depth_dict[tick_symbol]["ts"] = ts
                                    self.depth_dict[tick_symbol]["seqNum"] = seqNum
                                    self.depth_dict[tick_symbol]["asks"] = tick["asks"]
                                    self.depth_dict[tick_symbol]["bids"] = tick["bids"]
                                    
                                    self.depth_seq_num[tick_symbol] = seqNum
                                    
                                    # 
                                    depth = self.depth_transfer(tick_symbol, instTypeEnum.SPOT)

                                    if self.listener_depth:
                                        await self.listener_depth(depth)

                        elif "ping" in res:
                            d = {"pong": res["ping"]}
                            await ws.send(json.dumps(d))

                        else:
                            print(res)
                        

            except Exception as e:
                for key, value in self.depth_dict.items():
                    value = {}
                for key, value in self.depth_increase_list.items():
                    value = []
                for key, value in self.depth_seq_num.items():
                    value = 0
                self.market_ready = True
                self.log_record(f"coroutine_market_refresh error: {e}")
                # self.log.info(get_timestmap() + "连接断开，正在重连……" + str(e))
                continue

    async def coroutine_trade(self):
        while True:
            try:
                params_sign = create_signature_v2(self.__api_key, "GET", SPOT_REST_HOST, "/ws/v2", self.__secret_key)
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

                    for inst_id_local in self.subscribe_symbols:
                        info = self.symbols_info[inst_id_local]
                        topic = {
                            "action": "sub",
                            "ch": f"orders#{info.inst_id}"
                            }
                        await ws.send(json.dumps(topic))

                        topic = {
                            "action": "sub",
                            "ch": f"trade.clearing#{info.inst_id}#0"
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

                        # print(res)
                        res = json.loads(res)
                        # self.log_record(res)
                        # print(res)

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
                                        self.log_record(f"push channel receive message without eventType: {res}")
                                        continue

                                    eventType = data["eventType"]

                                    if eventType in ["trigger", "deletion"]:
                                        ws_info = self.ws_info_trans(data)
                                        # self.log_record(f"{eventType}")
                                        # self.log_record(f"{ws_info}")

                                        if self.listener_ws:
                                            await self.listener_ws(ws_info)

                                    elif eventType in ["creation", "trade", "cancellation"]:
                                        if eventType == "trade":
                                            order = self.order_fill_trans(data)
                                            if self.listener_order:
                                                await self.listener_order(order)
                                            # if self.listener_fill:
                                            #     await self.listener_fill(fill)
                                            # self.log_record(f"{eventType}")
                                            # self.log_record(f"{order}")
                                            # self.log_record(f"{fill}")
                                            # delete if filled, incase memory get more and more
                                            if order.state == orderStateEnum.FILLED:
                                                if order.ord_id in self.order_dict:
                                                    del self.order_dict[order.ord_id]
                                        else:
                                            order = self.order_trans(data)
                                            if self.listener_order:
                                                await self.listener_order(order)
                                            # self.log_record(f"{eventType}")
                                            # self.log_record(f"{order}")
                                            # delete if filled, incase memory get more and more
                                            if order.state in [orderStateEnum.PARTIALCANCELED, orderStateEnum.CANCELED]:
                                                if order.ord_id in self.order_dict:
                                                    del self.order_dict[order.ord_id]

                                elif "trade" in ch:
                                    fill = self.fill_trans(data)
                                    # print("fill")
                                    # print(fill)
                                    if self.listener_fill:
                                        await self.listener_fill(fill)
                                        

                                elif "accounts.update" in ch:
                                    if not data:
                                        continue
                                    if not self.trade_ready:
                                        self.trade_ready = True
                                    account = self.account_trans(data)
                                    # self.log_record(f"account update 2")
                                    # self.log_record(f"{account}")
                                    if self.listener_account:
                                        await self.listener_account(account)

                            elif action == "sub":
                                
                                if str(res["code"]) == "500":
                                    raise Exception(f"connection error {res}")
                                elif str(res["code"] == "200"):
                                    self.log_record("sub topic")
                                    self.log_record(res)
                                    
                            else:
                                self.log_record("no prepare")
                                self.log_record(res)
                        else:
                            self.log_record('error message ' )
                            self.log_record(res)

            except Exception as e:
                self.trade_ready = False
                self.log_record(str(datetime.now()) + " error: coroutine_trade 连接断开，正在重连……" + str(e))
                
                continue

    
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
        return orderStateEnum.CANCELED
    elif str(order_state) == "1":
        return orderStateEnum.CREATED
    elif str(order_state) == "3":
        return orderStateEnum.SUBMITTED
    elif str(order_state) == "4":
        return orderStateEnum.PARTIALFILLED
    elif str(order_state) == "5":
        return orderStateEnum.PARTIALCANCELED
    elif str(order_state) == "6":
        return orderStateEnum.FILLED
    elif str(order_state) == "7":
        return orderStateEnum.CANCELED
    elif str(order_state) == "10":
        return orderStateEnum.CANCELLING
    else:
        return order_state
    

