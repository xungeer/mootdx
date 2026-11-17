from mootdx._protocol.base_socket_client import BaseSocketClient
from mootdx._protocol.base_socket_client import CONNECT_TIMEOUT
from mootdx._protocol.constants import BJ_A_STOCK_PREFIXES
from mootdx._protocol.constants import SECURITY_EXCHANGE
from mootdx._protocol.constants import SH_FUND_PREFIXES
from mootdx._protocol.constants import SZ_FUND_PREFIXES
from mootdx._protocol.reader import TdxDailyBarReader

from mootdx.logger import logger


class MooTdxDailyBarReader(TdxDailyBarReader):
    """感谢 bopomofo 的鼎力支持"""

    SECURITY_TYPE = [
        'SH_A_STOCK',
        'SH_B_STOCK',
        'SH_STAR_STOCK',
        'SH_INDEX',
        'SH_FUND',
        'SH_BOND',
        'SZ_A_STOCK',
        'SZ_B_STOCK',
        'SZ_INDEX',
        'SZ_FUND',
        'SZ_BOND',
        'BJ_A_STOCK',
        'BJ_INDEX',
        'BJ_FUND',
        'BJ_BOND',
    ]

    SECURITY_COEFFICIENT = {
        'SH_A_STOCK': [0.01, 0.01],
        'SH_B_STOCK': [0.001, 0.01],
        'SH_STAR_STOCK': [0.01, 0.01],
        'SH_INDEX': [0.01, 1.0],
        'SH_FUND': [0.001, 1.0],
        'SH_BOND': [0.001, 1.0],
        'SZ_A_STOCK': [0.01, 0.01],
        'SZ_B_STOCK': [0.01, 0.01],
        'SZ_INDEX': [0.01, 1.0],
        'SZ_FUND': [0.001, 0.01],
        'SZ_BOND': [0.001, 0.01],
        'BJ_A_STOCK': [0.01, 0.01],
        'BJ_INDEX': [0.01, 1.0],
        'BJ_FUND': [0.001, 1.0],
        'BJ_BOND': [0.001, 1.0],
    }

    def get_security_type(self, fname):

        exchange = str(fname[-12:-10]).lower()
        code_head = fname[-10:-8]

        if exchange == SECURITY_EXCHANGE[0]:
            if code_head in ['00', '30']:
                return 'SZ_A_STOCK'

            if code_head in ['20']:
                return 'SZ_B_STOCK'

            if code_head in ['39']:
                return 'SZ_INDEX'

            if code_head in SZ_FUND_PREFIXES:
                return 'SZ_FUND'

            if code_head in ['10', '11', '12', '13', '14']:
                return 'SZ_BOND'

            return 'SZ_OTHER'

        if exchange == SECURITY_EXCHANGE[1]:
            if code_head in ['60']:
                return 'SH_A_STOCK'

            if code_head in ['90']:
                return 'SH_B_STOCK'

            if code_head in ['68']:
                return 'SH_STAR_STOCK'

            if code_head in ['00', '88', '99']:
                return 'SH_INDEX'

            if code_head in SH_FUND_PREFIXES:
                return 'SH_FUND'

            # if code_head in ['01', '10', '11', '12', '13', '14']:
            if code_head in ['01', '02', '10', '11', '12', '13', '14', '15', '16', '17', '18', '19', '20']:
                return 'SH_BOND'

            return 'SH_OTHER'
        
        if exchange == SECURITY_EXCHANGE[2]:
            if code_head in BJ_A_STOCK_PREFIXES:
                return 'BJ_A_STOCK'
            
            if code_head in ['89']:
                return 'BJ_INDEX'

            return 'BJ_OTHER'

        logger.error('Unknown security exchange !\n')
        raise NotImplementedError


class MooBaseSocketClient(BaseSocketClient):
    def __init__(self):
        super().__init__()
        self.client = None

    def connect(self, ip='101.227.73.20', port=7709, time_out=CONNECT_TIMEOUT, bindport=None, bindip='0.0.0.0'):
        """

        :param ip:  服务器ip 地址
        :param port:  服务器端口
        :param time_out: 连接超时时间
        :param bindport: 绑定的本地端口
        :param bindip: 绑定的本地ip
        :return: 是否连接成功 True/False
        """

        return super().connect(
            ip=ip, port=port, time_out=time_out,
            bind_port=bindport, bind_ip=bindip,
        )

    def disconnect(self):
        return super().disconnect()

    def setup(self):
        pass
