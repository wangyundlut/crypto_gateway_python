import hmac
import base64
from copy import deepcopy
from decimal import Decimal
from datetime import datetime, timedelta
from crypto_gateway_python.utilities.utility_decimal import round_to
from crypto_rest_python.binance.sync_rest.spot_api import SpotAPI
from crypto_rest_python.binance.sync_rest.usdt_api import USDTAPI

from crypto_gateway_python.data_structure.base_data_struct import(
    instTypeEnum,
    instInfoData,
    contractTypeEnum,
)
from crypto_rest_python.binance.sync_rest.consts import EXCHANGE_NAME

HOURS8 = 8

##################basic log and async function##############################
def bn_get_inst_id_local(inst_id: str, inst_type: str = ""):
    return f"{EXCHANGE_NAME.lower()}_{inst_type.lower()}_{inst_id.lower()}"

def bn_get_account_ccy(ccy: str, inst_id: str = "", inst_type: str = ""):
    return f"{EXCHANGE_NAME.lower()}_{inst_type.lower()}_{inst_id.lower()}_{ccy.lower()}"

##################basic log and async function##############################

##################load rest##############################

def bn_load_exchange_info(rest=None):
    inst_id_info = {}
    def exchange_info_transfer(data) -> instInfoData:
        info = instInfoData()
        info.exchange = EXCHANGE_NAME
        
        info.base_ccy = data["baseAsset"].lower()
        info.quote_ccy = data["quoteAsset"].lower()

        info.underlying = ""
        filters_ = data["filters"]

        info.con_val = Decimal("1")

        for filterType in filters_:
            if filterType["filterType"] == "PRICE_FILTER":
                info.price_tick = Decimal(filterType["minPrice"])
            if filterType["filterType"] == "LOT_SIZE":
                info.min_order_sz = Decimal(filterType["minQty"])
                info.step_order_sz = Decimal(filterType["minQty"])
        # for bn, min order sz is 10 usdt. 
        for inst_type in [instTypeEnum.SPOT, instTypeEnum.MARGINCROSS, instTypeEnum.MARGINISOLATED]:
            info_ = deepcopy(info)
            info_.inst_type = inst_type
            info_.inst_id = data["symbol"]
            info_.inst_id_local = bn_get_inst_id_local(info_.inst_id, inst_type)
            inst_id_info[info_.inst_id_local] = info_

    spot = SpotAPI('', '')
    result = spot.market_exchangeInfo()
    for data in result["symbols"]:
        exchange_info_transfer(data)

    return inst_id_info

def bn_load_usdt_margin_exchange_info():
    inst_id_info = {}
    # for bn swap min order notional no less than 5 usd
    min_order_notional = 10

    def exchange_info_transfer(data) -> instInfoData:
        info = instInfoData()
        info.exchange = EXCHANGE_NAME
        
        info.base_ccy = data["baseAsset"].lower()
        info.quote_ccy = data["quoteAsset"].lower()

        info.underlying = data["pair"]
        filters_ = data["filters"]

        info.con_val = Decimal("1")
        
        for filterType in filters_:
            if filterType["filterType"] == "PRICE_FILTER":
                info.price_tick = Decimal(filterType["tickSize"])
            if filterType["filterType"] == "LOT_SIZE":
                info.min_order_sz = round_to(min_order_notional / ticker_price[data["symbol"]], Decimal(filterType["stepSize"]))
                info.step_order_sz = Decimal(filterType["stepSize"])

        info.inst_type = instTypeEnum.USDTM
        info.inst_id = data["symbol"]
        info.inst_id_local = bn_get_inst_id_local(info.inst_id, instTypeEnum.USDTM)
        inst_id_info[info.inst_id_local] = info

    rest = USDTAPI('', '')
    result = rest.market_get_exchangeInfo()
    ticker_result = rest.market_ticker()
    ticker_price = {}
    for ticker in ticker_result:
        ticker_price[ticker['symbol']] = Decimal(ticker['price'])
    for data in result["symbols"]:
        # only BTCSTUSDT is DEFI
        if 'DEFI' in data['underlyingSubType']:
            print(f"{data['symbol']}  {data['underlyingSubType']}")
            continue 
        
        exchange_info_transfer(data)
    return inst_id_info

def helper_get_price_spot(inst_id: str, rest=None):
    spot = SpotAPI('', '')
    result = spot.market_bookTicker(inst_id.upper())
    if "bidPrice" in result:
        return Decimal(result["bidPrice"])
    return None


def helper_get_price_usdt_margin(inst_id: str, rest=None):
    rest = USDTAPI('', '')
    result = rest.market_bookTicker(inst_id.upper())
    if "bidPrice" in result:
        return Decimal(result["bidPrice"])
    return None

    