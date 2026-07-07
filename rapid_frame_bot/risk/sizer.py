from __future__ import annotations
import math


def calc_quantity(
    capital: float,
    risk_rate: float,
    entry_price: float,
    sl_price: float,
    qty_step: float,
) -> float:
    stop_distance = entry_price - sl_price
    if stop_distance <= 0:
        return 0.0
    risk_amount = capital * risk_rate
    raw_qty = risk_amount / stop_distance
    steps = math.floor(raw_qty / qty_step)
    return round(steps * qty_step, 10)
