from dataclasses import dataclass, field
import time
from decimal import Decimal

@dataclass
class orderError:
    SERVICE = "Service temporarily unavailable, please try again later."
    FREQUENT = "Requests too frequent."
    
    INSUFFICIENTBALANCE =  "Order placement failed due to insufficient balance"
    MINORDERSIZE = "Order amount should be greater than the min available amount."
    MULTIPLESIZE = "Order count should be the integer multiples of the lot size"
    

@dataclass
class cancelOrderError:
    SERVICE = "Service temporarily unavailable, please try again later."
    FREQUENT = "Requests too frequent."

    NOTEXIST = "Cancellation failed as the order does not exist."
    

@dataclass
class amendOrderError:
    SERVICE = "Service temporarily unavailable, please try again later."
    FREQUENT = "Requests too frequent."

    CANCELED = "Modification failed as the order has been canceled."
    COMPLETED = "Modification failed as the order has been completed."
    CLIORDERID = "Either client order ID or order ID is required."
    


