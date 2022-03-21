import yaml

CONFIGBASEPATH = '/app/config/'

def load_yaml_file(file_path):
    config_file = ''
    with open(file_path) as f:
        config_file = yaml.load(f, Loader=yaml.FullLoader)
    return config_file



