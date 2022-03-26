
from crypto_rest_python.okx.sync.rest_v5 import okx_api_v5
from crypto_gateway_python.utilities.utility_yaml import load_yaml_file

account_test_path = '/app/config/okx/simulated20210922.yaml'
# account_test_path = '/app/config/okx/okextest20210419.yaml'
inst_id_test = 'btc-usdt'

config = load_yaml_file(account_test_path)
apiKey = config['apiKey']
secretKey = config['secretKey']
passPhrase = config['passPhrase']
isTest = config['isTest']

rest = okx_api_v5(apiKey, secretKey, passPhrase, test=isTest)



def get_all_alive_orders(inst_id):
    # get all alive orders
    orders_alive = rest.trade_get_orders_pending(instId=inst_id.upper())
    print(orders_alive)
    return orders_alive

def cancel_all_alive_orders(inst_id):
    # cancel all alive orders
    orders_alive = rest.trade_get_orders_pending(instId=inst_id.upper())
    orderIds = []
    for order in orders_alive["data"]:
        orderIds.append(order["ordId"])

    # cancel alive orders max 100
    for ordId in orderIds:
        orders_cancel = rest.trade_post_cancel_order(instId=inst_id.upper(), ordId=ordId)
        print(orders_cancel)

def get_set_account_config():
    # get account config
    print(rest.account_get_config())

def account_transfer():
    pass

def close_position():
    """
    twap close position
    """
    pass


if __name__ == "__main__":
    inst_id = "btc-usdt"
    # get_set_account_config()
    # get_all_alive_orders(inst_id)
    # cancel_all_alive_orders(inst_id)
    








