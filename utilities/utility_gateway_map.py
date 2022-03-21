
from gateways.okx.gateway_okx import okxGateway
from gateways.okx.okx_rest.consts import EXCHANGE_NAME as ok_name


exchange_gateway_map = {
    ok_name: okxGateway,

}