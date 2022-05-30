import hmac
import base64
from copy import deepcopy
from decimal import Decimal
from datetime import datetime, timedelta
from crypto_rest_python.huobi.sync_rest.rest_api_spot import huobiRestSpot
from crypto_rest_python.huobi.sync_rest.rest_api_usdt import huobiRestUSDT
from crypto_gateway_python.data_structure.base_data_struct import(
    instTypeEnum,
    instInfoData,
    contractTypeEnum,
)
from crypto_rest_python.huobi.sync_rest.consts import EXCHANGE_NAME

HOURS8 = 8

def huobi_get_inst_id_local(inst_id: str, inst_type: str = ""):
    return f"{EXCHANGE_NAME.lower()}_{inst_type.lower()}_{inst_id.lower()}"
    
def huobi_get_account_ccy(ccy: str, inst_id: str = "", inst_type: str = ""):
    return f"{EXCHANGE_NAME.lower()}_{inst_type.lower()}_{inst_id.lower()}_{ccy.lower()}"
    

def huobi_load_exchange_info():
    symbols_info = {}
    def exchange_info_transfer(data):
        info = instInfoData()
        info.exchange = EXCHANGE_NAME
        info.inst_type = instTypeEnum.SPOT
        # lower character
        info.inst_id = data["sc"]
        info.inst_id_local = huobi_get_inst_id_local(info.inst_id, info.inst_type)
        info.price_tick = Decimal(str(10 ** (-data["tpp"])))
        info.min_order_sz = Decimal(str(10 ** (-data["tap"])))

        info.base_ccy = data["bc"]
        info.quote_ccy = data["qc"]

        info.con_val = Decimal(1)
        symbols_info[info.inst_id_local] = info

    rest = huobiRestSpot("", "")
    result = rest.common_symbols()
    for info in result["data"]:
        exchange_info_transfer(info)
    return symbols_info

def huobi_load_usdt_margin_info():
    rest = huobiRestUSDT("", "")
    result = rest.market_get_contract_info()
    symbols_info = {}
    def exchange_info_transfer(data):
        info = instInfoData()
        info.exchange = EXCHANGE_NAME
        info.inst_type = instTypeEnum.USDTM
        # lower character
        info.inst_id = data["contract_code"].lower()
        info.inst_id_local = huobi_get_inst_id_local(info.inst_id, info.inst_type)
        info.price_tick = Decimal(str(data["price_tick"]))
        info.min_order_sz = Decimal(str("1"))

        # info.base_ccy = data["bc"]
        # info.quote_ccy = data["qc"]

        info.con_val = Decimal(str(data["contract_size"]))
        symbols_info[info.inst_id_local] = info
    for info in result["data"]:
        exchange_info_transfer(info)
    return symbols_info

def helper_get_price_spot(inst_id: str, inst_type: str = ""):
    
    rest = huobiRestSpot("", "")
    
    result = rest.market_ticker(inst_id.lower())
    
    return Decimal(str(result["tick"]["close"]))

def helper_get_price_usdt_margin(inst_id:str, inst_type:str=""):
    rest = huobiRestUSDT("", "")
    result = rest.market_get_ticker(inst_id.upper())
    return Decimal(str(result["tick"]["close"]))
