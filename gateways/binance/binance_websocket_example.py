import asyncio 
import websockets 
import json 
from time import sleep  

async def hello():     
    url = "wss://stream.binance.com:9443/stream?streams="     
    async with websockets.connect(url) as websocket:        
        # channels = {"method": "SUBSCRIBE","params":["btcusdt@bookTicker","btcusdt@depth"],"id": 1}    
        channels = {"method": "SUBSCRIBE","params":["btcusdt@bookTicker"],"id": 1}              
        await websocket.send(json.dumps(channels))         
        while True:             
            try:                 
                greeting = await websocket.recv()                
                print(f"result: {greeting}")             
            except Exception as e:                 
                print(f"wrong: {e}")                  
                sleep(5) 

asyncio.get_event_loop().run_until_complete(hello())