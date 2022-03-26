
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
for example, ws info channel, if listener more then one, may cause serious problem

Gateway translate exchange info to local info
for example

change depth data to local depth data(class)
change account data to local account data(class)
change position data to local position data(class)
change order data to local order  data(class)
"""
from typing import Dict, List 

from .base_data_struct import (
    accountData,
    instInfoData,
    orderData,
    orderSendData, 
    cancelOrderSendData,
    amendOrderSendData,
    positionData)

class baseGateway:

    def __init__(self, gateway_name='') -> None:        
        self.gateway_name = gateway_name
        
        self.listener_depth = None
        self.listener_account = None
        self.listener_position = None
        self.listener_order = None
        self.listener_fill = None
        self.listener_ws = None

        self.rest = None
        self.inst_id_info = {}

    ##################load rest##############################
    def add_config_account(self, config_path='/test/.yaml'):
        """
        this is a json or dict
        after add config account, load rest
        """
        pass

    def load_rest(self):
        """
        after load rest, load exchange info
        """
        pass

    def load_exchange_info(self):
        pass

    def exchange_info_transfer(self, data):
        pass

    def get_inst_id_local(self, inst_id: str, inst_type: str=""):
        pass

    def get_inst_ccy_local(self, inst_id: str="", inst_type: str="", ccy: str="", pair: str=""):
        pass

    ##################load rest##############################

    ##################strategy engine add##############################
    def add_inst_id_needed(self, inst_id: str, inst_type: str=""):
        """
        this is a inst_id list need to be listen, maybe one
        """
        pass

    def add_log(self, log):
        pass

    def log_record(self, msg):
        pass
    
    ##################exchange helper##############################
    def get_inst_id_price(self, inst_id: str, inst_type: str=""):
        pass

    def get_account(self, inst_id: str, inst_type: str, ccy: str) -> accountData:
        pass
        
    def get_position(self, inst_id: str, inst_type: str="") -> positionData:
        """
        for spot, it will return 
        """
        pass
    
    def get_info(self, inst_id: str, inst_type: str="") -> instInfoData:
        pass

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
    
    def send_order_rest(self, order: orderSendData):
        """
        rest also async, 
        """
        pass

    def send_batch_order_rest(self, order_list: List[orderSendData]):
        pass

    def cancel_order_rest(self, cancel: cancelOrderSendData):
        pass

    def cancel_batch_orders_rest(self, cancel_list: List[cancelOrderSendData]):
        pass
    
    def amend_order_rest(self, amend: amendOrderSendData):
        pass

    def amend_batch_order_rest(self, amend_list: List[amendOrderSendData]):
        pass

    def get_order_info(self, ord_id="", cl_ord_id="") -> orderData:
        pass

    
    
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
        pass

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
    
    def depth_transfer(self, depth):
        pass

    
    def account_trans(self, account):
        """
        middle engine's listener
        """
        pass

    
    def position_trans(self, position):
        """
        middle engine's listener
        """
        pass


    def order_trans(self, order):
        """
        middle engine's listener
        """
        pass
    

    def trade_trans(self, trade):
        """
        middle engine's listener
        """
        pass

    def ws_info_trans(self, d: dict):
        pass

    async def ws_info_trans(self, d: dict):
        pass
    

        
