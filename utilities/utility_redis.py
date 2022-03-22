import redis
import os
from utilities.utility_yaml import load_yaml_file


def load_redis_connection_pool(filename='redis_local'):
    filepath = os.path.join("/app/utility_config", filename + '.yml')
    config_file = load_yaml_file(filepath)
    host = config_file['host']
    port = config_file['port']
    if "password" in config_file:
        password = config_file['password']
        rc = redis.ConnectionPool(host=host, port=port, password=password,decode_responses=True)   
    else:
        rc = redis.ConnectionPool(host=host, port=port, decode_responses=True)
    return rc

def load_redis_connection_in_pool(redis_pool):
    return redis.Redis(connection_pool=redis_pool)

def load_redis_connection(filename='redis_local'):
    filepath = os.path.join("/app/utility_config", filename + '.yml')
    config_file = load_yaml_file(filepath)
    host = config_file['host']
    port = config_file['port']
    if "password" in config_file:
        password = config_file['password']
        rc = redis.Redis(host=host, port=port, password=password, decode_responses=True)   
    else:
        rc = redis.Redis(host=host, port=port, decode_responses=True)
    return rc

