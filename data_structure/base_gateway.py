
"""
this is base Gateway:

1 add account config file: {'exchange': 'okx', 'apiKey': 'sfdfs', ...}
2 -> load rest -> load exchange info
3 add inst_id 
4 add log(if need)

...
finally, add async private in loop, run as thread safe or just run
depends on how the main program design

every channel can only add one listener
in case same info push more then once
for example, send return channel, if listener more then one, may cause serious problem

Gateway translate exchange info to local info
for example

change depth data to local depth data(class)
change account data to local account data(class)
change position data to local position data(class)
change order data to local order  data(class)
"""
import asyncio
from datetime import datetime
from decimal import Decimal
import aiohttp 
import time
from typing import Dict, List
import logging

from crypto_gateway_python.utilities.utility_time import dt_epoch_to_china_str
from .base_data_struct import (
    instInfoData,
    depthData,
    klineData,
    feeData,
    priceLimitData,
    marketTradeData,

    accountData,
    positionData,
    orderData,
    fillData,
    sendReturnData,
    timeOutData,
    wsBreakData,
    subData,

    orderSendData, 
    cancelOrderSendData,
    amendOrderSendData,
    )

class baseGateway:
    """
    use for market and base class for gatewayTrade
    """
    def __init__(self, gateway_name='') -> None:   
        self.gateway_name = gateway_name
        self.exchange_name = ""
        self.log :logging.Logger = None
        self.gateway_ready = False
        self.ws = None
        self.account_config = {}
        self.account_name = ""

        ##################### listener #####################
        ##################### listener #####################
        ##################### listener #####################
        ##################### listener #####################

        ##################### gateway data #####################
        self.inst_id_info: Dict[str, instInfoData] = {}
        self.sub_data_set: set[subData] = set()
        ##################### gateway data #####################

        ##################### async helper #####################
        self.loop: asyncio.AbstractEventLoop = None
        self.session: aiohttp.ClientSession = None
        ##################### async helper #####################
    
    ##################basic log and async function##############################
    def add_loop_session(self, loop: asyncio.AbstractEventLoop, session: aiohttp.ClientSession):
        self.loop = loop
        self.session = session
    
    def add_log(self, log:logging.Logger):
        self.log = log

    def helper_log_record(self, msg):
        if self.log:
            self.log.info(f"{self.gateway_name}, {self.exchange_name}, {msg}")
        else:
            print(f"{datetime.now()}, {self.gateway_name}, {self.exchange_name}, {msg}")
        return 

    def helper_get_inst_id_local(self, inst_id: str, inst_type: str=""):
        raise NotImplementedError

    def helper_get_account_ccy(self, ccy: str, inst_id: str="", inst_type: str=""):
        raise NotImplementedError

    ##################basic log and async function##############################


    ##################load rest##############################
    def helper_load_exchange_info(self):
        raise NotImplementedError

    ##################load rest##############################


    ##################exchange helper##############################
    """
    get price, info .....
    """
    def helper_get_price(self, inst_id: str, inst_type: str=""):
        raise NotImplementedError
    
    def helper_get_info(self, inst_id: str, inst_type: str=""):
        inst_id_local = self.helper_get_inst_id_local(inst_id, inst_type)
        return self.inst_id_info[inst_id_local]

    ##################exchange helper##############################


    ##################gateway ##############################
    async def gateway_async(self):
        raise NotImplementedError
    
    def gateway_start(self):
        raise NotImplementedError

    def is_gateway_ready(self):
        return self.gateway_ready

    ##################gateway ##############################

class baseGatewayMarket(baseGateway):
    def __init__(self, gateway_name='') -> None:     
        baseGateway.__init__(self, gateway_name)   

        ##################### listener #####################
        self.listener_depth = None
        self.listener_kline = None
        self.listener_fee = None
        self.listener_price_limit = None
        self.listener_market_trade = None

        self.listener_ws_break = None
        self.listener_time_out = None
        ##################### listener #####################

        ##################### gateway data #####################
        self.depth_data: Dict[str, depthData] = {}
        self.kline_data: Dict[str, klineData] = {}
        self.fee_data: Dict[str, feeData] = {}
        self.price_limit_data: Dict[str, priceLimitData] = {}
        self.market_trade_data: Dict[str, marketTradeData] = {}
        ##################### gateway data #####################

    ##################add func from strategy##############################
    def add_listener_depth(self, func):
        self.listener_depth = func

    def add_listener_kline(self, func):
        self.listener_kline = func

    def add_listener_fee(self, func):
        self.listener_fee = func

    def add_listener_price_limit(self, func):
        self.listener_price_limit = func

    def add_listener_market_trade(self, func):
        self.listener_market_trade = func
    
    def add_listener_ws_break(self, func):
        self.listener_ws_break = func

    def add_listener_time_out(self, func):
        self.listener_time_out = func

    def add_strategy_sub(self, sub: subData):
        self.sub_data_set.add(sub)

    ##################add func from strategy##############################

