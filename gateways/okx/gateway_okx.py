

import asyncio
from typing import Dict, List
from datetime import datetime, timedelta
import zlib
import websockets
import json
import hmac
import base64
import logging
from decimal import Decimal


from crypto_gateway_python.utilities.utility_decimal import round_to
from crypto_gateway_python.utilities.utility_time import dt_epoch_to_china_str
from crypto_gateway_python.data_structure.base_gateway import baseGateway
from crypto_gateway_python.data_structure.base_data_struct import(
    depthData,
    accountData,
    fillData,
    orderStateData,
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

class okxGateway(baseGateway):
    """
    this is gateway for okx
    update 2022 02
    this is for Multi-currency margin and Portfolio margin
    """

    def __init__(self, gateway_name='') -> None:
        super(okxGateway, self).__init__(gateway_name)
        ##################### listener #####################
        self.listener_depth = None
        self.listener_account = None
        self.listener_position = None
        self.listener_order = None
        self.listener_fill = None
        self.listener_send = None
        ##################### listener #####################

        self.exchange_name = EXCHANGE_NAME
        # public data 
        self.instrument_info :Dict[str, instInfoData]= {}
        self.depth_dict: Dict[str, depthData] = {}
        self.depth_dict_helper = {}
        self.price_limit_dict = {}
        self.fee_dict = {}
        # private data
        self.account_dict: Dict[str, accountData] = {}
        self.account_dict_helper = {}
        self.account_dict_helper['details'] = {}
        self.positions_dict: Dict[str, positionData] = {}
        self.positions_dict_helper = {}
        # only save active order
        self.orders_dict: Dict[str, orderData] = {}
        self.orders_dict_helper = {}

        self.market_depth_listener = None
        self.private_account_listener = None
        self.okx_private_position_listener = None
        self.okx_private_order_listener = None

        self.websocketPubUrl = WS_PUB_URL
        self.websocketPriUrl = WS_PRI_URL

        # websocket ws
        self.ws_public = None
        self.ws_public_ready = False
        self.ws_private = None
        self.ws_private_ready = False
        
        self.subscribe_pub_str = ""
        self.subscribe_pri_str = ""

        self.inst_id_set = set()

        self.apiKey = ''
        self.secretKey = ''
        self.passPhrase = ''
        self.account_name = ''
        self.isTest = False

        self.log:logging.Logger = None
    
    ##################load rest##############################
    def add_config_account(self, config):
        # config -> load rest
        assert config['exchange'] == self.exchange_name
        self.apiKey = config['apiKey']
        self.secretKey = config['secretKey']
        self.passPhrase = config['passPhrase']
        self.account_name = config['account_name']
        self.isTest = config['isTest']
        if self.isTest:
            self.websocketPubUrl = WS_PUB_URL_SIMULATION
            self.websocketPriUrl = WS_PRI_URL_SIMULATION

        self.rest = okx_api_v5(
            self.apiKey, 
            self.secretKey, 
            self.passPhrase, 
            test=self.isTest)
        self.load_exchange_info()
    
    def load_exchange_info(self):
        rest = self.rest

        result = rest.public_get_instruments(instTypeData.SPOT.upper())
        datas = result['data']
        for data in datas:
            data['ctVal'] = "1"
            info = self.exchange_info_transfer(data)
            self.instrument_info[info.inst_id_local] = info
            
        result = rest.public_get_instruments(instTypeData.SWAP.upper())
        for data in result["data"]:
            info = self.exchange_info_transfer(data)
            self.instrument_info[info.inst_id_local] = info
        
        result = rest.public_get_instruments(instTypeData.FUTURES.upper())
        for data in result["data"]:
            info = self.exchange_info_transfer(data)
            self.instrument_info[info.inst_id_local] = info
        return

    def exchange_info_transfer(self, data):
        info = instInfoData()
        info.exchange = EXCHANGE_NAME
        info.inst_type = data["instType"].lower()
        instId = data["instId"]
        info.inst_id = instId
        info.inst_id_local = self.get_inst_id_local(instId)

        info.base_ccy = data["baseCcy"].lower()
        info.quote_ccy = data["quoteCcy"].lower()

        info.underlying = data["uly"].lower()
        if info.inst_type in [instTypeData.FUTURES, instTypeData.SWAP]:
            if data["ctValCcy"].lower() == "usd":
                info.con_type = contractTypeData.USD
            else:
                info.con_type = contractTypeData.COIN
        info.con_val = Decimal(data["ctVal"])
        info.con_val_ccy = data["ctValCcy"].lower()
        info.price_tick = Decimal(data["tickSz"])
        info.min_order_sz = Decimal(data["minSz"])
        return info
        
    def get_inst_id_local(self, inst_id: str, inst_type: str = ""):
        # for okx, all products can be distinct by inst_id
        return f"{self.exchange_name}_{inst_id.lower()}"
    
    def get_ccy_local(self, inst_id: str="", inst_type: str="", ccy: str="", pair: str=""):
        
        return f"{self.exchange_name}_{ccy.lower()}"

    ##################load rest##############################
    ##################strategy engine add##############################
    def add_inst_id_needed(self, inst_id: str, inst_type: str=""):
        # for okx, all inst_id is upper
        inst_id_local = self.get_inst_id_local(inst_id)
        self.inst_id_set.add(inst_id_local)

    def add_log(self, log: logging.Logger):
        self.log = log
    
    def log_record(self, msg):
        if self.log:
            self.log.info(f"{self.gateway_name}: {msg}")
        else:
            print(f"{datetime.now()} {self.gateway_name}: {msg}")
    ##################strategy engine add##############################
    ############## okx ##############

    def parse_subscribe_channels(self):
        # for public
        channels_pub = []
        for inst_id_local in self.inst_id_set:
            # depth
            info = self.instrument_info[inst_id_local]
            channel = {'channel': 'books50-l2-tbt', 'instId': info.inst_id.upper()}
            channels_pub.append(channel)
            # price-limit
            if info.inst_type in [instTypeData.FUTURES, instTypeData.SWAP]:
                channel = {'channel': 'price-limit', 'instId': info.inst_id.upper()}
                channels_pub.append(channel)
        self.subscribe_pub_str = json.dumps({"op": "subscribe", "args": channels_pub})

        channels_pri = []
        # account listener
        for inst_id_local in self.inst_id_set:
            info = self.instrument_info[inst_id_local]
            if info.inst_type == instTypeData.SPOT:
                baseCcy = info.base_ccy.upper()
                channel = {'channel': 'account', 'ccy': baseCcy}
                channels_pri.append(channel)
                quoteCcy = info.quote_ccy.upper()
                if quoteCcy != "USDT":
                    channel = {'channel': 'account', 'ccy': quoteCcy}
                    channels_pri.append(channel)
            channel = {'channel': 'account', 'ccy': 'USDT'}
            channels_pri.append(channel)

            if info.inst_type in [instTypeData.FUTURES, instTypeData.SWAP]:
                channel = {'channel': 'positions', 'instType': info.inst_type.upper(), 'instId': info.inst_id.upper()}
                channels_pri.append(channel)

            channel = {'channel': 'orders', 'instType': info.inst_type.upper(), 'instId': info.inst_id.upper()}
            channels_pri.append(channel)
        # channels_pri.append({'channel': 'balance_and_position'})
        self.subscribe_pri_str = json.dumps({"op": "subscribe", "args": channels_pri})

    def get_inst_id_price(self, inst_id: str, inst_type: str=""):
        inst_id_local = self.get_inst_id_local(inst_id)
        info = self.instrument_info[inst_id_local]

        if inst_id_local in self.depth_dict:
            # 
            ask_price = self.depth_dict[inst_id_local].ask_price_1
            bid_price = self.depth_dict[inst_id_local].bid_price_1
            middle_price = Decimal("0.5") * (ask_price + bid_price)
            return bid_price
        else:
            result = self.rest.market_get_ticker(instId=info.inst_id.upper())
            return Decimal(result['data'][0]['last'])

    def get_account(self, inst_id: str, inst_type: str, ccy: str) -> accountData:
        ccy = ccy.upper()
        inst_ccy_local = self.get_ccy_local("", "", ccy)
        print(f"get account {inst_id} {inst_type} {ccy}")

        if inst_ccy_local in self.account_dict:
            return self.account_dict[inst_ccy_local]
        
        result = self.rest.account_get_balance(ccy)
        data = result["data"][0]
        details = data["details"]
        if len(details) == 0:
            acc = accountData()
            acc.gateway_name = self.gateway_name
            acc.account_name = self.account_name
            acc.exchange = self.exchange_name
            acc.ccy = ccy.lower()
            acc.ccy_local = inst_ccy_local
            return acc

        for key, value in data.items():
            if key == "details":
                continue
            self.account_dict_helper[key] =  value
        for detail in details:
            self.account_dict_helper["details"][detail["ccy"]] = detail
            return self.account_trans(ccy)

    def get_position(self, inst_id: str, inst_type: str=""):
        inst_id = inst_id.upper()
        inst_id_local = self.get_inst_id_local(inst_id)
        info = self.instrument_info[inst_id_local]

        if inst_id_local in self.positions_dict:
            return self.positions_dict[inst_id_local]
        else:
            result = self.rest.account_get_position(instId = info.inst_id.upper())

            if len(result["data"]) == 0:
                pos = positionData()
                pos.gateway_name = self.gateway_name
                pos.account_name = self.account_name
                pos.exchange = self.exchange_name
                pos.inst_type = info.inst_type
                pos.inst_id = info.inst_id
                pos.inst_id_local = info.inst_id_local
                return pos
            data = result["data"][0]
            self.positions_dict_helper[data["instId"]] = data
            return self.position_trans(inst_id)

    def get_info(self, inst_id: str, inst_type: str=""):
        inst_id_local = self.get_inst_id_local(inst_id)
        return self.instrument_info[inst_id_local]
    
    async def send_order(self, order: orderSendData):
        # check price limit 
        inst_id_local = self.get_inst_id_local(order.inst_id)
        # order.sz_change(self.instrument_info[inst_id_local])

        d = {
            "id": str(order.ws_id),
            "op": "order",
            "args": [{
                "clOrdId": order.cl_ord_id,
                "side": order.side,
                "instId": order.inst_id.upper(),
                "tdMode": "cross",
                "ordType": order.ord_type,
                "sz": str(order.sz),
                "px": str(order.px)
            }]
            }
        if not self.ws_private:
            self.log_record(f"not have ws_private, return, send_ioc_order return!")
            return
        # print(f"send order: {d}")
        await self.ws_private.send(json.dumps(d))
    
    async def send_batch_order(self, order_list: List[orderSendData]):
        
        li = []
        ws_id = ""
        for order in order_list:
            if (not ws_id) and (order.ws_id != ""):
                ws_id = order.ws_id

            inst_id_local = self.get_inst_id_local(order.inst_id)
            # order.sz_change(self.instrument_info[inst_id_local])

            li.append({
                "clOrdId": order.cl_ord_id,
                "side": order.side,
                "instId": order.inst_id.upper(),
                "tdMode": "cross",
                "ordType": order.ord_type,
                "sz": str(order.sz),
                "px": str(order.px)
            })

        if not self.ws_private:
            self.log_record(f"not have ws_private, return, send_batch_ioc_order return!")
            return

        d = {
            "id": ws_id,
            "op": "batch-orders",
            "args": li}
        # self.log_record(f"gateway send batch order {d}")
        await self.ws_private.send(json.dumps(d))
    
    async def cancel_order(self, cancel: cancelOrderSendData):
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
        await self.ws_private.send(json.dumps(d))    
        
    async def cancel_batch_orders(self, cancel_list: List[cancelOrderSendData]):
        args = {}
        args_list = []
        ws_id: str = ""
        for cancel in cancel_list:
            if (not ws_id) and (cancel.ws_id != ""):
                ws_id = cancel.ws_id
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
        await self.ws_private.send(json.dumps(d))

    async def amend_order(self, amend: amendOrderSendData):
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
        # print(f"gateway okx: send amend order: {d}")
        await self.ws_private.send(json.dumps(d))

    async def amend_batch_order(self, amend_list: List[amendOrderSendData]):
        args = {}
        args_list = []
        ws_id: str = ""
        for amend in amend_list:
            if (not ws_id) and (amend.ws_id != ""):
                ws_id = amend.ws_id
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
        await self.ws_private.send(json.dumps(d))     

    def start_coroutine_market(self):
        asyncio.run_coroutine_threadsafe(self.market_coroutine(), self.loop)
        # return self.market_coroutine()
    
    def start_coroutine_trade(self):
        asyncio.run_coroutine_threadsafe(self.private_coroutine(), self.loop)
        # return self.private_coroutine()

    def get_engine_status(self):
        # use and ,both ready will return True
        return self.ws_public_ready and self.ws_private_ready

    def depth_trans(self, instId: str) -> depthData:
        inst_id_local = self.get_inst_id_local(instId)
        orderbooks = self.depth_dict_helper[instId]
        info = self.instrument_info[inst_id_local]
        
        depth_data = depthData()
        depth_data.gateway_name = self.gateway_name
        depth_data.exchange = self.exchange_name
        depth_data.inst_type = info.inst_type
        depth_data.inst_id = info.inst_id
        depth_data.inst_id_local = info.inst_id_local
        depth_data.time_epoch = Decimal(orderbooks['ts'])
        depth_data.time_china = dt_epoch_to_china_str(orderbooks['ts'])
        depth_data.bid_price_1 = Decimal(orderbooks['bids_p'][0][0])
        depth_data.bid_volume_1 = Decimal(orderbooks['bids_p'][0][1])
        depth_data.ask_price_1 = Decimal(orderbooks['asks_p'][0][0])
        depth_data.ask_volume_1 = Decimal(orderbooks['asks_p'][0][1])
        asks_list = []
        bids_list = []
        for asks in orderbooks["asks_p"]:
            asks_list.append([asks[0], asks[1]])
        for bids in orderbooks["bids_p"]:
            bids_list.append([bids[0], bids[1]])
        depth_data.asks_list = asks_list
        depth_data.bids_list = bids_list        

        self.depth_dict[inst_id_local] = depth_data

        return depth_data

    def account_trans(self, ccy: str) -> accountData:
        detail = self.account_dict_helper["details"][ccy]
        ccy_local = self.get_ccy_local("", "", ccy)
        
        account_data = accountData()
        account_data.gateway_name = self.gateway_name
        account_data.account_name = self.account_name
        account_data.exchange = self.exchange_name
        account_data.ccy = ccy.lower()
        account_data.ccy_local = ccy_local

        account_data.equity = Decimal(detail["eq"])
        account_data.debt = Decimal(detail["liab"])
        account_data.frozen = Decimal(detail["frozenBal"])
        account_data.cash_balance = Decimal(detail['cashBal'])
        if not detail["mgnRatio"]:
            account_data.account_risk = Decimal("10000")
        else:
            account_data.account_risk = Decimal(detail["mgnRatio"])

        account_data.update_time_epoch = Decimal(self.account_dict_helper['uTime'])
        account_data.update_time_china = dt_epoch_to_china_str(self.account_dict_helper['uTime'])

        self.account_dict[ccy_local] = account_data

        return account_data

    def position_trans(self, instId: str) -> positionData:
        position = self.positions_dict_helper[instId]
        inst_id_local = self.get_inst_id_local(instId)
        info = self.instrument_info[inst_id_local]
        
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

        self.positions_dict[inst_id_local] = position_data
        return position_data

    def order_trans(self, ordId: str) -> orderData:
        order = self.orders_dict_helper[ordId]
        # self.log_record(f'gateway order: {order}')
        # self.log_record(order)
        # self.log_record(order['state'])

        instId = order['instId']
        inst_id_local = self.get_inst_id_local(instId)
        info = self.instrument_info[inst_id_local]

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
            order_data.state = orderStateData.SENDSUCCEED
        elif order['state'] == "partially_filled":
            order_data.state = orderStateData.PARTIALFILLED
        elif order['state'] == "filled":
            order_data.state = orderStateData.FILLED
        elif order['state'] == "canceled":
            order_data.state = orderStateData.CANCELSUCCEED
        
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
        
        if order_data.state in [orderStateData.CANCELSUCCEED, orderStateData.FILLED]:
            if order_data.ord_id in self.orders_dict_helper:
                del self.orders_dict_helper[order_data.ord_id]
            if order_data.ord_id in self.orders_dict:
                del self.orders_dict[order_data.ord_id]
        else:
            self.orders_dict[order_data.ord_id] = order_data

        return order_data

    def fill_trans(self, order: orderData) -> fillData:
        instId = order['instId']
        inst_id_local = self.get_inst_id_local(instId)
        info = self.instrument_info[inst_id_local]

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
        return fill

    async def send_return_trans(self, d: dict) -> sendReturnData:
        if d["op"] in  ["order", "cancel-order", "amend-order"]:
            send_return = sendReturnData()
            send_return.gateway_name = self.gateway_name
            send_return.account_name = self.account_name
            send_return.ws_id = d["id"]
            if d["op"] == "order":
                send_return.channel = orderChannelData.ORDER
            elif d["op"] == "cancel-order":
                send_return.channel = orderChannelData.CANCELORDER
            elif d["op"] == "amend-order":
                send_return.channel = orderChannelData.AMENDORDER
            send_return.ord_id = d["data"][0]["ordId"]
            send_return.cl_ord_id = d["data"][0]["clOrdId"]
            send_return.code = d["data"][0]["sCode"]

            if d["data"][0]["sMsg"] == "Cancellation failed as the order does not exist.":
                send_return.msg = cancelOrderError.NOTEXIST
            elif d["data"][0]["sMsg"] == "Duplicated client order ID":
                send_return.msg = orderError.DUPLICATECLIORDID
            else:
                send_return.msg = d["data"][0]["sMsg"]

            await self.listener_send(send_return)

        elif d["op"] in ["batch-orders", "batch-cancel-orders", "batch-amend-orders"]:
            for data in d["data"]:
                send_return = sendReturnData()
                send_return.gateway_name = self.gateway_name
                send_return.account_name = self.account_name
                send_return.ws_id = d["id"]
                if d["op"] == "batch-orders":
                    send_return.channel = orderChannelData.BATCHORDERS
                elif d["op"] == "batch-cancel-orders":
                    send_return.channel = orderChannelData.BATCHCANCELORDERS
                elif d["op"] == "batch-amend-orders":
                    send_return.channel = orderChannelData.BATCHAMENDORDERS
                send_return.ord_id = data["ordId"]
                send_return.cl_ord_id = data["clOrdId"]
                send_return.code = data["sCode"]
                
                if d["data"][0]["sMsg"] == "Cancellation failed as the order does not exist.":
                    send_return.msg = cancelOrderError.NOTEXIST
                elif d["data"][0]["sMsg"] == "Duplicated client order ID":
                    send_return.msg = orderError.DUPLICATECLIORDID
                else:
                    send_return.msg = d["data"][0]["sMsg"]
                await self.listener_send(send_return)
        return

    async def market_coroutine(self):
        
        def get_timestamp():
            # now = datetime.now()
            # t = now.isoformat("T", "milliseconds")
            # return t + "Z"
            return str(datetime.now())

        def partial(data):
            bids = data['bids']
            asks = data['asks']
            # instrument_id = data_obj['instrument_id']
            # print(timestamp + '全量数据bids为：' + str(bids))
            # print('档数为：' + str(len(bids)))
            # print(timestamp + '全量数据asks为：' + str(asks))
            # print('档数为：' + str(len(asks)))
            return bids, asks

        def update_bids(data, bids_p, timestamp=None):
            # 获取增量bids数据
            bids_u = data['bids']
            # print(timestamp + '增量数据bids为：' + str(bids_u))
            # print('档数为：' + str(len(bids_u)))
            # bids合并
            for i in bids_u:
                bid_price = i[0]
                for j in bids_p:
                    if bid_price == j[0]:
                        if i[1] == '0':
                            bids_p.remove(j)
                            break
                        else:
                            del j[1]
                            j.insert(1, i[1])
                            break
                else:
                    if i[1] != "0":
                        bids_p.append(i)
            else:
                bids_p.sort(key=lambda price: sort_num(price[0]), reverse=True)
                # print(timestamp + '合并后的bids为：' + str(bids_p) + '，档数为：' + str(len(bids_p)))
            return bids_p

        def update_asks(data, asks_p, timestamp=None):
            # 获取增量asks数据
            asks_u = data['asks']
            # print(timestamp + '增量数据asks为：' + str(asks_u))
            # print('档数为：' + str(len(asks_u)))
            # asks合并
            for i in asks_u:
                ask_price = i[0]
                for j in asks_p:
                    if ask_price == j[0]:
                        if i[1] == '0':
                            asks_p.remove(j)
                            break
                        else:
                            del j[1]
                            j.insert(1, i[1])
                            break
                else:
                    if i[1] != "0":
                        asks_p.append(i)
            else:
                asks_p.sort(key=lambda price: sort_num(price[0]))
                # print(timestamp + '合并后的asks为：' + str(asks_p) + '，档数为：' + str(len(asks_p)))
            return asks_p

        def sort_num(n):
            if n.isdigit():
                return int(n)
            else:
                return Decimal(n)

        def check(bids, asks):
            # 获取bid档str
            bids_l = []
            bid_l = []
            count_bid = 1
            while count_bid <= 25:
                if count_bid > len(bids):
                    break
                bids_l.append(bids[count_bid-1])
                count_bid += 1
            for j in bids_l:
                str_bid = ':'.join(j[0 : 2])
                bid_l.append(str_bid)
            # 获取ask档str
            asks_l = []
            ask_l = []
            count_ask = 1
            while count_ask <= 25:
                if count_ask > len(asks):
                    break
                asks_l.append(asks[count_ask-1])
                count_ask += 1
            for k in asks_l:
                str_ask = ':'.join(k[0 : 2])
                ask_l.append(str_ask)
            # 拼接str
            num = ''
            if len(bid_l) == len(ask_l):
                for m in range(len(bid_l)):
                    num += bid_l[m] + ':' + ask_l[m] + ':'
            elif len(bid_l) > len(ask_l):
                # bid档比ask档多
                for n in range(len(ask_l)):
                    num += bid_l[n] + ':' + ask_l[n] + ':'
                for l in range(len(ask_l), len(bid_l)):
                    num += bid_l[l] + ':'
            elif len(bid_l) < len(ask_l):
                # ask档比bid档多
                for n in range(len(bid_l)):
                    num += bid_l[n] + ':' + ask_l[n] + ':'
                for l in range(len(bid_l), len(ask_l)):
                    num += ask_l[l] + ':'

            new_num = num[:-1]
            int_checksum = zlib.crc32(new_num.encode())
            fina = change(int_checksum)
            return fina

        def change(num_old):
            num = pow(2, 31) - 1
            if num_old > num:
                out = num_old - num * 2 - 2
            else:
                out = num_old
            return out

        self.log_record(f"{self.exchange_name}, market_coroutine, start ...")

        while True:
            try:

                async with websockets.connect(self.websocketPubUrl) as self.ws_public:
                    self.parse_subscribe_channels()
                    self.log_record(f"{self.exchange_name}, market_coroutine, send: {self.subscribe_pub_str}")
                    await self.ws_public.send(self.subscribe_pub_str)

                    while True:
                        try:
                            res = await asyncio.wait_for(self.ws_public.recv(), timeout=25)
                        except (asyncio.TimeoutError, websockets.exceptions.ConnectionClosed) as e:
                            try:
                                await self.ws_public.send('ping')
                                res = await self.ws_public.recv()
                                continue
                            except Exception as e:
                                timestamp = get_timestamp()
                                print(f"{timestamp} market channel 正在重连…… error: {e}")
                                break

                        res = json.loads(res)
                        
                        if 'event' in res:
                            # check if depth checksum error ..
                            self.log_record(f"event res: {res}")
                            if res['event'] == 'unsubscribe':
                                if res['arg']['channel'] == 'books50-l2-tbt':
                                    subscribe = {
                                        "op": "subscribe", "args": [{"channel": "books50-l2-tbt", "instId": res['arg']['instId']}]
                                    }
                                    await self.ws_public.send(json.dumps(subscribe))
                            continue

                        channel = res['arg']['channel']
                        
                        if channel == 'books50-l2-tbt':
                            arg = res['arg']
                            instId = arg['instId']
                            action = res['action']
                            data = res['data'][0]

                            # 订阅频道是深度频道
                            # 全量
                            if action == 'snapshot':
                                self.depth_dict_helper[instId] = {}
                                # for m in l:
                                #     if instId == m['instId']:
                                #         l.remove(m)
                                # 获取首次全量深度数据
                                bids_p, asks_p = partial(data)
                                d = {}
                                d['instId'] = instId
                                d['bids_p'] = bids_p
                                d['asks_p'] = asks_p
                                d['checksum'] = data['checksum']
                                d['ts'] = data['ts']
                                self.depth_dict_helper[instId] = d
                                # l.append(d)

                                # 校验checksum
                                checksum = data['checksum']
                                check_num = check(bids_p, asks_p)

                                if check_num == checksum:
                                    self.log_record(f"{instId} 校验结果为: True snapshot  Done")
                                else:
                                    self.log_record(f"{instId} 校验结果为: False, 正在重新订阅……")
   
                                    ################### unsubscribe ###################
                                    unsubscribe = {
                                        "op": "unsubscribe", "args": [{"channel": "books50-l2-tbt", "instId": instId}]
                                    }
                                    self.log_record(unsubscribe)
                                    await self.ws_public.send(json.dumps(unsubscribe))
                                self.ws_public_ready = True
                                continue

                            if action != 'update':
                                continue

                            orderbooks = self.depth_dict_helper[instId]
                            # 获取全量数据
                            bids_p = orderbooks['bids_p']
                            asks_p = orderbooks['asks_p']
                            # 获取合并后数据
                            orderbooks['bids_p'] = update_bids(data, orderbooks['bids_p'])
                            orderbooks['asks_p'] = update_asks(data, orderbooks['asks_p'])
                            orderbooks['checksum'] = data['checksum']
                            orderbooks['ts'] = data['ts']
                            # 校验checksum
                            checksum = data['checksum']
                            # print(timestamp + '推送数据的checksum为：' + str(checksum))
                            check_num = check(bids_p, asks_p)
                            # print(timestamp + '校验后的checksum为：' + str(check_num))
                            # if miss depth
                            
                            if check_num != checksum:
                                self.log_record(f"{instId} 校验结果为: False, 正在重新订阅……")
                                
                                ################### unsubscribe ###################
                                unsubscribe = {
                                    "op": "unsubscribe", "args": [{"channel": "books50-l2-tbt", "instId": instId}]
                                }
                                self.log_record(unsubscribe)
                                await self.ws_public.send(json.dumps(unsubscribe))
                                continue
                            
                            okx_depth = self.depth_trans(instId)
                            # for okx depth, this will be depth async
                            await self.listener_depth(okx_depth)

                        elif channel == 'price-limit':
                            arg = res['arg']
                            instId = arg['instId']
                            data = res['data'][0]
                            inst_id_local = self.get_inst_id_local(instId)
                            self.price_limit_dict[inst_id_local] = data
                            """
                            "instId": "LTC-USD-190628",
                            "buyLmt": "300",
                            "sellLmt": "200",
                            "ts": "1597026383085"
                            """
                            # await self.middle_engine.okx_price_limit_listener(data)
            except Exception as e:
                self.ws_public_ready = False

                if 'cannot schedule new FUTURES after shutdown' in str(e):
                    pass
                elif 'no running event loop' in str(e):
                    pass
                else:
                    self.log_record(f"{self.exchange_name}, {self.gateway_name}, {self.exchange_name} subscribe_market_data error: {e}")
                # print(timestamp + f" subscribe_market_data error: {e}")
                self.ws_public = None
                continue

    async def private_coroutine(self):

        def get_okx_sign(timestamp, secret_key):
            message = timestamp + 'GET' + '/users/self/verify'

            mac = hmac.new(bytes(secret_key, encoding='utf8'), bytes(message, encoding='utf-8'), digestmod='sha256')
            d = mac.digest()
            sign = base64.b64encode(d)
            return sign.decode("utf-8")

        self.log_record(f"{self.exchange_name}, {self.gateway_name}, private_coroutine, {self.account_name}, start ...")
        
        while True:
            try:
                async with websockets.connect(self.websocketPriUrl) as ws:
                    # login

                    timestamp = str(round(int(1000 * datetime.timestamp(datetime.now()))/1000, 3))

                    sign = get_okx_sign(timestamp, self.secretKey)

                    login_dict = {'op': 'login', 'args': [{'apiKey': self.apiKey, 
                                                        'passphrase': self.passPhrase, 
                                                        'timestamp': timestamp, 
                                                        'sign': sign}]
                                                        }
                    self.log_record(f"{self.account_name} , send login params.")
                    await ws.send(json.dumps(login_dict))
                    res = await ws.recv()
                    self.log_record(f"{self.account_name} , send login receive: {res}")

                    # after websocket break, restart 
                    self.ws_private = ws
                    # subscribe
                    self.parse_subscribe_channels()
                    
                    self.log_record(f"{self.account_name} ,send subscribe: {self.subscribe_pri_str}")
                    await ws.send(self.subscribe_pri_str)
                    self.ws_private_ready = True

                    while True:
                        try:
                            res = await asyncio.wait_for(ws.recv(), timeout=25)
                        except (asyncio.TimeoutError, websockets.exceptions.ConnectionClosed) as e:
                            try:
                                await ws.send('ping')
                                res = await ws.recv()
                                # time = datetime.now()
                                # self.log_record(f"{time} res")
                                continue
                            except Exception as e:
                                # time = datetime.now()
                                self.log_record(f"{datetime.now()} 正在重连……")
                                self.log_record(e)
                                break

                        res = json.loads(res)

                        if 'event' in res.keys():
                            self.log_record(f"{self.account_name} ,event : {res}")
                            continue

                        # this is ws send order/cancel order/amend order
                        elif 'id' in res.keys():
                            # self.log_record('gateway ws info')
                            # self.log_record(res)
                            # after transfer push
                            await self.send_return_trans(res)

                        elif 'arg' in res.keys():
                            arg = res['arg']
                            channel = arg['channel']
                            data = res['data']

                            if channel == 'account':
                                # self.log_record('account')
                                # details only update when the coin changed
                                # account change

                                ## account part, and details part
                                account = data[0]
                                details = account['details']
                                if not ("details" in self.account_dict_helper):
                                    self.account_dict_helper["details"] = {}
                                for detail in details:
                                    self.account_dict_helper["details"][detail["ccy"]] = detail

                                for key, value in account.items():
                                    if key == 'details':
                                        continue
                                    self.account_dict_helper[key] = value
                                
                                for detail in details:
                                    ccy = detail["ccy"]
                                    account_data = self.account_trans(ccy)
                                    await self.listener_account(account_data)
                                    
                            elif channel == 'positions':
                                # self.log_record('positions')
                                for position in data:
                                    self.positions_dict_helper[position['instId']] = position
                                
                                for position in data:
                                    instId = position["instId"]
                                    position_data = self.position_trans(position)
                                    await self.listener_position(position_data)
                            
                            elif channel == 'orders':
                                # self.log_record("gateway receive orders")
                                # self.log_record(data)
                                for order in data:
                                    ordId = order["ordId"]
                                    self.orders_dict_helper[ordId] = order
                                    order_data = self.order_trans(ordId)
                                    if order_data.fill_sz:
                                        fill_data = self.fill_trans(order)
                                        if self.listener_fill:
                                            await self.listener_fill(fill_data)
                                    await self.listener_order(order_data)

                            else:
                                print("gateway receive other")
                                print(res) 

            except Exception as e:
                if 'cannot schedule new FUTURES after shutdown' in str(e):
                    pass
                elif 'no running event loop' in str(e):
                    pass
                else:
                    self.log_record(f"{self.gateway_name}, private 连接断开,正在重连…… {e}")
                # API Request Error(error_code=None): System error
                # server rejected WebSocket connection: HTTP 503
                self.ws_private = None
                self.ws_private_ready = False
                # self.restart_redis()
                # websocket break 之后
                continue
    
    def cancel_batch_orders_sync(self, cancel_list: List[cancelOrderSendData]) -> List[sendReturnData]:
        post_list = []
        for cancel_order in cancel_list:
            d = {}
            if cancel_order.ord_id:
                d["instId"] = cancel_order.inst_id.upper()
                d["ordId"] = cancel_order.ord_id
                post_list.append(d)
            elif cancel_order.cl_ord_id:
                d['instId'] = cancel_order.inst_id.upper()
                d['clOrdId'] = cancel_order.cl_ord_id
                post_list.append(d)
            
        result = self.rest.trade_post_cancel_batch_orders(post_list)
        ret = []

        for data in result['data']:
            send_return = sendReturnData()
            send_return.gateway_name = self.gateway_name
            send_return.account_name = self.account_name
            send_return.channel = orderChannelData.BATCHORDERS
            if data["clOrdId"]:
                send_return.cl_ord_id = data["clOrdId"]
            if data["ordId"]:
                send_return.ord_id = data["ordId"]
            if data["sCode"]:
                send_return.code = data["sCode"]
            if data["sMsg"]:
                send_return.msg = data["sMsg"]
            ret.append(send_return)
        return ret

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
        
        return 
    
    def send_order_sync(self, order: orderSendData) -> sendReturnData:
        
        if order.px:
            px=str(order.px)
        else:
            px=None
        result = self.rest.trade_post_order(
            instId=order.inst_id,
            side=order.side,
            ordType=order.ord_type,
            sz=order.sz,
            px=px
        )
        # result - > send return info
        return 


################ exchange helper ################  

def okx_timestr():
    # get okx string format
    now = datetime.utcnow()
    t = now.isoformat("T", "milliseconds") + "Z"
    return t

def okx_timestamp():
    # okx的时间戳是  +8 也就是 香港/新加坡时间 北京时间
    now = int((datetime.utcnow() + timedelta(hours=HOURS8)).timestamp() * 1000)
    return now

def okx_login_ts():
    timestamp = round(int(1000 * datetime.timestamp(datetime.now()))/1000, 3)
    return str(timestamp)

def exch_to_local(time_exchange: str or int):
    # 交易所的时间 -> 本地的时间 str -> datetime
    # time_local = datetime.utcfromtimestamp(int(time_exchange / 1000))
    time_local = datetime.utcfromtimestamp(int(time_exchange) / 1000)
    time_local = time_local.replace(tzinfo=None)
    time_local = time_local + timedelta(hours=HOURS8)
    # time_local = CHINA_TZ.localize(time_local)
    return time_local

def local_to_exch(time_local: datetime):
    # 本地的时间 ->交易所的时间 datetime -> str
    time_utc = time_local - timedelta(hours=HOURS8)
    stamp_utc = int(time_utc.timestamp() * 1000)
    time_exchange = stamp_utc + HOURS8 * 3600 * 1000
    return time_exchange

def local_time_str(time_local: datetime):
    # 本地时间 -> 数据库时间 datetime ->
    return time_local.strftime("%Y-%m-%d %H:%M:%S")



#########################################################





    