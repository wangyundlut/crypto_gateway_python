import mmap
from time import sleep
import json
from pprint import pprint
import os
class utility_mmap:
    
    def __init__(self, file_txt, memory_size):
        self.file_txt = file_txt
        self.memory_size = memory_size

        folder_path, file_name = os.path.split(self.file_txt)
        if not os.path.exists(folder_path):
            os.makedirs(os.path.join(folder_path))

        if os.path.exists(self.file_txt):
            f = open(self.file_txt, "r+b", )
        else:
            f = open(self.file_txt, "w+b", )
        self.file = f
    
    def init_file(self):
        
        with open(self.file_txt, "wb") as f:
            f.write((" " * self.memory_size).encode())
    
    def mmap_set(self, d):
        
        mm = mmap.mmap(self.file.fileno(), 0)
        msg = json.dumps(d)
        if len(msg) < self.memory_size:
            for i in range(self.memory_size - len(msg)):
                msg += " "
        mm[0:self.memory_size] = msg.encode()

    def mmap_get(self):
        
        mm = mmap.mmap(self.file.fileno(), 0)
        msg = mm.readline().decode()
        
        msg = msg.replace(" ", "")
        return json.loads(msg)
    