class baseGatewayTrade(baseGateway):
    def __init__(self, gateway_name='') -> None:  
        super(baseGatewayTrade, self).__init__(gateway_name)   

        ##################### listener #####################
        self.listener_account = None
        self.listener_position = None
        self.listener_order = None
        self.listener_fill = None
        self.listener_send_return = None # send order ,cancel order, return if success

        self.listener_ws_break = None
        self.listener_time_out = None
        ##################### listener #####################

        ##################### gateway data #####################
        self.account_data: Dict[str, accountData] = {} # account_ccy
        self.position_data: Dict[str, positionData] = {} # inst_id_local
        self.live_order_data: Dict[str, orderData] = {} # client ord id

        self.check_time_out_data: Dict[str, int] = {} # cliordid ,send time
        ##################### gateway data #####################

        ##################### async helper #####################
        self.loop: asyncio.AbstractEventLoop = None
        self.session: aiohttp.ClientSession = None
        ##################### async helper #####################


    ##################load rest##############################
    def add_config_account(self, account_config={}):
        """
        this is a json or dict
        after add config account, load rest
        """
        raise NotImplementedError
    ##################load rest##############################

    ##################exchange helper##############################
    """
    get price, 
    """
    
    def helper_get_order_info(self, ordId: str="", clOrdId: str="") -> orderData:
        raise NotImplementedError

    def helper_get_account(self, ccy, inst_id: str, inst_type: str="") -> accountData:
        raise NotImplementedError
    
    def helper_get_position(self, inst_id: str, inst_type: str="") -> positionData:
        raise NotImplementedError

    ##################exchange helper##############################
    

    ##################add func from strategy##############################
    def add_listener_account(self, func):
        self.listener_account = func
    
    def add_listener_position(self, func):
        self.listener_position  = func
    
    def add_listener_order(self, func):
        self.listener_order = func
    
    def add_listener_fill(self, func):
        self.listener_fill = func
    
    def add_listener_send_return(self, func):
        self.listener_send_return = func
    
    def add_listener_ws_break(self, func):
        self.listener_ws_break = func
    
    def add_listener_time_out(self, func):
        self.listener_time_out = func
    
    def add_strategy_sub(self, sub: subData):
        self.sub_data_set.add(sub)

    ##################add func from strategy##############################


    ##################trade engine ##############################

    async def send_data_time_pass(self):
        # when send order, cancel order, or amend order, 
        # self.check_time_out_data will record send time base on clOrdId
        del_clordids = []
        while True:
            await asyncio.sleep(1)
            try:
                for clordId, send_time in self.check_time_out_data.items():
                    time_delay = int(time.time() * 1000) - send_time
                    if time_delay > 5000:
                        del_clordids.append(clordId)
                        data = timeOutData()
                        data.gateway_name = self.gateway_name
                        data.exchange_name = self.exchange_name
                        data.event = "client order id time out."
                        data.cl_ord_id = clordId
                        data.send_time_china = dt_epoch_to_china_str(send_time)
                        data.time_delay = time_delay
                        
                        if self.listener_time_out:
                            self.listener_time_out(data)
                for clordId in del_clordids:
                    del self.check_time_out_data[clordId]
                del_clordids = []

            except Exception as e:
                self.helper_log_record(f"send_data_time_pass error: {e}")

    ##################trade engine ##############################


    ##################send order ##############################
    # this is async send, must implemented
    def send_order(self, order: orderSendData):
        raise NotImplementedError

    def send_batch_order(self, order_list: List[orderSendData]):
        raise NotImplementedError

    def cancel_order(self, cancel: cancelOrderSendData):
        raise NotImplementedError

    def cancel_batch_order(self, cancel_list: List[cancelOrderSendData]):
        raise NotImplementedError
    
    def amend_order(self, amend: amendOrderSendData):
        raise NotImplementedError

    def amend_batch_order(self, amend_list: List[amendOrderSendData]):
        raise NotImplementedError
    # this is async send, must implemented


    # this is sync send
    def send_order_sync(self, order: orderSendData):
        """
        rest also async, 
        """
        pass

    def send_batch_order_sync(self, order_list: List[orderSendData]):
        pass

    def cancel_order_sync(self, cancel: cancelOrderSendData):
        pass

    def cancel_batch_orders_sync(self, cancel_list: List[cancelOrderSendData]):
        pass
    
    def amend_order_sync(self, amend: amendOrderSendData):
        pass

    def amend_batch_order_sync(self, amend_list: List[amendOrderSendData]):
        pass

    ##################send order ##############################
    def get_order_info(self, inst_id: str="", ord_id: str="", cl_ord_id: str="None") -> orderData:
        pass

