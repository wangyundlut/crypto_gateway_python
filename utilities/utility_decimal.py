"""
utility to process decimal

"""
from decimal import Decimal
from math import floor, ceil


def round_to(value: float or Decimal, target: float or Decimal) -> float or Decimal:
    """
    Round price to price tick value.
    """
    try:
        value = Decimal(str(value))
        target = Decimal(str(target))
        rounded = Decimal(int(round(value / target)) * target)
        if target > 0.5:
            rounded = int(rounded)
    except Exception as e:
        print(e)
    return rounded

def floor_to(value: float or Decimal, target: float or Decimal) -> float or Decimal:
    """
    Similar to math.floor function, but to target float number.
    """
    value = Decimal(str(value))
    target = Decimal(str(target))
    result = Decimal(int(floor(value / target)) * target)
    if target > 0.5:
        result = int(result)
    return result

def ceil_to(value: float or Decimal, target: float or Decimal) -> float or Decimal:
    """
    Similar to math.ceil function, but to target float number.
    """
    value = Decimal(str(value))
    target = Decimal(str(target))
    result = Decimal(int(ceil(value / target)) * target)
    if target > 0.5:
        result = int(result)
    return result

def get_digits(value: float) -> int:
    """
    Get number of digits after decimal point.
    """
    value_str = str(value)

    if "e-" in value_str:
        _, buf = value_str.split("e-")
        return int(buf)
    elif "." in value_str:
        _, buf = value_str.split(".")
        return len(buf)
    else:
        return 0

