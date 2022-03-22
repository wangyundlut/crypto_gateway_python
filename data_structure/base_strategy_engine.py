from .base_data_struct import(
    depthData,
    accountData,
    positionData,
    orderData,
    fillData
)
from .base_gateway import baseGateway
HOURS8=8

class baseStrategyEngine:
    def __init__(self) -> None:
        self.strategy_name = ''
        self.gateaway_map = {}

    def add_gateway(self, gateway: baseGateway):
        self.gateaway_map[gateway.gateway_name] = baseGateway

    async def depth_listener(self, depth: depthData):
        pass

    async def account_listener(self, account: accountData):
        pass

    async def position_listener(self, position: positionData):
        pass
    
    async def order_listener(self, order: orderData):
        pass

    async def fill_listener(self, fill: fillData):
        pass

    async def ws_listener(self, ws_info: str):
        pass

   
