

import asyncio
import json
import websockets
import gzip
from datetime import datetime, timedelta
import urllib
import hmac
import base64
import hashlib

import time
from decimal import Decimal


class huobiGateway:

    def __init__(self):    
        pass

   
    
    async def coroutine_trade(self, api_key, secret_key):
        while True:
            try:
                params_sign = create_signature_v2(api_key, "GET", "https://api-aws.huobi.pro", "/ws/v2", secret_key)
                login_params = {
                    "action": "req", 
                    "ch": "auth",
                    "params": params_sign
                }
                async with websockets.connect("wss://api-aws.huobi.pro/ws/v2") as ws:
                    await ws.send(json.dumps(login_params))
                    res = await asyncio.wait_for(ws.recv(), timeout=25)

                    topic = {
                        "action": "sub",
                        "ch": "accounts.update#2"
                        }

                    await ws.send(json.dumps(topic))
                        

                    while True:
                        try:
                            res = await asyncio.wait_for(ws.recv(), timeout=25)
                        except (asyncio.TimeoutError, websockets.exceptions.ConnectionClosed) as e:
                            try:
                                await ws.send('ping')
                                res = await ws.recv()
                                print(str(datetime.now()) + res)
                                continue
                            except Exception as e:
                                
                                print(str(datetime.now()) + "正在重连……")
                                print(e)
                                break

                        # print(res)
                        res = json.loads(res)
                       

                        if "action" in res:
                            action = res["action"]
                            if action == "ping":
                                d = {
                                    "action": "pong",
                                    "data": {"ts": res["data"]["ts"]}
                                }
                                await ws.send(json.dumps(d))

                            elif action == "push":
                                ch = res["ch"]
                                data = res["data"]

                                if "accounts.update" in ch:
                                    if not data:
                                        continue
                                    
                                    

                            elif action == "sub":
                                
                                if str(res["code"]) == "500":
                                    raise Exception(f"connection error {res}")
                                elif str(res["code"] == "200"):
                                    print("sub topic")
                                    print(res)
                                    
                            else:
                                print("no prepare")
                                print(res)
                        else:
                            print('error message ' )
                            print(res)

            except Exception as e:
                self.trade_ready = False
                print(str(datetime.now()) + " error: coroutine_trade 连接断开，正在重连……" + str(e))
                
                continue

    
def create_signature_v2(
    api_key: str,
    method: str,
    host: str,
    path: str,
    secret_key: str,
    get_params=None
):
    """
    创建WebSocket接口签名
    """
    
    sorted_params: list = [
        ("accessKey", api_key),
        ("signatureMethod", "HmacSHA256"),
        ("signatureVersion", "2.1"),
        ("timestamp", datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S"))
    ]

    if get_params:
        sorted_params.extend(list(get_params.items()))
        sorted_params = list(sorted(sorted_params))
    encode_params = urllib.parse.urlencode(sorted_params)

    host_name = urllib.parse.urlparse(host + path).hostname
    path_name = urllib.parse.urlparse(host + path).path

    payload: list = [method, host_name, path_name, encode_params]
    payload: str = "\n".join(payload)
    payload: str = payload.encode(encoding="UTF8")

    # print(payload)
    secret_key: str = secret_key.encode(encoding="UTF8")

    digest: bytes = hmac.new(secret_key, payload, digestmod=hashlib.sha256).digest()
    signature: bytes = base64.b64encode(digest)

    params = {}
    params["authType"] = "api"
    params.update(dict(sorted_params))

    params["signature"] = signature.decode("UTF8")
    
    return params
