
"""
this is is base data structure
All letter should be lower. 
For compare.
"""

from dataclasses import dataclass, field
from typing import List, Union
import time
from decimal import Decimal

"""
orderStateEnum, orderTypeEnum, orderSideEnum
instTypeEnum, contractTypeEnum, subChannelEnum, orderChannelEnum, 
instInfoData, depthData, klineData, feeData, priceLimitData, marketTradeData, wsBreakData, timeOutData
accountData, orderData, positionData, fillData, sendReturnData, subData
orderSendData, cancelOrderSendData, amendOrderSendData
"""


@dataclass
class orderStateEnum:
    SENDING = "sending" # local sending
    SENDSUCCEED = "send-succeed" # accept by exchange
    SENDFAILED = "send-failed" # send failed, reject by exchange

    CANCELING = "canceling" # in exchange, ready to quit
    CANCELSUCCEED = "canceled" # order finished
    CANCELFAILED = "cancel-failed" # 

    AMENDING = "amending"
    AMENDSUCCEED = "amend-succeed"
    AMENDFAILED = "amend-failed"

    PARTIALFILLED = "partial-filled" # order is not finished
    FILLED = "filled"
    PARTIALCANCELED = "partial-canceled" # partial-filled then cancel rest, order finished
    
@dataclass
class orderTypeEnum:
    LIMIT = "limit"
    MARKET = "market"
    IOC = "ioc"
    FOK = "fok"
    POSTONLY = "post_only"

@dataclass
class orderSideEnum:
    BUY = "buy"
    SELL = "sell"

@dataclass
class instTypeEnum:
    SPOT = "spot"
    MARGINCROSS = "scross"
    MARGINISOLATED = "sisolated"
    # usdt margin
    USDTM = "usdtm"
    # coin margin
    COINM = "coinm"
    FUTURES = "futures"
    FUTURESISOLATED = "fisolated"
    SWAP = "swap"
    SWAPISOLATED = "sisolated"

@dataclass
class contractTypeEnum:
    COIN = "coin" # buy/sell contract means buy/sell coin, means btc-usdt-swap
    USD = "usd" # buy/sell contract means buy/sell usd, means btc-usd-swap

@dataclass
class subChannelEnum:
    DEPTH: str = "depth"
    DEPTH5: str = "depth5"
    DEPTH10: str = "depth10"
    DEPTH50: str = "depth50"
    DEPTH50: str = "depth400"
    KLINE: str = "kline"
    FUNDINGRATE: str = "funding_rate"
    PRICELIMIT: str = "price_limit"
    MARKETTRADE: str = "market_trade"

    ACCOUNT = "account"
    POSITION = "position"
    ORDER = "order"
    FILL = "fill"
    SENDRETURN = "send_return"
    WSBREAK = "ws_break"

@dataclass
class orderChannelEnum:
    ORDER: str = "order"
    BATCHORDERS: str = "batch-orders"
    CANCELORDER: str = "cancel-order"
    BATCHCANCELORDERS: str = "batch-cancel-orders"
    AMENDORDER: str = "amend-order"
    BATCHAMENDORDERS: str =  "batch-amend-orders"


################# market data #################
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
    con_type: contractTypeEnum = "" # coin (1 for coin), usd(1 for how many usd) spot
    con_val: Decimal = 0 # contract value, 1 for how many contract value ccy
    con_val_ccy: str = "" # contract value cct, usd or coin, 
    # inst_type + con_type:  swap, coin.. swap usd..

@dataclass
class depthData:
    gateway_name : str = "" # sender, okx_market
    exchange: str = "" # okx
    inst_type: str = "" # instType
    inst_id: str = "" # btc-usdt
    inst_id_local: str = "" # exchange + inst_type + inst_id
    time_epoch: int = int(time.time() * 1000) # decimal in milleseconds
    time_china: str = "" # 2021-01-01 00:00:00.123456 +0800

    bid_price_1: Decimal = 0
    bid_volume_1: Decimal = 0 # exchange volume

    ask_price_1: Decimal = 0
    ask_volume_1: Decimal = 0

    asks_list: list = field(default_factory=list) # [[p1, sz1], [p2, sz2]] ask1, ask2, ask3
    bids_list: list = field(default_factory=list) # [[p1, sz1], [p2, sz2]] bid1, bid2, bid3
    other_data = {}

@dataclass
class klineData:
    gateway_name : str = "" # sender, okx_market
    exchange: str = "" # okx
    inst_type: str = "" # instType
    inst_id: str = "" # btc-usdt
    inst_id_local: str = "" # exchange + inst_type + inst_id
    time_epoch: int = int(time.time() * 1000) # decimal in milleseconds
    time_china: str = "" # 2021-01-01 00:00:00.123456 +0800
    open_price: Decimal = 0
    high_price: Decimal = 0
    low_price: Decimal = 0
    close_price: Decimal = 0
    sz_base_coin: Decimal = 0
    sz_quote_coin: Decimal = 0
    sz_usdt: Decimal = 0

