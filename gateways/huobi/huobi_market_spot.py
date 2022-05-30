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
    huobi_load_exchange_info,
    helper_get_price_spot,
)

from crypto_rest_python.huobi.sync_rest.consts import (
    EXCHANGE_NAME,
    SPOT_WEBSOCKET_DATA_HOST,
    SPOT_WEBSOCKET_MBP_DATA_HOST
)


HOURS8=8
ZERODECIMAL = Decimal("0")


class huobiGatewayMarketSpot(baseGatewayMarket):
    def __init__(self, gateway_name='') -> None:
        baseGatewayMarket.__init__(self, gateway_name=gateway_name)
        self.exchange_name = EXCHANGE_NAME
        self.websocketPubUrl = SPOT_WEBSOCKET_DATA_HOST
        self.websocketMBP = SPOT_WEBSOCKET_MBP_DATA_HOST
    
        self.depth_dict = {} # "btcusdt": {tick}
        self.depth_increase_list = {} # "btcusdt": []}
        self.depth_seq_num = {} # "btcusdt": {tick}
        self.gateway_ready_mbp = False
        self.gateway_ready_refresh = False
    
    ##################basic log and async function##############################
    def helper_get_inst_id_local(self, inst_id: str, inst_type: str = ""):
        return huobi_get_inst_id_local(inst_id, inst_type)

    def helper_get_account_ccy(self, ccy: str, inst_id: str = "", inst_type: str = ""):
        return huobi_get_account_ccy(ccy, inst_id, inst_type)

    ##################basic log and async function##############################

    ##################load rest##############################
    def helper_load_exchange_info(self):
        
        inst_id_info = huobi_load_exchange_info()
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
    def depth_transfer(self, inst_id: str, inst_type: str=""):
        data = self.depth_dict[inst_id]
        inst_id_local = self.helper_get_inst_id_local(inst_id, inst_type)
        info = self.inst_id_info[inst_id_local]

        ts = data["ts"]
        asks = data["asks"]
        bids = data["bids"]
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
        depth.bid_price_1 = Decimal(str(bids[0][0]))
        depth.bid_volume_1 = Decimal(str(bids[0][1]))
        depth.ask_price_1 = Decimal(str(asks[0][0]))
        depth.ask_volume_1 = Decimal(str(asks[0][1]))
        depth.asks_list = asks
        depth.bids_list = bids
        return depth

    def is_gateway_ready(self):
        return self.gateway_ready_refresh and self.gateway_ready_mbp

    async def gateway_async(self):
        """
        depth_dict: save the newest
        depth_dict_refresh: save the fresh 
        depth_dict_increase: save the increase
        1 start depth_dict_increase, save increase
        2 start depth_dict_refresh, save refresh as the newest depth_dict
        3 when found depth_dict, update depth_dict from refresh + increase
        4 update depth_dict if refresh is the newest
        5 update depth_dict if increase is the newest
        6 when market server break down, clear depth_dict
        """
        # init 
        for sub in self.sub_data_set:
            inst_id = sub.inst_id.lower()

            self.depth_dict[inst_id] = {}
            self.depth_increase_list[inst_id] = []
            self.depth_seq_num[inst_id] = 0

        def update_bids(data, bids_p):
            # 获取增量bids数据
            bids_u = data['bids']
            # print(timestamp + '增量数据bids为：' + str(bids_u))
            # print('档数为：' + str(len(bids_u)))
            # bids合并
            for i in bids_u:
                bid_price = i[0]
                for j in bids_p:
                    if bid_price == j[0]:
                        if i[1] == 0.0:
                            bids_p.remove(j)
                            break
                        else:
                            del j[1]
                            j.insert(1, i[1])
                            break
                else:
                    if i[1] != 0.0:
                        bids_p.append(i)
            else:
                bids_p.sort(key=lambda price: Decimal(str(price[0])), reverse=True)
                # print(timestamp + '合并后的bids为：' + str(bids_p) + '，档数为：' + str(len(bids_p)))
            return bids_p

        def update_asks(data, asks_p):
            # 获取增量asks数据
            asks_u = data['asks']
            # print(timestamp + '增量数据asks为：' + str(asks_u))
            # print('档数为：' + str(len(asks_u)))
            # asks合并
            for i in asks_u:
                ask_price = i[0]
                for j in asks_p:
                    if ask_price == j[0]:
                        if i[1] == 0.0:
                            asks_p.remove(j)
                            break
                        else:
                            del j[1]
                            j.insert(1, i[1])
                            break
                else:
                    if i[1] != 0.0:
                        asks_p.append(i)
            else:
                asks_p.sort(key=lambda price: Decimal(str(price[0])))
                # print(timestamp + '合并后的asks为：' + str(asks_p) + '，档数为：' + str(len(asks_p)))
            return asks_p

        def sort_num(n: str):
            if n.isdigit():
                return int(n)
            else:
                return Decimal(n)

        while True:
            try:
                
                async with websockets.connect(SPOT_WEBSOCKET_MBP_DATA_HOST) as ws:
                    for sub in self.sub_data_set:
                        inst_id = sub.inst_id.lower()

                        sub_str = {
                            "sub": f"market.{inst_id.lower()}.mbp.5",
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
                        if not self.gateway_ready_mbp:
                            self.gateway_ready_mbp = True

                        if 'tick' in res:
                            
                            ch = res['ch']
                            ts = res['ts']
                            tick_symbol = ch.split(".mbp")[0].split("market.")[1]

                            tick_new = res["tick"]
                            tick_new["ts"] = ts
                            
                            if not self.depth_seq_num[tick_symbol]:
                                # self.log_record(f"update by increase, append: {tick_symbol} {tick_new}")
                                self.depth_increase_list[tick_symbol].append(tick_new)
                                continue

                            # update by MBP, continue
                            
                            if self.depth_seq_num[tick_symbol] == tick_new["prevSeqNum"]:
                                self.depth_dict[tick_symbol]["seqNum"] = tick_new["seqNum"]
                                self.depth_dict[tick_symbol]["prevSeqNum"] = tick_new["prevSeqNum"]
                                self.depth_dict[tick_symbol]["ts"] = tick_new["ts"]

                                if "asks" in tick_new:
                                    asks = update_asks(tick_new, self.depth_dict[tick_symbol]["asks"])
                                    self.depth_dict[tick_symbol]["asks"] = asks
                                if "bids" in tick_new:
                                    bids = update_bids(tick_new, self.depth_dict[tick_symbol]["bids"])
                                    self.depth_dict[tick_symbol]["bids"] = bids

                                self.depth_seq_num[tick_symbol] = tick_new["seqNum"]
                                #
                                
                                depth = self.depth_transfer(f"{tick_symbol}", instTypeEnum.SPOT)
                                if not depth:
                                    continue

                                
                                if self.listener_depth:
                                    self.listener_depth(depth)
                                continue
                            else:
                                self.depth_increase_list[tick_symbol].append(tick_new)
                            # update by MBP, increase + depth
                            for tick_increase in self.depth_increase_list[tick_symbol]:
                                if tick_increase["seqNum"] > self.depth_seq_num[tick_symbol]:
                                    # update
                                    self.depth_dict[tick_symbol]["seqNum"] = tick_increase["seqNum"]
                                    self.depth_dict[tick_symbol]["prevSeqNum"] = tick_increase["prevSeqNum"]
                                    self.depth_dict[tick_symbol]["ts"] = tick_increase["ts"]

                                    if "asks" in tick_increase:
                                        asks = update_asks(tick_increase, self.depth_dict[tick_symbol]["asks"])
                                        self.depth_dict[tick_symbol]["asks"] = asks
                                    if "bids" in tick_increase:
                                        bids = update_bids(tick_increase, self.depth_dict[tick_symbol]["bids"])
                                        self.depth_dict[tick_symbol]["bids"] = bids
                                    self.depth_seq_num[tick_symbol] = tick_increase["seqNum"]

                            self.depth_increase_list[tick_symbol] = []

                            # change and push

                            depth = self.depth_transfer(f"{tick_symbol}", instTypeEnum.SPOT)
                            if not depth:
                                continue
                            
                            if self.listener_depth:
                                self.listener_depth(depth)

                        elif "ping" in res:
                            d = {"pong": res["ping"]}
                            await ws.send(json.dumps(d))
                            
                        else:
                            print(res)
                            

            except Exception as e:
                for key, value in self.depth_dict.items():
                    value = {}
                for key, value in self.depth_increase_list.items():
                    value = []
                for key, value in self.depth_seq_num.items():
                    value = 0
                if str(e) == "cannot schedule new futures after shutdown":
                    continue
                self.gateway_ready_mbp = False
                self.helper_log_record(f"coroutine_market_increase error: {e}")
                # self.log.info(get_timestmap() + "连接断开，正在重连……" + str(e))
                continue
    
    async def gateway_async_refresh(self):
        while True:
            try:
                await asyncio.sleep(1)
                async with websockets.connect(SPOT_WEBSOCKET_DATA_HOST) as ws:
                    
                    for sub in self.sub_data_set:
                        inst_id = sub.inst_id.lower()
                        sub_str = {
                            "sub": f"market.{inst_id}.mbp.refresh.5",
                            "id": "id5"
                        }
                        self.helper_log_record(f"send: refresh: {sub_str}")
                        await ws.send(json.dumps(sub_str))

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
                        # self.log_record(res)
                        if not self.gateway_ready_refresh:
                            self.gateway_ready_refresh = True

                        if 'tick' in res:
                            
                            ch = res['ch']
                            ts = res['ts']
                            tick = res['tick']
                            tick_symbol = ch.split(".mbp")[0].split("market.")[1]
                            tick["ts"] = ts
                            seqNum = tick["seqNum"]
                            
                            if not self.depth_seq_num[tick_symbol]:
                                self.depth_dict[tick_symbol] = tick
                                self.depth_seq_num[tick_symbol] = seqNum
                                
                                continue
                            else:
                                if seqNum >= self.depth_seq_num[tick_symbol]:

                                    self.depth_dict[tick_symbol]["ts"] = ts
                                    self.depth_dict[tick_symbol]["seqNum"] = seqNum
                                    self.depth_dict[tick_symbol]["asks"] = tick["asks"]
                                    self.depth_dict[tick_symbol]["bids"] = tick["bids"]
                                    
                                    self.depth_seq_num[tick_symbol] = seqNum
                                    
                                    # 
                                    depth = self.depth_transfer(tick_symbol, instTypeEnum.SPOT)
                                    
                                    if self.listener_depth:
                                        self.listener_depth(depth)

                        elif "ping" in res:
                            d = {"pong": res["ping"]}
                            await ws.send(json.dumps(d))

                        else:
                            print(res)
                        

            except Exception as e:
                for key, value in self.depth_dict.items():
                    value = {}
                for key, value in self.depth_increase_list.items():
                    value = []
                for key, value in self.depth_seq_num.items():
                    value = 0
                if str(e) == "cannot schedule new futures after shutdown":
                    continue
                self.gateway_ready_refresh = False
                self.helper_log_record(f"coroutine_market_refresh error: {e}")
                
                continue

    def gateway_start(self):
        asyncio.run_coroutine_threadsafe(self.gateway_async(), self.loop)
        asyncio.run_coroutine_threadsafe(self.gateway_async_refresh(), self.loop)

def test_listener(depth: depthData):
    return
    print(f"{depth.time_china} :: {depth.ask_price_1}")

def gateway_test():
    gateway = huobiGatewayMarketSpot("test")
    gateway.add_listener_depth(test_listener)
    sub = subData()
    sub.inst_id="btcusdt"
    gateway.add_strategy_sub(sub)
    gateway.helper_load_exchange_info()

    async def simulate_market():
        while True:
            print(f"simulate {datetime.now()}")
            await asyncio.sleep(10)

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

