import pytest
from risk.sizer import calc_quantity


def test_basic_quantity():
    # capital 10000, risk 2% -> 200; stop_distance 1000 -> 0.2
    q = calc_quantity(10000, 0.02, entry_price=98000, sl_price=97000,
                      qty_step=0.001)
    assert q == pytest.approx(0.2, abs=1e-9)


def test_floor_to_step():
    # raw 0.2347 with step 0.01 -> 0.23
    q = calc_quantity(10000, 0.02, entry_price=100.852, sl_price=100.0,
                      qty_step=0.01)
    # risk 200 / stop 0.852 = 234.74 -> floor step 0.01 = 234.74
    assert q == pytest.approx(234.74, abs=1e-2)


def test_zero_when_stop_distance_nonpositive():
    assert calc_quantity(10000, 0.02, entry_price=100, sl_price=100,
                         qty_step=0.001) == 0.0
    assert calc_quantity(10000, 0.02, entry_price=90, sl_price=100,
                         qty_step=0.001) == 0.0
