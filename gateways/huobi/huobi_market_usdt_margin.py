import asyncio

import zlib
import gzip
import websockets
import json
from datetime import datetime, timedelta
from decimal import Decimal
from time import time, sleep

import asyncio

from crypto_rest_python.async_rest_client import create_session, start_event_loop
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
    wsBreakData,
)
from crypto_gateway_python.gateways.huobi.public_helper import (
    huobi_get_inst_id_local,
    huobi_get_account_ccy,
    huobi_load_usdt_margin_info,
    helper_get_price_usdt_margin,
)

from crypto_rest_python.huobi.sync_rest.consts import (
    EXCHANGE_NAME,
    USDT_WEBSOCKET_DATA_HOST,
    USDT_WEBSOCKET_TRADE_HOST,
)


HOURS8=8
ZERODECIMAL = Decimal("0")


class huobiGatewayMarketUsdtMargin(baseGatewayMarket):
    def __init__(self, gateway_name='') -> None:
        baseGatewayMarket.__init__(self, gateway_name=gateway_name)
        self.exchange_name = EXCHANGE_NAME
        self.url = USDT_WEBSOCKET_DATA_HOST
        self.depth_dict = {} # "btcusdt": {tick}
        self.gateway_ready = False
        
    
    ##################basic log and async function##############################
    def helper_get_inst_id_local(self, inst_id: str, inst_type: str = ""):
        return huobi_get_inst_id_local(inst_id, inst_type)

    def helper_get_account_ccy(self, ccy: str, inst_id: str = "", inst_type: str = ""):
        return huobi_get_account_ccy(ccy, inst_id, inst_type)

    ##################basic log and async function##############################

    ##################load rest##############################
    def helper_load_exchange_info(self):
        inst_id_info = huobi_load_usdt_margin_info()
        self.inst_id_info = inst_id_info
        return

    ##################load rest##############################


    ##################exchange helper##############################
    """
    get price, info .....
    """
    def helper_get_price(self, inst_id: str, inst_type: str=""):
        return helper_get_price_usdt_margin(inst_id)

    ##################exchange helper##############################

    ##################market gateway ##############################
    def depth_transfer(self, inst_id: str, inst_type: str=""):
        data = self.depth_dict[inst_id]
        inst_id_local = self.helper_get_inst_id_local(inst_id, inst_type)
        info = self.inst_id_info[inst_id_local]

        ts = data["ts"]
        asks = data["ask"]
        bids = data["bid"]
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
        depth.bid_price_1 = Decimal(str(bids[0]))
        depth.bid_volume_1 = Decimal(str(bids[1]))
        depth.ask_price_1 = Decimal(str(asks[0]))
        depth.ask_volume_1 = Decimal(str(asks[1]))
        depth.asks_list = [asks]
        depth.bids_list = [bids]
        return depth

    def is_gateway_ready(self):
        return self.gateway_ready

    async def gateway_async(self):
        """
        """
        # init 
        for sub in self.sub_data_set:
            inst_id = sub.inst_id.lower()

            self.depth_dict[inst_id] = {}
        

        while True:
            try:
                
                async with websockets.connect(USDT_WEBSOCKET_DATA_HOST) as ws:
                    for sub in self.sub_data_set:
                        inst_id = sub.inst_id.lower()

                        sub_str = {
                            "sub": f"market.{inst_id.upper()}.bbo",
                            "id": "id5"
                        }
                        await ws.send(json.dumps(sub_str))
                        self.helper_log_record(f"mbp data: {sub_str}")
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
                        if not self.gateway_ready:
                            self.gateway_ready = True

                        if 'tick' in res:
                            
                            ch = res['ch']
                            ts = res['ts']
                            tick_symbol = ch.split(".bbo")[0].split("market.")[1]

                            tick = res["tick"]
                            tick["ts"] = ts
                            self.depth_dict[tick_symbol] = tick
                            depth = self.depth_transfer(tick_symbol, instTypeEnum.USDTM)

                            if self.listener_depth:
                                self.listener_depth(depth)
                            continue

                        elif "ping" in res:
                            d = {"pong": res["ping"]}
                            await ws.send(json.dumps(d))
                        else:
                            print(res)
                            
            except Exception as e:
                for key, value in self.depth_dict.items():
                    value = {}
                if str(e) == "cannot schedule new futures after shutdown":
                    continue
                self.gateway_ready = False
                self.helper_log_record(f"coroutine_market_increase error: {e}")
                # self.log.info(get_timestmap() + "连接断开，正在重连……" + str(e))
                continue
    
    def gateway_start(self):
        asyncio.run_coroutine_threadsafe(self.gateway_async(), self.loop)


def test_listener(depth: depthData):
    print(f"{depth.time_china} :: {depth.ask_price_1}")
    return

def gateway_test():
    gateway = huobiGatewayMarketUsdtMargin("test")
    gateway.add_listener_depth(test_listener)
    sub = subData()
    sub.inst_id="BTC-USDT"
    gateway.add_strategy_sub(sub)
    gateway.helper_load_exchange_info()

    loop = asyncio.get_event_loop()
    session = loop.run_until_complete(create_session(loop))
    start_event_loop(loop)

    while True:
        print(f"{datetime.now()} :: {loop.is_running()} {loop.is_closed()}")
        if loop.is_running():
            break
        sleep(0.1)
    gateway.add_loop_session(loop, session)
    gateway.gateway_start()
    
    while True:
        sleep(100)

if __name__ == "__main__":
    gateway_test()

