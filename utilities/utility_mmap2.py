from datetime import datetime
import json
import time

import mmap
from utilities.utility_redis import load_redis_connection_pool, load_redis_connection_in_pool

stat_d = {
    "last_time": None,
    "this_time": None,
    "diff": None,
    "num": 0,
    "sum_diff": 0,
    "ave_diff": 0
}
pool = load_redis_connection_pool()
d = {
    "time": "1645002302.814824",
    "strategy": "strategy"
}
with open("/app/projects/py_okex/utilities/hello.txt", "wb") as f:
    f.write((" " * 3000).encode())


# while True:
#     rc = load_redis_connection_in_pool(pool)
#     t = time.time()

#     if not stat_d["last_time"]:
#         stat_d["last_time"] = t
#         stat_d["this_time"] = t
#     else:
#         stat_d["last_time"] = stat_d["this_time"]
#         stat_d["this_time"] = t
#         stat_d["diff"] = stat_d["this_time"] - stat_d["last_time"] - 1
#         stat_d["num"] += 1
#         stat_d["sum_diff"] += stat_d["diff"]
#         stat_d["ave_diff"] = stat_d["sum_diff"] / stat_d["num"]
#         print(stat_d)
#     d["时间"] = str(t)
#     rc.set("test", json.dumps(d))
#     time.sleep(1)


max_len = 200

with open("/app/projects/py_okex/utilities/hello.txt", "r+b") as f:
    while True:
        # memory-map the file, size 0 means whole file
        mm = mmap.mmap(f.fileno(), 0)
        # read content via standard file methods
        # print(mm.readline())  # prints b"Hello Python!\n"
        # read content via slice notation
        # print(mm[:5])  # prints b"Hello"
        # update content using slice notation;

        # note that new content must have same size
        t = time.time()
        t_str = str(t)
        
        d["time"] = t_str

        msg = json.dumps(d)
        # msg = "\"" + json.dumps(f"{str(datetime.now())}") + "\""
        if len(msg) < max_len:
            
            for i in range(max_len - len(msg)):
                msg += " "
                # print(msg)
            # max_len = len(msg)

        # print(len(msg) - max_len)
        print(msg)
        # print(len(msg))
        mm[0:max_len] = msg.encode()
        # mm[:] = msg
       
        # ... and read again using standard file methods
        # mm.seek(0)
        # print(mm.readline())  # prints b"Hello  world!\n"
        # close the map
        # mm.close()
        if not stat_d["last_time"]:
            stat_d["last_time"] = t
            stat_d["this_time"] = t
        else:
            stat_d["last_time"] = stat_d["this_time"]
            stat_d["this_time"] = t
            stat_d["diff"] = stat_d["this_time"] - stat_d["last_time"] - 1
            stat_d["num"] += 1
            stat_d["sum_diff"] += stat_d["diff"]
            stat_d["ave_diff"] = stat_d["sum_diff"] / stat_d["num"]
            # print(stat_d)


        time.sleep(1)