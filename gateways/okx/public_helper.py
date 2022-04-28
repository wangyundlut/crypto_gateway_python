import hmac
import base64
from decimal import Decimal
from datetime import datetime, timedelta
from crypto_rest_python.okx.sync_rest.rest_v5 import okx_api_v5
from crypto_gateway_python.data_structure.base_data_struct import(
    instTypeEnum,
    instInfoData,
    contractTypeEnum,

)
from crypto_rest_python.okx.sync_rest.consts import (
    EXCHANGE_NAME,
    WS_PRI_URL,
    WS_PRI_URL_SIMULATION,
    WS_PUB_URL,
    WS_PUB_URL_SIMULATION,
)
HOURS8 = 8

##################basic log and async function##############################
def okx_get_inst_id_local(inst_id: str, inst_type: str = ""):
    return f"{EXCHANGE_NAME.lower()}_{inst_id.lower().replace('-', '_')}"

def okx_get_account_ccy(ccy: str, inst_id: str = "", inst_type: str = ""):
    return f"{EXCHANGE_NAME.lower()}_{ccy.lower().replace('-', '_')}"

##################basic log and async function##############################

##################load rest##############################

def okx_load_exchange_info(rest=None):
    def exchange_info_transfer(data) -> instInfoData:
        info = instInfoData()
        info.exchange = EXCHANGE_NAME
        info.inst_type = data["instType"].lower()
        instId = data["instId"]
        info.inst_id = instId
        info.inst_id_local = okx_get_inst_id_local(instId)

        info.base_ccy = data["baseCcy"].lower()
        info.quote_ccy = data["quoteCcy"].lower()

        info.underlying = data["uly"].lower()
        if info.inst_type in [instTypeEnum.FUTURES, instTypeEnum.SWAP]:
            if data["ctValCcy"].lower() == "usd":
                info.con_type = contractTypeEnum.USD
            else:
                info.con_type = contractTypeEnum.COIN
        info.con_val = Decimal(data["ctVal"])
        info.con_val_ccy = data["ctValCcy"].lower()
        info.price_tick = Decimal(data["tickSz"])
        info.min_order_sz = Decimal(data["minSz"])
        return info
    
    inst_id_info = {}
    if not rest:
        rest = okx_api_v5('', '', '')

    result = rest.public_get_instruments(instTypeEnum.SPOT.upper())
    for data in result['data']:
        data['ctVal'] = "1"
        info = exchange_info_transfer(data)
        inst_id_info[info.inst_id_local] = info
        
    result = rest.public_get_instruments(instTypeEnum.SWAP.upper())
    for data in result["data"]:
        info = exchange_info_transfer(data)
        inst_id_info[info.inst_id_local] = info
    
    result = rest.public_get_instruments(instTypeEnum.FUTURES.upper())
    for data in result["data"]:
        info = exchange_info_transfer(data)
        inst_id_info[info.inst_id_local] = info
    return inst_id_info

def helper_get_price(inst_id: str, rest: okx_api_v5=None):
    result = rest.market_get_ticker(inst_id)
    price = None
    if result["msg"] == "":
        return Decimal(result["data"][0]["last"])
    return price


def okx_sign(timestamp, secret_key):
    message = timestamp + 'GET' + '/users/self/verify'

    mac = hmac.new(bytes(secret_key, encoding='utf8'), bytes(message, encoding='utf-8'), digestmod='sha256')
    d = mac.digest()
    sign = base64.b64encode(d)
    return sign.decode("utf-8") 

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