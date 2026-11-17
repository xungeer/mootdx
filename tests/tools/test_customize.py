import pytest

from mootdx.tools.customize import Customize


@pytest.fixture()
def custom(tmp_path):
    (tmp_path / 'T0002' / 'blocknew').mkdir(parents=True)
    client = Customize(tdxdir=str(tmp_path))
    client.create(name='龙虎榜', symbol=['600036', '600016'], blk_file='lhb')
    client.create(name='优质股', symbol=['600036', '600016'], blk_file='yzg')
    return client


def test_block_create(custom):
    assert custom.create(name='测试板块', symbol=['600036', '600016'], blk_file='test')
    assert custom.create(name=None, symbol=['600036', '600016'])
    assert custom.create(name='优质股1', symbol=['600036', '600016'])
    assert custom.create(name='空板块', symbol=[], blk_file='empty')
    for name, symbols in [('优质股', ['600036']),
                          ('优质股3', None), ('', None), (None, None)]:
        with pytest.raises(Exception):
            custom.create(name=name, symbol=symbols)


def test_block_update(custom):
    assert custom.update(name='龙虎榜', symbol=['600036'])


def test_block_search(custom):
    assert not custom.search(group=True).empty
    assert not custom.search().empty
    assert custom.search(name='龙虎榜')
    assert custom.search(name='龙虎榜', group=True)


def test_block_remove(custom):
    assert custom.remove(name='优质股')
    assert custom.search(name='优质股') is None
