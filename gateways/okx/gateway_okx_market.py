import asyncio
import zlib
import websockets
import json
from datetime import datetime
from decimal import Decimal
from time import time, sleep


from crypto_gateway_python.utilities.utility_time import dt_china_now_str, dt_epoch_to_china_str
from crypto_gateway_python.data_structure.base_gateway import baseGatewayMarket
from crypto_gateway_python.data_structure.base_data_struct import(
    depthData,
    subChannelEnum,
    timeOutData,
    instTypeEnum,
    subData,
)
from crypto_gateway_python.gateways.okx.public_helper import (
    okx_get_inst_id_local,
    okx_get_account_ccy,
    okx_load_exchange_info,
    helper_get_price
)
from crypto_rest_python.okx.sync_rest.rest_v5 import okx_api_v5
from crypto_rest_python.okx.sync_rest.consts import (
    EXCHANGE_NAME,
    WS_PUB_URL,
    WS_PUB_URL_SIMULATION,
)

HOURS8=8
ZERODECIMAL = Decimal("0")




class okxGatewayMarket(baseGatewayMarket):
    def __init__(self, gateway_name='') -> None:
        baseGatewayMarket.__init__(self, gateway_name=gateway_name)
        self.exchange_name = EXCHANGE_NAME
        self.websocketPubUrl = WS_PUB_URL
    
    ##################basic log and async function##############################
    def helper_get_inst_id_local(self, inst_id: str, inst_type: str = ""):
        return okx_get_inst_id_local(inst_id, inst_type)

    def helper_get_account_ccy(self, ccy: str, inst_id: str = "", inst_type: str = ""):
        return okx_get_account_ccy(ccy, inst_id, inst_type)

    ##################basic log and async function##############################


    ##################load rest##############################
    # okx market is special, depth50, must log in ..
    def add_config_account(self, account_config={
        "exchange": "okx",
        "apiKey": "",
        "passPhrase": "",
        "secretKey": "",
        "isTest": True,
        "account_name": "",
    }):
        """
        this is a json dict
        after add config account, load rest

        exchange: "okx"
        apiKey: ''
        passPhrase: ''
        secretKey: ''
        isTest: True
        account_name: ''
        """
        assert account_config['exchange'] == self.exchange_name

        self.account_config = account_config
        self.account_name = account_config["account_name"]

        isTest = self.account_config['isTest']
        if isTest:
            self.websocketPubUrl = WS_PUB_URL_SIMULATION

        self.rest = okx_api_v5(
            api_key=self.account_config['apiKey'],
            api_secret_key=self.account_config['secretKey'],
            passphrase=self.account_config['passPhrase'],
            test=isTest
        )
        return

    def helper_load_exchange_info(self):
        inst_id_info = okx_load_exchange_info(self.rest)
        self.inst_id_info = inst_id_info
        return


    ##################load rest##############################


    ##################exchange helper##############################
    """
    get price, info .....
    """
    def helper_get_price(self, inst_id: str, inst_type: str=""):
        return helper_get_price(inst_id, self.rest)

    ##################exchange helper##############################

    ##################market gateway ##############################
    async def gateway_async(self):
        time_out_max_seconds = 25

        def get_timestamp():
            # now = datetime.now()
            # t = now.isoformat("T", "milliseconds")
            # return t + "Z"
            return str(datetime.now())

        def partial(data):
            bids = data['bids']
            asks = data['asks']
            # instrument_id = data_obj['instrument_id']
            # print(timestamp + '全量数据bids为：' + str(bids))
            # print('档数为：' + str(len(bids)))
            # print(timestamp + '全量数据asks为：' + str(asks))
            # print('档数为：' + str(len(asks)))
            return bids, asks

        def update_bids(data, bids_p, timestamp=None):
            # 获取增量bids数据
            bids_u = data['bids']
            # print(timestamp + '增量数据bids为：' + str(bids_u))
            # print('档数为：' + str(len(bids_u)))
            # bids合并
            for i in bids_u:
                bid_price = i[0]
                for j in bids_p:
                    if bid_price == j[0]:
                        if i[1] == '0':
                            bids_p.remove(j)
                            break
                        else:
                            del j[1]
                            j.insert(1, i[1])
                            break
                else:
                    if i[1] != "0":
                        bids_p.append(i)
            else:
                bids_p.sort(key=lambda price: sort_num(price[0]), reverse=True)
                # print(timestamp + '合并后的bids为：' + str(bids_p) + '，档数为：' + str(len(bids_p)))
            return bids_p

        def update_asks(data, asks_p, timestamp=None):
            # 获取增量asks数据
            asks_u = data['asks']
            # print(timestamp + '增量数据asks为：' + str(asks_u))
            # print('档数为：' + str(len(asks_u)))
            # asks合并
            for i in asks_u:
                ask_price = i[0]
                for j in asks_p:
                    if ask_price == j[0]:
                        if i[1] == '0':
                            asks_p.remove(j)
                            break
                        else:
                            del j[1]
                            j.insert(1, i[1])
                            break
                else:
                    if i[1] != "0":
                        asks_p.append(i)
            else:
                asks_p.sort(key=lambda price: sort_num(price[0]))
                # print(timestamp + '合并后的asks为：' + str(asks_p) + '，档数为：' + str(len(asks_p)))
            return asks_p

        def sort_num(n):
            if n.isdigit():
                return int(n)
            else:
                return Decimal(n)

        def check(bids, asks):
            # 获取bid档str
            bids_l = []
            bid_l = []
            count_bid = 1
            while count_bid <= 25:
                if count_bid > len(bids):
                    break
                bids_l.append(bids[count_bid-1])
                count_bid += 1
            for j in bids_l:
                str_bid = ':'.join(j[0 : 2])
                bid_l.append(str_bid)
            # 获取ask档str
            asks_l = []
            ask_l = []
            count_ask = 1
            while count_ask <= 25:
                if count_ask > len(asks):
                    break
                asks_l.append(asks[count_ask-1])
                count_ask += 1
            for k in asks_l:
                str_ask = ':'.join(k[0 : 2])
                ask_l.append(str_ask)
            # 拼接str
            num = ''
            if len(bid_l) == len(ask_l):
                for m in range(len(bid_l)):
                    num += bid_l[m] + ':' + ask_l[m] + ':'
            elif len(bid_l) > len(ask_l):
                # bid档比ask档多
                for n in range(len(ask_l)):
                    num += bid_l[n] + ':' + ask_l[n] + ':'
                for l in range(len(ask_l), len(bid_l)):
                    num += bid_l[l] + ':'
            elif len(bid_l) < len(ask_l):
                # ask档比bid档多
                for n in range(len(bid_l)):
                    num += bid_l[n] + ':' + ask_l[n] + ':'
                for l in range(len(bid_l), len(ask_l)):
                    num += ask_l[l] + ':'

            new_num = num[:-1]
            int_checksum = zlib.crc32(new_num.encode())
            fina = change(int_checksum)
            return fina

        def change(num_old):
            num = pow(2, 31) - 1
            if num_old > num:
                out = num_old - num * 2 - 2
            else:
                out = num_old
            return out

        def get_sub_str():
            channels_list = []
            for sub in self.sub_data_set:
                # depth
                channel = sub.channel
                inst_id = sub.inst_id
                inst_type = sub.inst_type
                inst_id_local = self.helper_get_inst_id_local(inst_id, inst_type)
                info = self.inst_id_info[inst_id_local]
                # TODO: add other channel
                if channel == subChannelEnum.DEPTH50:
                    channels_list.append({'channel': 'books50-l2-tbt', 'instId': info.inst_id.upper()})
                elif channel == subChannelEnum.DEPTH:
                    channels_list.append({'channel': 'bbo-tbt', 'instId': info.inst_id.upper()})
                elif channel == subChannelEnum.FUNDINGRATE:
                    channels_list.append({'channel': 'funding-rate', 'instId': info.inst_id.upper()})
                elif channel == subChannelEnum.PRICELIMIT:
                    channels_list.append({'channel': 'price-limit', 'instId': info.inst_id.upper()})
                elif channel == subChannelEnum.MARKETTRADE:
                    channels_list.append({'channel': 'trades', 'instId': info.inst_id.upper()})

            return json.dumps({"op": "subscribe", "args": channels_list})

        def get_time_out_data():
            todata = timeOutData()
            todata.gateway_name = self.gateway_name
            todata.exchange_name = self.exchange_name
            todata.event = "no receive market data long time."
            todata.send_time_china = dt_china_now_str()
            todata.time_delay = time_out_max_seconds
            return todata
        
        async def update_depth50(res):
            arg = res['arg']
            instId = arg['instId']
            action = res['action']
            data = res['data'][0]
            inst_id_local = self.helper_get_inst_id_local(instId)
            info = self.inst_id_info[inst_id_local]

            # 订阅频道是深度频道
            # 全量
            if action == 'snapshot':
                bids_p, asks_p = partial(data)

                depth = depthData()
                depth.gateway_name = self.gateway_name
                depth.exchange = self.exchange_name
                depth.inst_type = info.inst_type
                depth.inst_id = info.inst_id
                depth.inst_id_local = info.inst_id_local
                depth.time_epoch = Decimal(data["ts"])
                depth.time_china = dt_epoch_to_china_str(depth.time_epoch)
                depth.asks_list = asks_p
                depth.bids_list = bids_p

                depth.ask_price_1 = Decimal(asks_p[0][0])
                depth.ask_volume_1 = Decimal(asks_p[0][1])

                depth.bid_price_1 = Decimal(bids_p[0][0])
                depth.bid_volume_1 = Decimal(bids_p[0][1])

                depth.other_data["checksum"] = data["checksum"]
                
                self.depth_data[depth.inst_id_local] = depth
                # 校验checksum
                checksum = data['checksum']
                check_num = check(bids_p, asks_p)

                if check_num == checksum:
                    self.helper_log_record(f"{instId} 校验结果为: True snapshot  Done")
                else:
                    self.helper_log_record(f"{instId} 校验结果为: False, 正在重新订阅……")
                    ################### unsubscribe ###################
                    unsubscribe = {
                        "op": "unsubscribe", "args": [{"channel": "books50-l2-tbt", "instId": instId}]
                    }
                    self.helper_log_record(unsubscribe)

                    await self.ws_market.send(json.dumps(unsubscribe))
                    return
                return

            elif action == 'update':
                depth = self.depth_data[inst_id_local]

                # 获取合并后数据
                depth.bids_list = update_bids(data, depth.bids_list)
                depth.asks_list = update_asks(data, depth.asks_list)
                depth.other_data['checksum'] = data["checksum"]
                depth.time_epoch = Decimal(data["ts"])
                depth.time_china = dt_epoch_to_china_str(depth.time_epoch)
                
                # 校验checksum
                checksum = data['checksum']
                check_num = check(depth.bids_list, depth.asks_list)

                # if miss depth
            
                if check_num != checksum:
                    self.helper_log_record(f"{instId} 校验结果为: False, 正在重新订阅……")
                    
                    ################### unsubscribe ###################
                    unsubscribe = {
                        "op": "unsubscribe", "args": [{"channel": "books50-l2-tbt", "instId": instId}]
                    }
                    self.helper_log_record(unsubscribe)
                    await self.ws_market.send(json.dumps(unsubscribe))
                    return

                ############ push data ############
                if self.listener_depth:
                    self.listener_depth(self.depth_data[inst_id_local])

        async def update_depth(res):
            
            arg = res['arg']
            instId = arg['instId']
            data = res['data'][0]
            inst_id_local = self.helper_get_inst_id_local(instId)
            info = self.inst_id_info[inst_id_local]

            if inst_id_local in self.depth_data:
                depth = self.depth_data[inst_id_local]
            else:
                depth = depthData()
                depth.gateway_name = self.gateway_name
                depth.exchange = self.exchange_name
                depth.inst_type = info.inst_type
                depth.inst_id = info.inst_id
                depth.inst_id_local = info.inst_id_local

            depth.time_epoch = Decimal(data["ts"])
            depth.time_china = dt_epoch_to_china_str(depth.time_epoch)
            depth.ask_price_1 = Decimal(data["asks"][0][0])
            depth.ask_volume_1 = Decimal(data["asks"][0][1])

            depth.bid_price_1 = Decimal(data["bids"][0][0])
            depth.bid_volume_1 = Decimal(data["bids"][0][1])
            self.depth_data[depth.inst_id_local] = depth

            ############ push data ############
            if self.listener_depth:
                self.listener_depth(self.depth_data[inst_id_local])

        async def update_fee(res):
            pass

        async def update_price_limit(res):
            # TODO
            arg = res['arg']
            instId = arg['instId']
            data = res['data'][0]
            inst_id_local = self.helper_get_inst_id_local(instId)

            self.price_limit_data[inst_id_local] = data
            """
            "instId": "LTC-USD-190628",
            "buyLmt": "300",
            "sellLmt": "200",
            "ts": "1597026383085"
            """
            if self.listener_price_limit:
                self.listener_price_limit(self.price_limit_data[inst_id_local])

        self.helper_log_record(f"market_engine, start ...")

        while True:
            try:
                async with websockets.connect(self.websocketPubUrl) as self.ws_market:
                    sub_channel_str = get_sub_str()
                    self.helper_log_record(f"{self.exchange_name}, market_engine, send: {sub_channel_str}")
                    await self.ws_market.send(sub_channel_str)

                    while True:
                        try:
                            res = await asyncio.wait_for(self.ws_market.recv(), timeout=time_out_max_seconds)
                        except (asyncio.TimeoutError, websockets.exceptions.ConnectionClosed) as e:
                            try:
                                if self.listener_time_out:
                                    self.listener_time_out(get_time_out_data())

                                await self.ws_market.send('ping')
                                res = await self.ws_market.recv()
                                continue

                            except Exception as e:
                                timestamp = get_timestamp()
                                self.helper_log_record(f"{timestamp} market channel 正在重连…… error: {e}")
                                break

                        
                        res = json.loads(res)
                        self.gateway_ready = True
                        ####################################################
                        if 'event' in res:
                            # check if depth checksum error ..
                            self.helper_log_record(f"event res: {res}")
                            # for okx, small change checksum will return false, but actually is true
                            # in this case , just re sub is fine
                            if res['event'] == 'unsubscribe':
                                if res['arg']['channel'] == 'books50-l2-tbt':
                                    subscribe = {
                                        "op": "subscribe", "args": [{"channel": "books50-l2-tbt", "instId": res['arg']['instId']}]
                                    }
                                    await self.ws_market.send(json.dumps(subscribe))
                            continue
                        
                        ####################################################

                        channel = res['arg']['channel']
                        
                        if channel == 'books50-l2-tbt':
                           await update_depth50(res)
                        elif channel == "bbo-tbt":
                            await update_depth(res)
                        elif channel == 'price-limit':
                            await update_price_limit(res)
                        elif channel == "funding-rate":
                            await update_fee(res)

            except Exception as e:

                if 'cannot schedule new FUTURES after shutdown' in str(e):
                    pass
                elif 'no running event loop' in str(e):
                    pass
                else:
                    self.helper_log_record(f"market_engine_async error: {e}")
                # print(timestamp + f" subscribe_market_data error: {e}")
                self.ws = None
                self.gateway_ready = False
                continue

    def gateway_start(self):
        asyncio.run_coroutine_threadsafe(self.gateway_async(), self.loop)


def gateway_test():
    def listener(data):
        print(data)

    loop = asyncio.get_event_loop()
    from crypto_rest_python.async_rest_client import create_session, start_event_loop
    session =loop.run_until_complete(create_session(loop))
    start_event_loop(loop)

    gateway = okxGatewayMarket("test")
    gateway.add_loop_session(loop, session)
    gateway.add_config_account()
    gateway.helper_load_exchange_info()

    sub = subData()
    # okx is very strange, DEPTH50 market data need log in.
    sub.channel = subChannelEnum.DEPTH
    sub.inst_type = instTypeEnum.SPOT
    sub.inst_id = "btc-usdt"
    gateway.add_strategy_sub(sub)

    gateway.add_listener_depth(listener)
    gateway.gateway_start()
    
    while True:
        sleep(60)


if __name__ == "__main__":
    gateway_test()



