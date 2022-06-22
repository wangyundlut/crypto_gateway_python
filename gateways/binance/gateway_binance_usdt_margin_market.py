
import asyncio
import websockets
import json
import requests
from datetime import datetime, timedelta
import csv
import os
import time


UMARGINURL = "wss://fstream.binance.com"


STREAM = "/stream?streams="

async def save_trades():
    csv_file_dict = {}
    csv_writer_dict = {}
    
    ws_str = UMARGINURL + STREAM
    
    for symbol in ['BTCUSDT', 'ETHUSDT']:
        ws_str += f"{symbol.lower()}@bookTicker/"
    ws_str = ws_str[0:-1]

    last_send_pong_time = datetime.now()
    while True:
        try:
            
            async with websockets.connect(ws_str) as ws:
            
                while True:
                    try:
                        res_b = await asyncio.wait_for(ws.recv(), timeout=10)
                    except (asyncio.TimeoutError, websockets.exceptions.ConnectionClosed) as e:
                        try:
                            # await ws.send('pong')
                            last_send_pong_time = datetime.now()
                            continue
                        except Exception as e:
                            # log.info(f"{instType} send pong error {e}")
                            
                            break
                    res = json.loads(res_b)
                    
                    if '@bookTicker' not in res['stream']:
                        
                        print(res)
                        continue
                    
                    stream = res['stream']
                    symbol = stream.split("@")[0].upper()
                    data = res['data']
                    
                    dt = exchange_time_to_local(data['T'])
                    bid_price = data['b']
                    bid_sz = data['B']
                    ask_price = data['a']
                    ask_sz = data['A']
                    dt_now = int(time.time() * 1000)
                    print(f"delay: {dt_now - data['T']}")
                    # print(f"{symbol} {dt}:{bid_price} {bid_sz}")


        except Exception as e:
            
            print(f" 连接断开，正在重连…… {e}")
            
            continue


def exchange_time_to_local(ts):
    time_local = datetime.utcfromtimestamp(int(ts) / 1000)
    time_local = time_local.replace(tzinfo=None)
    time_local = time_local + timedelta(hours=8)
    # time_local = CHINA_TZ.localize(time_local)
    return time_local


if __name__ == '__main__':
    try:
        

        loop = asyncio.get_event_loop()
        tasks = []
        task = save_trades()
        tasks.append(task) 
       

        loop.run_until_complete(asyncio.gather(*tasks))
        loop.close()
    except Exception as e:
        print(e)
        
