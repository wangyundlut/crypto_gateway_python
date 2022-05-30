import yaml
import os
from .utility_common_path import COMMON_PATH
account_path = os.path.join(COMMON_PATH, "account_config")


def load_yaml_file(file_path):
    config_file = ''
    with open(file_path) as f:
        config_file = yaml.load(f, Loader=yaml.FullLoader)
    return config_file


def load_account_file(account_config):
    with open (os.path.join(account_path, account_config + ".yaml")) as f:
        config_file = yaml.load(f, Loader=yaml.FullLoader)
    return config_file
