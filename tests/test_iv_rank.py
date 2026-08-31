"""Covers the two IV-history bugs that pinned iv_rank at its ceiling:
logging the current sample before ranking against it, and mislabelling cycles as days."""

import csv

import pytest

from src.signals.iv_rank import iv_rank_from_log, log_iv_snapshot


@pytest.fixture
def history(tmp_path):
    def _write(values):
        path = tmp_path / "iv_history_TEST.csv"
        with open(path, "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["timestamp", "underlying", "atm_iv"])
            for i, v in enumerate(values):
                w.writerow([f"2026-08-30T00:{i:02d}:00", "TEST", v])
        return path
    return _write


def test_new_high_is_not_forced_to_100(history):
    """The original bug: log first, rank after, so any new high was exactly 100.0."""
    path = history([0.10, 0.11, 0.12, 0.13, 0.14])
    rank, _, n = iv_rank_from_log("TEST", 0.20, log_path=path)
    assert n == 5
    assert rank == 100.0  # clamped, because 0.20 is above the prior window...
    # ...but the prior window is untouched: the reading is not in its own denominator.
    with open(path) as f:
        assert len(list(csv.DictReader(f))) == 5


def test_midrange_value_ranks_proportionally(history):
    path = history([0.10, 0.20])  # too thin
    assert iv_rank_from_log("TEST", 0.15, log_path=path) == (None, None, 2)

    path = history([0.10, 0.12, 0.14, 0.16, 0.20])
    rank, pct, n = iv_rank_from_log("TEST", 0.15, log_path=path)
    assert rank == 50.0          # (0.15-0.10)/(0.20-0.10)
    assert pct == 60.0           # 3 of 5 prior samples below
    assert n == 5


def test_new_low_clamps_to_zero_not_negative(history):
    path = history([0.10, 0.11, 0.12, 0.13, 0.14])
    rank, pct, _ = iv_rank_from_log("TEST", 0.05, log_path=path)
    assert rank == 0.0
    assert pct == 0.0


def test_flat_history_returns_neutral(history):
    path = history([0.10] * 5)
    rank, _, _ = iv_rank_from_log("TEST", 0.10, log_path=path)
    assert rank == 50.0


def test_too_few_samples_returns_none(history):
    path = history([0.10, 0.11, 0.12, 0.13])
    assert iv_rank_from_log("TEST", 0.12, log_path=path) == (None, None, 4)


def test_missing_log_returns_zero_samples(tmp_path):
    assert iv_rank_from_log("TEST", 0.12, log_path=tmp_path / "nope.csv") == (None, None, 0)


def test_rank_is_stable_across_repeated_reads(history):
    """Ranking must be a pure read. Calling it twice cannot move the answer - it did before,
    because each call appended the current sample and widened the window."""
    path = history([0.10, 0.12, 0.14, 0.16, 0.20])
    first = iv_rank_from_log("TEST", 0.30, log_path=path)
    second = iv_rank_from_log("TEST", 0.30, log_path=path)
    assert first == second


def test_log_snapshot_appends_one_row(tmp_path):
    path = tmp_path / "iv_history_TEST.csv"
    log_iv_snapshot("TEST", 0.11, log_path=path)
    log_iv_snapshot("TEST", 0.12, log_path=path)
    with open(path) as f:
        rows = list(csv.DictReader(f))
    assert [r["atm_iv"] for r in rows] == ["0.11", "0.12"]


# --- IV-window trust -------------------------------------------------------------------
# The window that pinned iv_rank to 100 for four days held 14 samples, every one stamped
# 2026-08-28. Sample depth alone would have passed it; the day spread is what catches it.

def test_single_day_window_is_not_trusted_however_many_samples():
    from src.signals.iv_rank import iv_rank_is_trusted
    assert not iv_rank_is_trusted(samples=200, days=1)


def test_thin_window_is_not_trusted_however_many_days():
    from src.signals.iv_rank import iv_rank_is_trusted
    assert not iv_rank_is_trusted(samples=6, days=4)


def test_deep_multi_day_window_is_trusted():
    from src.signals.iv_rank import iv_rank_is_trusted
    assert iv_rank_is_trusted(samples=30, days=2)


def test_history_depth_counts_distinct_days(tmp_path):
    from src.signals.iv_rank import history_depth
    p = tmp_path / "iv_history_TEST.csv"
    p.write_text(
        "timestamp,underlying,atm_iv\n"
        "2026-08-28T16:00:00,TEST,0.08\n"
        "2026-08-28T16:15:00,TEST,0.09\n"
        "2026-08-29T16:00:00,TEST,0.07\n"
    )
    assert history_depth("TEST", log_path=p) == (3, 2)


def test_untrusted_iv_withdraws_the_condor_but_keeps_direction():
    """An untrusted rank must not route everything to cash — that stops the agent trading.
    It demotes the IV branch only; the classifier-driven direction branch still stands."""
    from src.decision_schema import rulebook_strategy
    assert rulebook_strategy(100.0, 0.50, iv_rank_trusted=False)[0] == "cash"
    assert rulebook_strategy(100.0, 0.50, iv_rank_trusted=True)[0] == "iron_condor"
    assert rulebook_strategy(100.0, 0.4311, iv_rank_trusted=False)[0] == "bear_put_spread"
    assert rulebook_strategy(100.0, 0.60, iv_rank_trusted=False)[0] == "bull_call_spread"


def test_absent_iv_rank_still_allows_a_directional_trade():
    """A newly added underlying has no IV history precisely because it is new. Treating that
    absence as a reason to refuse every trade kept IWM and AAPL at cash on their first day."""
    from src.decision_schema import rulebook_strategy

    assert rulebook_strategy(None, 0.4160)[0] == "bear_put_spread"
    assert rulebook_strategy(None, 0.60)[0] == "bull_call_spread"


def test_absent_iv_rank_still_withdraws_the_condor():
    """No read on whether premium is rich means no basis for selling it."""
    from src.decision_schema import rulebook_strategy

    assert rulebook_strategy(None, 0.50)[0] == "cash"


def test_absent_classifier_is_still_a_full_stop():
    from src.decision_schema import rulebook_strategy

    assert rulebook_strategy(100.0, None)[0] == "cash"
