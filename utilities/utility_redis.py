import redis
from utilities.utility_yaml import load_yaml_file, CONFIGBASEPATH


def load_redis_connection_pool(filename='utility/redis_local'):
    filepath = CONFIGBASEPATH + filename + '.yaml'
    config_file = load_yaml_file(filepath)
    host = config_file['host']
    port = config_file['port']
    password = config_file['password']
    rc = redis.ConnectionPool(host=host, port=port, password=password)   
    return rc

def load_redis_connection_in_pool(redis_pool):
    return redis.Redis(connection_pool=redis_pool)

def load_redis_connection(filename='utility/redis_local'):
    filepath = CONFIGBASEPATH + filename + '.yaml'
    config_file = load_yaml_file(filepath)
    host = config_file['host']
    port = config_file['port']
    password = config_file['password']
    rc = redis.Redis(host=host, port=port, password=password)
    return rc

