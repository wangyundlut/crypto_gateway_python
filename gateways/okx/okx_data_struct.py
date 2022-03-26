from dataclasses import dataclass
from decimal import Decimal
from crypto_gateway_python.data_structure.base_data_struct import (
    instTypeData,
    instInfoData,
    depthData,
    orderSendData,
    orderStateData,
    cancelOrderSendData,
    amendOrderSendData,
    contractTypeData,
    orderSideData
)
@dataclass
class depthDataokx(depthData):
    checksum: int = 0


@dataclass
class orderSendDataokx(orderSendData):
    ws_id: str = ""
    def sz_change(self, info: instInfoData):
        # for futures, swap
        if info.inst_type in [instTypeData.FUTURES, instTypeData.SWAP]:
            ctValCcy = info.con_val_ccy
            ctVal = info.con_val
            # have been changed your self
            if self.ccy == "" or self.ccy == "contract":
                return

            # coin base contract
            if info.con_val_ccy != "usd":
                if self.ccy == ctValCcy:
                    self.sz = Decimal(int(self.sz / ctVal))
                    
            # usd base contract
            elif info.con_val_ccy == "usd":
                if self.ccy == "usd":
                    self.sz = Decimal(int(self.sz / ctVal))
    
    def price_limit(self, data: dict):
        if self.side == orderSideData.BUY and self.px > Decimal(data['buyLmt']):
            self.px = Decimal(data['buyLmt'])
        elif self.side == orderSideData.SELL and self.px < Decimal(data['sellLmt']):
            self.px = Decimal(data['sellLmt'])
        


@dataclass
class cancelOrderSendDataokx(cancelOrderSendData):
    ws_id: str = ""
    # priority ord_id

@dataclass
class amendOrderSendDataokx(amendOrderSendData):
    ws_id: str = ""
    def sz_change(self, info: instInfoData):
        # for futures, swap
        if info.inst_type in [instTypeData.FUTURES, instTypeData.SWAP]:
            ctValCcy = info.con_val_ccy
            ctVal = info.con_val
            # have been changed your self
            if self.ccy == "" or self.ccy == "contract":
                return

            # coin base contract
            if info.con_val_ccy != "usd":
                if self.ccy == ctValCcy:
                    self.new_sz = Decimal(int(self.new_sz / ctVal))
                    
            # usd base contract
            elif info.con_val_ccy == "usd":
                if self.ccy == "usd":
                    self.new_sz = Decimal(int(self.new_sz / ctVal))
    

inst_type_map = {
    "SPOT": instTypeData.SPOT,
    "FUTURES": instTypeData.FUTURES,
    "SWAP": instTypeData.SWAP
}

inst_type_map_reverse = {}
for key, value in inst_type_map.items():
    inst_type_map_reverse[value] = key


order_state_map = {
    "canceled": orderStateData.CANCELED,
    "live": orderStateData.SUBMITTED,
    "partially_filled": orderStateData.PARTIALFILLED,
    "filled": orderStateData.FILLED
}

order_state_map_reverse = {}
for key, value in order_state_map.items():
    order_state_map_reverse[value] = key



