import re

from mootdx._protocol.hq import ServerAdjustedTdxHqAPI
from mootdx._protocol.parser.std.get_server_adjusted_security_bars import ADJUST_MODES
from mootdx._protocol.parser.std.get_server_adjusted_security_bars import GetServerAdjustedSecurityBarsCmd
from mootdx._protocol.parser.std.get_server_adjusted_security_bars import SERVER_ADJUSTED_BAR_BATCH_SIZE
from mootdx._protocol.parser.std.get_server_adjusted_security_bars import normalize_adjust
from mootdx._protocol.parser.std.get_server_adjusted_security_bars import normalize_anchor_date


PERIOD_ALIASES = {
    '5m': (0, 1),
    '5min': (0, 1),
    '15m': (1, 1),
    '15min': (1, 1),
    '30m': (2, 1),
    '30min': (2, 1),
    '1h': (3, 1),
    '60m': (3, 1),
    '60min': (3, 1),
    'hour': (3, 1),
    'days': (4, 1),
    'week': (5, 1),
    '1w': (5, 1),
    'mon': (6, 1),
    'month': (6, 1),
    '1mo': (6, 1),
    'ex_1m': (7, 1),
    '1m': (8, 1),
    '1min': (8, 1),
    'minute': (8, 1),
    'day': (9, 1),
    'dk': (9, 1),
    '1d': (9, 1),
    'daily': (9, 1),
    '3mon': (10, 1),
    'quarter': (10, 1),
    '1q': (10, 1),
    'year': (11, 1),
    '1y': (11, 1),
}


def normalize_period(frequency):
    """将固定周期或 N 分钟/N 日/N 秒周期转换为 0x052d 的两个周期字段。"""
    if isinstance(frequency, bool):
        raise ValueError(f'K 线周期错误: {frequency!r}')

    if isinstance(frequency, int):
        period = (frequency, 1)
    elif isinstance(frequency, tuple) and len(frequency) == 2:
        if any(isinstance(value, bool) or not isinstance(value, int) for value in frequency):
            raise ValueError(f'K 线周期错误: {frequency!r}')
        period = frequency
    elif isinstance(frequency, str):
        key = frequency.strip().lower()
        if key in PERIOD_ALIASES:
            period = PERIOD_ALIASES[key]
        else:
            matched = re.fullmatch(r'(\d+)(m|min|d|s)', key)
            if not matched:
                raise ValueError(f'K 线周期错误: {frequency!r}')

            value = int(matched.group(1))
            unit = matched.group(2)
            if value <= 0 or value > 0x7FFF:
                raise ValueError('自定义 K 线周期必须在 1 到 32767 之间')

            if unit in ['m', 'min']:
                period = {
                    1: (8, 1),
                    5: (0, 1),
                    15: (1, 1),
                    30: (2, 1),
                    60: (3, 1),
                }.get(value, (8, value))
            elif unit == 'd':
                period = (9, value)
            else:
                period = (13, value)
    else:
        raise ValueError(f'K 线周期错误: {frequency!r}')

    category, period_param = (int(value) for value in period)
    if category not in list(range(12)) + [13]:
        raise ValueError(f'不支持的 K 线周期类别: {category!r}')
    if period_param <= 0 or period_param > 0x7FFF:
        raise ValueError('K 线周期参数必须在 1 到 32767 之间')
    if category not in [8, 9, 13] and period_param != 1:
        raise ValueError(f'K 线周期类别 {category} 的周期参数必须为 1')

    return category, period_param


__all__ = [
    'ADJUST_MODES',
    'GetServerAdjustedSecurityBarsCmd',
    'PERIOD_ALIASES',
    'SERVER_ADJUSTED_BAR_BATCH_SIZE',
    'ServerAdjustedTdxHqAPI',
    'normalize_adjust',
    'normalize_anchor_date',
    'normalize_period',
]
