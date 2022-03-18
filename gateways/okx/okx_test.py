import requests
import datetime
import json
import hmac
import base64

apiKey = "606c2656-fbfe-4e6b-a259-7c6ecb9c6863"
secretKey = "1BE2E53229A31B8F9409496C72F5D853"
passPhrase = "vVWLhZMDBqpV2YG3"
API_URL = 'https://www.okx.com'
GET = "GET"
POST = "POST"
DELETE = "DELETE"
CONTENT_TYPE = 'Content-Type'
OK_ACCESS_KEY = 'OK-ACCESS-KEY'
OK_ACCESS_SIGN = 'OK-ACCESS-SIGN'
OK_ACCESS_TIMESTAMP = 'OK-ACCESS-TIMESTAMP'
OK_ACCESS_PASSPHRASE = 'OK-ACCESS-PASSPHRASE'
APPLICATION_JSON = 'application/json'

def account_get_balance(self, ccy=None):
        params = {}
        if ccy:
            params['ccy'] = ccy
        return self._request_with_params(GET, '/api/v5/account/balance', params)

def parse_params_to_str(params):
    url = '?'
    for key, value in params.items():
        url = url + str(key) + '=' + str(value) + '&'

    return url[0:-1]

def get_timestamp():
    now = datetime.datetime.utcnow()
    t = now.isoformat("T", "milliseconds")
    return t + "Z"

def sign(message, secret_key):
    mac = hmac.new(bytes(secret_key, encoding='utf8'), bytes(message, encoding='utf-8'), digestmod='sha256')
    d = mac.digest()
    return base64.b64encode(d)

def pre_hash(timestamp, method, request_path, body):
    return str(timestamp) + str.upper(method) + request_path + body

def get_header(api_key, sign, timestamp, passphrase):
    header = dict()
    header[CONTENT_TYPE] = APPLICATION_JSON
    header[OK_ACCESS_KEY] = api_key
    header[OK_ACCESS_SIGN] = sign
    header[OK_ACCESS_TIMESTAMP] = str(timestamp)
    header[OK_ACCESS_PASSPHRASE] = passphrase

    return header

method = "GET"
request_path = '/api/v5/account/balance'
params = {}

if method == "GET":
    request_path = request_path + parse_params_to_str(params)
# url
url = API_URL + request_path

# 获取本地时间
# format: %Y-%m-%dT%H:%M:%S.%3fZ
timestamp = get_timestamp()

# sign & header

# body 如果不是post 都是空，也就是非post 所有的东西都写到url中去
body = json.dumps(params) if method == POST else ""
sign_msg = sign(pre_hash(timestamp, method, request_path, str(body)), secretKey)
header = get_header(apiKey, sign_msg, timestamp, passPhrase)

if True:
    header['x-simulated-trading'] = '1'


# send request
response = None
if method == GET:
    response = requests.get(url, headers=header)
elif method == POST:
    response = requests.post(url, data=body, headers=header)
elif method == DELETE:
    response = requests.delete(url, headers=header)

# exception handle
if not str(response.status_code).startswith('2'):
    raise Exception(response)
try:
    res_header = response.headers
    print(response.json())
    

except ValueError:
    raise Exception(response)