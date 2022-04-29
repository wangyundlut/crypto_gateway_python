import asyncio
import zlib
import websockets
import json
from datetime import datetime
from decimal import Decimal
from time import time, sleep


from crypto_gateway_python.utilities.utility_time import dt_china_now_str, dt_epoch_to_china_str, dt_epoch_utz_now
from crypto_gateway_python.data_structure.base_gateway import baseGatewayMarket
from crypto_gateway_python.data_structure.base_data_struct import(
    depthData,
    subChannelEnum,
    timeOutData,
    instTypeEnum,
    instInfoData,
    contractTypeEnum,
    subData,
)
from crypto_gateway_python.gateways.binance.public_helper import (
    bn_get_inst_id_local,
    bn_get_account_ccy,
    bn_load_exchange_info,
    helper_get_price_spot,
)
from crypto_rest_python.binance.sync_rest.spot_api import SpotAPI
from crypto_rest_python.binance.sync_rest.consts import (
    EXCHANGE_NAME,
    WS_SPOT_URL,
)

HOURS8=8
ZERODECIMAL = Decimal("0")




class binanceGatewayMarketSpot(baseGatewayMarket):
    def __init__(self, gateway_name='') -> None:
        baseGatewayMarket.__init__(self, gateway_name=gateway_name)
        self.exchange_name = EXCHANGE_NAME
        self.websocketPubUrl = WS_SPOT_URL
        self.rate_filters = {}
    
    ##################basic log and async function##############################
    def helper_get_inst_id_local(self, inst_id: str, inst_type: str = ""):
        return bn_get_inst_id_local(inst_id, inst_type)

    def helper_get_account_ccy(self, ccy: str, inst_id: str = "", inst_type: str = ""):
        return bn_get_account_ccy(ccy, inst_id, inst_type)

    ##################basic log and async function##############################


    ##################load rest##############################
    def helper_load_exchange_info(self):
        spot = SpotAPI('', '')

        result = spot.market_exchangeInfo()
        for rateLimit in result["rateLimits"]:
            if rateLimit["rateLimitType"] == "REQUEST_WEIGHT":
                self.rate_filters["REQUEST_WEIGHT"] = rateLimit
            if rateLimit["rateLimitType"] == "ORDERS" and rateLimit["interval"] == "SECOND":
                self.rate_filters["ORDERS_SECOND"] = rateLimit
            if rateLimit["rateLimitType"] == "ORDERS" and rateLimit["interval"] == "DAY":
                self.rate_filters["ORDERS_DAY"] = rateLimit
            if rateLimit["rateLimitType"] == "RAW_REQUESTS":
                self.rate_filters["RAW_REQUESTS"] = rateLimit

        inst_id_info = bn_load_exchange_info()
        self.inst_id_info = inst_id_info
        return


    ##################load rest##############################


    ##################exchange helper##############################
    """
    get price, info .....
    """
    def helper_get_price(self, inst_id: str, inst_type: str=""):
        return helper_get_price_spot(inst_id)

    ##################exchange helper##############################

    ##################market gateway ##############################
    async def gateway_async(self):
        url = f"{self.websocketPubUrl}/stream?streams="
        """
         /stream?streams=<streamName1>/<streamName2>/<streamName3>
        """
        # url += "/stream?streams=ltcusdt@bookTicker/ltcbtc@bookTicker"
        book_url = ""
        for sub in self.sub_data_set:
            inst_id = sub.inst_id
            book_url += f"{inst_id.lower()}@bookTicker/"
        book_url = book_url[:-1]

        while True:
            try:

                async with websockets.connect(url + book_url) as self.ws:
                    
                    while True:
                        try:
                            res = await asyncio.wait_for(self.ws.recv(), timeout=10)
                        except (asyncio.TimeoutError, websockets.exceptions.ConnectionClosed) as e:
                            # TODO time out
                            print(f"{datetime.now()} {self.exchange_name} market channel not receive for 60 seconds, 正在重连…… error: {e}")
                            raise Exception(f"long time no receive")

                        res = json.loads(res)
                        if 'stream' in res:
                            if not self.gateway_ready:
                                self.gateway_ready = True
                            stream = res['stream']
                            if 'bookTicker' in stream:
                                data = res['data']
                                depth = self.update_depth(data)

                                if self.listener_depth:
                                    self.listener_depth(depth)

                            else:
                                self.helper_log_record(f"stream {stream}")
                        else:
                            self.helper_log_record(f"not stream, {res}")
                        
            except Exception as e:

                if 'cannot schedule new FUTURES after shutdown' in str(e):
                    pass
                elif 'no running event loop' in str(e):
                    pass
                else:
                    self.helper_log_record(f"{self.exchange_name}, {self.gateway_name}, subscribe_market_data error: {e}")
                # print(timestamp + f" subscribe_market_data error: {e}")
                self.gateway_ready = False
                continue


    def gateway_start(self):
        asyncio.run_coroutine_threadsafe(self.gateway_async(), self.loop)

    def update_depth(self, data):
        depth = depthData()
        depth.gateway_name = self.gateway_name
        depth.exchange = EXCHANGE_NAME
        depth.inst_type = "spot"
        depth.inst_id = data['s']
        depth.inst_id_local = bn_get_inst_id_local(depth.inst_id, depth.inst_type)
        depth.time_epoch = dt_epoch_utz_now()
        depth.time_china = dt_epoch_to_china_str(depth.time_epoch)
        depth.bid_price_1 = Decimal(data['b'])
        depth.bid_volume_1 = Decimal(data['B'])
        depth.ask_price_1 = Decimal(data['a'])
        depth.ask_volume_1 = Decimal(data['A'])
        depth.asks_list = []
        depth.bids_list = []
        return depth

def gateway_test():
    def listener(data):
        print(data)

    loop = asyncio.get_event_loop()
    from crypto_rest_python.async_rest_client import create_session, start_event_loop
    session =loop.run_until_complete(create_session(loop))
    start_event_loop(loop)

    gateway = binanceGatewayMarketSpot("test")
    gateway.add_loop_session(loop, session)
    gateway.helper_load_exchange_info()

    sub = subData()
    # okx is very strange, DEPTH50 market data need log in.
    sub.channel = subChannelEnum.DEPTH
    sub.inst_type = instTypeEnum.SPOT
    sub.inst_id = "LTCBTC"
    gateway.add_strategy_sub(sub)

    gateway.add_listener_depth(listener)
    gateway.gateway_start()
    
    while True:
        sleep(60)


if __name__ == "__main__":
    gateway_test()



