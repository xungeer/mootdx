import pytest

from mootdx.reader import Reader


@pytest.fixture()
def reader(tmp_path):
    (tmp_path / 'T0002' / 'blocknew').mkdir(parents=True)
    return Reader.factory(market='std', tdxdir=str(tmp_path))


def test_blocknew_01(reader):
    result = reader.block_new(name='最优盈利板块', symbol=['600001', '600002', '600003', '600004'])
    assert result


def test_blocknew_02(reader):
    assert reader.block_new(name='最优盈利板块', symbol=['600001'])
    assert reader.block_new(name='最优盈利板块')
    assert not reader.block_new().empty
