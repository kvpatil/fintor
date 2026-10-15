"""Market-series maths, checked against hand-computed values.

These are pure functions, so every expectation here is arithmetic someone can
verify on paper - not a snapshot of whatever the code happened to produce.
"""

from __future__ import annotations

import pytest

from src.core.market_calc import (
    InsufficientData,
    correlation,
    correlation_matrix,
    max_drawdown,
    moving_average,
    period_return,
    rebase,
    returns,
    sharpe,
    volatility,
)


# --- moving average -----------------------------------------------------


def test_moving_average_matches_hand_computed():
    series = [10, 20, 30, 40, 50]
    assert moving_average(series, 3) == [None, None, 20.0, 30.0, 40.0]


def test_moving_average_leaves_the_warmup_empty():
    """Back-filling would draw a 20-day average over 5 days of data."""
    out = moving_average([1, 2, 3, 4], 3)
    assert out[:2] == [None, None], "warm-up must not be invented"
    assert out[2] == 2.0


def test_moving_average_window_of_one_is_the_series():
    assert moving_average([3, 1, 4], 1) == [3.0, 1.0, 4.0]


# --- rebase -------------------------------------------------------------


def test_rebase_starts_at_one_hundred_and_keeps_shape():
    out = rebase([50, 75, 25])
    assert out[0] == 100.0
    assert out[1] == 150.0, "a 50% rise is 150 on the index"
    assert out[2] == 50.0


def test_rebase_is_what_replaces_a_second_y_axis():
    """Two series of wildly different magnitude become comparable on one axis."""
    big, small = rebase([1000, 1100]), rebase([10, 11])
    assert big == small == [100.0, 110.0]


def test_rebase_rejects_a_zero_start():
    with pytest.raises(ValueError, match="zero"):
        rebase([0, 5, 10])


# --- return and drawdown ------------------------------------------------


def test_period_return_is_first_to_last():
    assert period_return([100, 50, 120]) == 20.0


def test_max_drawdown_on_known_peak_trough():
    """120 -> 78 is a 35% decline, and recovery afterwards must not erase it."""
    assert max_drawdown([100, 120, 90, 78, 110]) == 35.0


def test_max_drawdown_of_a_rising_series_is_zero():
    assert max_drawdown([1, 2, 3, 4]) == 0.0


# --- volatility and sharpe ---------------------------------------------


def test_volatility_of_a_flat_series_is_zero():
    assert volatility([100] * 12) == 0.0


def test_sharpe_matches_worked_example():
    """8% return, 10% volatility, 3% risk-free -> 0.5."""
    assert sharpe(8.0, 10.0, 3.0) == 0.5


def test_sharpe_is_undefined_at_zero_volatility():
    with pytest.raises(ValueError, match="undefined"):
        sharpe(8.0, 0.0, 3.0)


# --- correlation --------------------------------------------------------


def test_correlation_of_identical_series_is_one():
    a = [0.01, -0.02, 0.03, 0.00, 0.015]
    assert correlation(a, a) == 1.0


def test_correlation_of_an_inverted_series_is_minus_one():
    a = [0.01, -0.02, 0.03, 0.00, 0.015]
    assert correlation(a, [-x for x in a]) == -1.0


def test_correlation_matrix_has_a_unit_diagonal():
    series = {
        "AAA": [100, 102, 101, 104, 103, 106],
        "BBB": [50, 51, 50.5, 52, 51.5, 53],
        "CCC": [20, 19, 19.5, 18, 18.5, 17],
    }
    symbols, matrix = correlation_matrix(series)
    assert symbols == ["AAA", "BBB", "CCC"]
    assert all(matrix[i][i] == 1.0 for i in range(3))
    assert matrix[0][1] == matrix[1][0], "matrix must be symmetric"


def test_correlation_matrix_drops_flat_and_short_series():
    """An absent row is honest; a fabricated 0.0 correlation is not."""
    series = {
        "GOOD": [100, 102, 101, 104, 103, 106],
        "ALSO": [10, 11, 10.5, 12, 11.5, 13],
        "FLAT": [7, 7, 7, 7, 7, 7],
    }
    symbols, _ = correlation_matrix(series)
    assert "FLAT" not in symbols
    assert symbols == ["ALSO", "GOOD"]


# --- refusing bad input -------------------------------------------------


@pytest.mark.parametrize("fn,args", [
    (period_return, ([100],)),
    (max_drawdown, ([100],)),
    (returns, ([100],)),
    (volatility, ([100, 101],)),
    (correlation, ([1.0, 2.0], [1.0, 2.0])),
])
def test_series_functions_refuse_too_few_points(fn, args):
    """A statistic computed from 2 points will still be narrated to a user as
    though it meant something. Raising is the honest outcome."""
    with pytest.raises(InsufficientData):
        fn(*args)
