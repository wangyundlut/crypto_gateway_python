"""
utility for log.
default log root path :LOGROOTPATH

strategy_name/account_name/{inst_id_local}_date.log

default log name: tempt/{datetime}.day
parameters: {strategyname}/{details}.log
"""
import os
from datetime import datetime, timedelta
import logging
from logging.handlers import TimedRotatingFileHandler
from logging.handlers import RotatingFileHandler
from .utility_common_path import COMMON_PATH

LOGROOTPATH = os.path.join(COMMON_PATH, "log")
DEFAULTLOGFILEPATH = 'tempt'

def load_file_log(name=None):
    """
    name with path such as , strategy/double_ma
    """
    
    logname = ''
    # 1 if not name, default log in default path
    if not name:
        logname = os.path.join(LOGROOTPATH, DEFAULTLOGFILEPATH, f"{datetime.now().strftime('%Y-%m-%d')}.log")
    # 2 if name, must have subpath, or will in tempt path
    else:
        if not ('/' in name):
            logname = os.path.join(LOGROOTPATH, DEFAULTLOGFILEPATH, name)
        else:
            logname = os.path.join(LOGROOTPATH, name)
    if logname[-4:] != '.log':
        logname += '.log'

    # 3 makedir
    folder_path, file_name = os.path.split(logname)
    if not os.path.exists(folder_path):
        os.makedirs(os.path.join(folder_path))

    logger = logging.getLogger(str(datetime.now()))
    logger.handlers = []
    logger.setLevel(level=logging.INFO)
    
    handler = logging.FileHandler(logname)
    handler.setLevel(logging.INFO)
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    handler.setFormatter(formatter)

    console = logging.StreamHandler()
    console.setLevel(logging.INFO)

    logger.addHandler(handler)

    logger.addHandler(console)
    
    return logger

def load_time_rotating_log(name=None, when='H', interval=8, backupCount= 3 * 3):

    logname = ''
    # 1 if not name, default log in default path
    if not name:
        logname = os.path.join(LOGROOTPATH, DEFAULTLOGFILEPATH, f"time_rotate")
    # 2 if name, must have subpath, or will in tempt path
    else:
        if not ('/' in name):
            logname = os.path.join(LOGROOTPATH, DEFAULTLOGFILEPATH, name + datetime.now().strftime('%Y%m%d%H'))
        else:
            logname = os.path.join(LOGROOTPATH, name + datetime.now().strftime('%Y%m%d%H'))
    if logname[-4:] != '.log':
        logname += '.log'
    # 3 makedir
    folder_path, file_name = os.path.split(logname)
    if not os.path.exists(folder_path):
        os.makedirs(os.path.join(folder_path))
    
    logger = logging.getLogger(str(datetime.now()))
    logger.handlers = []
    logger.setLevel(level=logging.INFO)
    
    handler = TimedRotatingFileHandler(filename=logname, when=when, interval=interval, backupCount=backupCount)
    handler.setLevel(logging.INFO)
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    handler.setFormatter(formatter)

    console = logging.StreamHandler()
    console.setLevel(logging.INFO)

    logger.addHandler(handler)

    logger.addHandler(console)
    return logger

def load_file_rotating_log(name=None, maxBytest=100*1024*1024, backupCount=3):
    # maxBytes= 1024* 1024 means 1MB

    logname = ''
    # 1 if not name, default log in default path
    if not name:
        logname = os.path.join(LOGROOTPATH, DEFAULTLOGFILEPATH, f"file_rotate")
    # 2 if name, must have subpath, or will in tempt path
    else:
        if not ('/' in name):
            logname = os.path.join(LOGROOTPATH, DEFAULTLOGFILEPATH, name + datetime.now().strftime('%Y%m%d%H%M%S'))
        else:
            logname = os.path.join(LOGROOTPATH, name + datetime.now().strftime('%Y%m%d%H%M%S'))
    if logname[-4:] != '.log':
        logname += '.log'
    # 3 makedir
    folder_path, file_name = os.path.split(logname)
    if not os.path.exists(folder_path):
        os.makedirs(os.path.join(folder_path))
        
    logger = logging.getLogger(str(datetime.now()))
    logger.handlers = []
    logger.setLevel(level=logging.INFO)
    
    handler = RotatingFileHandler(filename=logname, maxBytes=maxBytest, backupCount=backupCount)
    handler.setLevel(logging.INFO)
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    handler.setFormatter(formatter)

    console = logging.StreamHandler()
    console.setLevel(logging.INFO)

    logger.addHandler(handler)

    logger.addHandler(console)
    return logger
