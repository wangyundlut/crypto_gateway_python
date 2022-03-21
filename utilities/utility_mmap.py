import mmap
from time import sleep
import json
from pprint import pprint

with open("hello.txt", "r+b") as f:
    while True:
        # memory-map the file, size 0 means whole file
        mm = mmap.mmap(f.fileno(), 0)
        # read content via standard file methods
        # print(mm.readline())  # prints b"Hello Python!\n"
        msg = mm.readline().decode()
        
        msg = msg.replace(" ", "")
        pprint(json.loads(msg))
        # read content via slice notation
        # print(mm[:5])  # prints b"Hello"
        # update content using slice notation;

        # note that new content must have same size
        # mm[6:] = b" world!\n"
        # ... and read again using standard file methods
        # mm.seek(0)
        # print(mm.readline())  # prints b"Hello  world!\n"
        # close the map
        # mm.close()
        sleep(1)