@dataclass
class feeData:
    gateway_name : str = "" # sender, okx_market
    exchange: str = "" # okx
    inst_type: str = "" # instType
    inst_id: str = "" # btc-usdt
    inst_id_local: str = "" # exchange + inst_type + inst_id
    time_epoch: int = int(time.time() * 1000) # decimal in milleseconds
    time_china: str = "" # 2021-01-01 00:00:00.123456 +0800
    fee: Decimal = Decimal(0)
    fee_time_epoch: int = int(time.time() * 1000) # decimal in milleseconds
    fee_time_china: str = "" # 2021-01-01 00:00:00.123456 +0800
    next_fee: Decimal = Decimal(0)
    next_fee_time_epoch: int = int(time.time() * 1000) # decimal in milleseconds
    next_fee_time_china: str = "" # 2021-01-01 00:00:00.123456 +0800
    
@dataclass
class priceLimitData:
    gateway_name : str = "" # sender, okx_market
    exchange: str = "" # okx
    inst_type: str = "" # instType
    inst_id: str = "" # btc-usdt
    inst_id_local: str = "" # exchange + inst_type + inst_id
    time_epoch: int = int(time.time() * 1000) # decimal in milleseconds
    time_china: str = "" # 2021-01-01 00:00:00.123456 +0800
    upper_limit: Decimal = Decimal(0)
    lower_limit: Decimal = Decimal(0)

@dataclass
class marketTradeData: # this is market trade data, not order->trade data, that is fill data
    gateway_name : str = "" # sender, okx_market
    exchange: str = "" # okx
    inst_type: str = "" # instType
    inst_id: str = "" # btc-usdt
    inst_id_local: str = "" # exchange + inst_type + inst_id
    time_epoch: int = int(time.time() * 1000) # decimal in milleseconds
    time_china: str = "" # 2021-01-01 00:00:00.123456 +0800
    trade_id: str = "" # unique identifier
    side: str = ""
    px: Decimal = 0
    sz: Decimal = 0

@dataclass
class wsBreakData:
    gateway_name: str = ""
    exchange_name: str = ""
    break_reason : str = ""
    break_time_epoch : int = int(time.time() * 1000)
    break_time_china: str = ""

@dataclass
class timeOutData:
    gateway_name: str = ""
    exchange_name: str = ""
    event: str = ""
    cl_ord_id: str = ""
    send_time_china: str = ""
    time_delay: str = "" # seconds

################# market data #################
###############################################
################# trade data #################
@dataclass
class accountData:
    gateway_name : str = ""
    account_name: str = ""
    exchange: str = ""
    inst_type: str = ""
    inst_id: str = ""
    ccy: str = ""
    ccy_local: str = "" # exchange + ccy
    asset: Decimal = 0 # asset
    debt: Decimal = 0 # debt
    equity: Decimal = 0 # equity, netasset
    frozen: Decimal = 0 # frozen, locked
    interest: Decimal = 0 # 
    account_risk: Decimal = 0 # margin / asset, < 1 for ever, more close to 1, more risker!
    update_time_epoch: int = int(time.time() * 1000)
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
    update_time_epoch: int = int(time.time() * 1000)
    update_time_china: str = ""
    create_time_epoch: int = int(time.time() * 1000)
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
    open_px: Decimal = 0
    hold_px: Decimal = 0
    direction: str = ""
    pos: Decimal = 0
    available: Decimal = 0
    frozen: Decimal = 0
    update_time_epoch: int = int(time.time() * 1000)
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
    time_epoch: int = int(time.time() * 1000)
    time_china: str = ""

@dataclass
class sendReturnData:
    """
    this is order return info
    send order, normally will return ord_id, and msg info
    this should call sendReturnInfo
    """
    gateway_name : str = ""
    exchange_name : str = ""
    account_name: str = ""
    ws_id: str = ""
    channel: str = "" # order, batch-orders, cancel-order, cancel-batch-order, amend-order, amend-batch-order
    ord_id: str = ""
    cl_ord_id: str = ""
    ord_state: str = ""
    code: str = "" # error code
    msg: str = "" # error msg
    receive_time_epoch: int = int(time.time() * 1000)
    receive_time_china: str = ""


@dataclass
class subData:
    # depth(ticker), depth5, depth10, depth50, kline, fee, price_limit
    # account, position, order, fill, send_return, ws_break
    channel: subChannelEnum =  ""
    inst_type: instTypeEnum = ""
    inst_id: str = ""

    def __hash__(self) -> int:
        return hash(f"{self.channel}{self.inst_type}{self.inst_id}")

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
    receive_time: Decimal = Decimal(int(time.time() * 1000))

@dataclass
class cancelOrderSendData:
    inst_type: str = ""
    inst_id: str = ""
    inst_id_local: str = ""
    side: orderSideEnum = ""
    ord_id: str = ""
    cl_ord_id: str = ""
    ws_id: str = ""
    send_time: Decimal = Decimal(int(time.time() * 1000))
    receive_time: Decimal = Decimal(int(time.time() * 1000))

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
    receive_time: Decimal = Decimal(int(time.time() * 1000))



