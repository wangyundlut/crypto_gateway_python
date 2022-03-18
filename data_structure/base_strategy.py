from base_class.base_data_struct import(
    depthData,
    accountData,
    positionData,
    orderData
)
from base_class.base_strategy_engine import baseStrategyEngine

class strategyTemplate(baseStrategyEngine):
    def __init__(self) -> None:
        self.strategy_name = ''

    async def depth_listener(self, depth: depthData):
        print(f"{depth.inst_id_local} {depth.time_china}, {depth.ask_price_1}")

    async def account_listener(self, account: accountData):
        print(account)

    async def position_listener(self, position: positionData):
        print(position)
    
    async def order_listener(self, order: orderData):
        print(order)

    async def fill_listener(self, fill: orderData):
        print(fill)

    async def ws_listener(self, ws_info:str):
        print(ws_info)
        

   
