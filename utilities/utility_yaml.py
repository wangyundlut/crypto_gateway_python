import yaml
import os


def load_yaml_file(file_path):
    config_file = ''
    with open(file_path) as f:
        config_file = yaml.load(f, Loader=yaml.FullLoader)
    return config_file


def load_account_file(account_config):
    with open (os.path.join("/app/account_config", account_config + ".yml")) as f:
        config_file = yaml.load(f, Loader=yaml.FullLoader)
    return config_file
