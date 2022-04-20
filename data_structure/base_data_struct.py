
"""
this is is base data structure
All letter should be lower. 
For compare.
"""

from dataclasses import dataclass, field
import time
from decimal import Decimal

"""
orderStateData, orderSendStateData, orderTypeData, orderSideData
instTypeData, contractTypeData, instInfoData, depthData, tradeData, klineData
accountData, orderData, positionData, fillData, orderChannelData, sendReturnData, 
orderSendData, cancelOrderSendData, amendOrderSendData, orderErrorCodeMsgData
"""


@dataclass
class orderStateData:
    SENDING = "sending" # local sending
    SENDSUCCEED = "send-succeed" # accept by exchange
    SENDFAILED = "send-failed" # send failed, reject by exchange

    CANCELING = "canceling" # in exchange, ready to quit
    CANCELSUCCEED = "canceled"
    CANCELFAILED = "cancel-failed"

    AMENDING = "amending"
    AMENDSUCCEED = "amend-succeed"
    AMENDFAILED = "amend-failed"

    PARTIALFILLED = "partial-filled"
    FILLED = "filled"
    PARTIALCANCELED = "partial-canceled" # partial-filled then cancel rest
    

@dataclass
class orderTypeData:
    LIMIT = "limit"
    MARKET = "market"
    IOC = "ioc"
    FOK = "fok"
    POSTONLY = "post_only"

@dataclass
class orderSideData:
    BUY = "buy"
    SELL = "sell"

@dataclass
class instTypeData:
    SPOT = "spot"
    MARGINCROSS = "scross"
    MARGINISOLATED = "sisolated"
    FUTURES = "futures"
    FUTURESISOLATED = "fisolated"
    SWAP = "swap"
    SWAPISOLATED = "fswap"

@dataclass
class contractTypeData:
    COIN = "coin" # buy/sell contract means buy/sell coin, means btc-usdt-swap
    USD = "usd" # buy/sell contract means buy/sell usd, means btc-usd-swap
    
@dataclass
class instInfoData:
    exchange: str = ""
    inst_type: str = "" # instType: local not exchange (lower)
    inst_id: str = "" # btc-usdt: local not exchange (lower)
    inst_id_local: str = "" # exchange + inst_type + inst_id (unique)
    price_tick: Decimal = 0 # min price decimal
    min_order_sz: Decimal = 0 # min order size

    base_ccy: str = "" # btc-eth, btc is base ccy, spot
    quote_ccy: str = "" # btc-eth, eth is quote ccy, spot

    underlying: str = "" # for futures and swap only
    con_type: contractTypeData = contractTypeData.COIN # coin (1 for coin), usd(1 for how many usd) spot
    con_val: Decimal = 0 # contract value, 1 for how many contract value ccy
    con_val_ccy: str = "" # contract value cct, usd or coin, 
    # inst_type + con_type:  swap, coin.. swap usd..

@dataclass
class accountChangeTypeData:
    ORDERPLACE: str = "order-place"
    ORDERMATCH: str = "order-match"


################# market data #################
@dataclass
class depthData:
    
    gateway_name : str = "" # sender, okx_market
    exchange: str = "" # okx
    inst_type: str = "" # instType
    inst_id: str = "" # btc-usdt
    inst_id_local: str = "" # exchange + inst_type + inst_id
    time_epoch: Decimal = Decimal(int(time.time() * 1000)) # decimal in milleseconds
    time_china: str = "" # 2021-01-01 00:00:00.123456 +0800

    bid_price_1: Decimal = 0
    bid_volume_1: Decimal = 0 # exchange volume

    ask_price_1: Decimal = 0
    ask_volume_1: Decimal = 0

    asks_list: list = field(default_factory=list) # [[p1, sz1], [p2, sz2]] ask1, ask2, ask3
    bids_list: list = field(default_factory=list) # [[p1, sz1], [p2, sz2]] bid1, bid2, bid3

@dataclass
class marketTradeData: # this is market trade data, not order->trade data, that is fill data
    gateway_name : str = "" # sender, okx_market
    exchange: str = "" # okx
    inst_type: str = "" # instType
    inst_id: str = "" # btc-usdt
    inst_id_local: str = "" # exchange + inst_type + inst_id
    time_epoch: Decimal = Decimal(int(time.time() * 1000)) # decimal in milleseconds
    time_china: str = "" # 2021-01-01 00:00:00.123456 +0800
    trade_id: str = "" # unique identifier
    side: str = ""
    px: Decimal = 0
    sz: Decimal = 0

@dataclass
class klineData:
    gateway_name : str = "" # sender, okx_market
    exchange: str = "" # okx
    inst_type: str = "" # instType
    inst_id: str = "" # btc-usdt
    inst_id_local: str = "" # exchange + inst_type + inst_id
    time_epoch: Decimal = Decimal(int(time.time() * 1000)) # decimal in milleseconds
    time_china: str = "" # 2021-01-01 00:00:00.123456 +0800
    open_price: Decimal = 0
    high_price: Decimal = 0
    low_price: Decimal = 0
    close_price: Decimal = 0
    sz: Decimal = 0

