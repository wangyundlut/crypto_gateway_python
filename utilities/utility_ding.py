"""
utility of ding talk
this is a class
all dingding should bind ip

"""

import os
from datetime import datetime
from dingtalkchatbot import chatbot
from .utility_yaml import load_yaml_file

class helper_dingding:

    def __init__(self, yaml_file='ding_debug') -> None:
        self.ding_yaml_file = yaml_file
        self.ding: chatbot.DingtalkChatbot = None
        self.load_ding()
    
    def load_ding(self):
        if self.ding_yaml_file[-4:] != 'yaml':
            filepath =  os.path.join("/app/utility_config", self.ding_yaml_file + ".yml")
        else:
            filepath =  os.path.join("/app/utility_config", self.ding_yaml_file + ".yml")
            
        config_file = load_yaml_file(filepath)
        ding = chatbot.DingtalkChatbot(webhook=config_file['webhook'])
        self.ding = ding
        
    def ding_notice(self, msg, keywords='debug'):
        try:
            # all ding should limit ip, then will send free
            msg = f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ::  {msg}"
            if keywords:
                msg = keywords + " :: " + msg
            self.ding.send_text(msg)

        except Exception as e:
            print(e)

