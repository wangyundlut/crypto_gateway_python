import re
import time
from datetime import datetime, timedelta, tzinfo, timezone

TZCHINA = timezone(timedelta(hours=8), 'Asia/Shanghai')
TZUTC = timezone(timedelta(days=0), 'UTC')
TIMEFORMAT = '%Y-%m-%d %H:%M:%S.%f %z'

def dt_china_now_str():
    return datetime.now(tz=TZCHINA).strftime(TIMEFORMAT)

def dt_utz_now_str():
    return datetime.now(tz=TZUTC).strftime(TIMEFORMAT)

def dt_epoch_to_china_str(ts):
    time_local = datetime.fromtimestamp(int(ts) / 1000)
    time_local = time_local.replace(tzinfo=TZCHINA)
    # time_local = CHINA_TZ.localize(time_local)
    return time_local.strftime(TIMEFORMAT)

# print(dt_china_now_str())
# print(dt_utz_now_str())
# ts = 1643265016000
# print(dt_epoch_to_china_str(ts))