################# market data #################
###############################################
################# trade data #################
@dataclass
class accountData:
    gateway_name : str = ""
    account_name: str = ""
    exchange: str = ""
    change_type: str = ""
    ccy: str = ""
    ccy_local: str = "" # exchange + ccy
    asset: Decimal = 0 # asset
    debt: Decimal = 0 # debt
    equity: Decimal = 0 # equity, netasset
    frozen: Decimal = 0 # frozen, locked
    interest: Decimal = 0 # 
    account_risk: Decimal = 0 # margin / asset, < 1 for ever, more close to 1, more risker!
    update_time_epoch: Decimal = Decimal(int(time.time() * 1000))
    update_time_china: str = ""


@dataclass
class orderData:
    """
    Order data contains information for tracking lastest status
    of a specific order.
    """
    gateway_name : str = ""
    account_name: str = ""
    exchange: str = ""
    inst_type: str = ""
    inst_id: str = ""
    inst_id_local: str = ""
    ord_id: str = ""
    cl_ord_id: str = ""
    state: str = ""
    px: Decimal = 0
    sz: Decimal = 0
    pnl: Decimal = 0
    ord_type: str = ""
    side: str = ""
    fill_px: Decimal = 0  
    fill_sz: Decimal = 0
    acc_fill_sz: Decimal = 0
    avg_px: Decimal = 0
    fee_ccy: str = ""
    fee: Decimal = 0
    rebate_ccy: str = ""
    rebate: Decimal = 0
    update_time_epoch: Decimal = Decimal(int(time.time() * 1000))
    update_time_china: str = ""
    create_time_epoch: Decimal = Decimal(int(time.time() * 1000))
    create_time_china: str = ""


@dataclass
class positionData:
    """
    Positon data is used for tracking each individual position holding.
    """
    gateway_name : str = ""
    account_name: str = ""
    exchange: str = ""
    inst_type: str = ""
    inst_id: str = ""
    inst_id_local: str = ""
    avg_px: Decimal = 0
    last_price: Decimal = 0
    pos: Decimal = 0
    update_time_epoch: Decimal = Decimal(int(time.time() * 1000))
    update_time_china: str = ""


@dataclass
class fillData:
    """
    trade data contains information for tracking lastest status
    of a specific trade.
    """
    gateway_name : str = ""
    account_name: str = ""
    exchange: str = ""
    inst_type: str = ""
    inst_id: str = ""
    inst_id_local: str = ""
    ord_type: str = ""
    side: str = ""
    ord_id: str = ""
    cl_ord_id: str = ""
    bill_id: str = ""
    trade_id: str = ""
    tag = ""
    taker_or_maker = ""
    fill_px: Decimal = 0  
    fill_sz: Decimal = 0
    fee_ccy: str = ""
    fee: Decimal = 0
    rebate_ccy: str = ""
    rebate: Decimal = 0
    time_epoch: Decimal = Decimal(int(time.time() * 1000))
    time_china: str = ""


@dataclass
class orderChannelData:
    ORDER: str = "order"
    BATCHORDERS: str = "batch-orders"
    CANCELORDER: str = "cancel-order"
    BATCHCANCELORDERS: str = "batch-cancel-orders"
    AMENDORDER: str = "amend-order"
    BATCHAMENDORDERS: str =  "batch-amend-orders"

@dataclass
class sendReturnData:
    """
    this is order return info
    send order, normally will return ord_id, and msg info
    this should call sendReturnInfo
    """
    gateway_name : str = ""
    account_name: str = ""
    ws_id: str = ""
    channel: str = "" # order, batch-orders, cancel-order, cancel-batch-order, amend-order, amend-batch-order
    ord_id: str = ""
    cl_ord_id: str = ""
    ord_state: str = ""
    code: str = "" # error code
    msg: str = "" # error msg
    receive_time: Decimal = Decimal(int(time.time() * 1000))
    

################# trade data #################

@dataclass
class orderSendData:
    inst_type: str = ""
    inst_id: str = ""
    inst_id_local: str = ""
    trade_mode: str = ""
    cl_ord_id: str = ""
    side: str = ""
    ord_type: str = ""
    px: Decimal = 0
    sz: Decimal = 0 # how many ccy, (sz=0.1, ccy=btc)  (sz=100, ccy=USD)
    ccy: str = "" 
    ws_id: str = ""
    send_time: Decimal = Decimal(int(time.time() * 1000))

@dataclass
class cancelOrderSendData:
    inst_type: str = ""
    inst_id: str = ""
    inst_id_local: str = ""
    ord_id: str = ""
    cl_ord_id: str = ""
    ws_id: str = ""
    send_time: Decimal = Decimal(int(time.time() * 1000))

@dataclass
class amendOrderSendData:
    inst_type: str = ""
    inst_id: str = ""
    inst_id_local: str = ""
    ord_id: str = ""
    cl_ord_id: str = ""
    new_sz: Decimal = 0
    new_px: Decimal = 0
    ccy: str = ""
    ws_id: str = ""
    send_time: Decimal = Decimal(int(time.time() * 1000))
    

    


