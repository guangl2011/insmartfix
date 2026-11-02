"""T-CAL-1: MATCH / PARTIAL / MISS / NO_PREDICTION, property-tested over the catalog (FR-7.5)."""

import pytest
from hypothesis import given
from hypothesis import strategies as st

from app.calibration.labeler import Label, UnknownActualCodeError, label
from app.seed.failure_codes import FAILURE_CODES

CATALOGS = {
    subtype: {code: group for code, group, _ in codes} for subtype, codes in FAILURE_CODES.items()
}


@st.composite
def catalog_and_codes(draw: st.DrawFn) -> tuple[dict[str, str], str, str]:
    groups = CATALOGS[draw(st.sampled_from(sorted(CATALOGS)))]
    codes = sorted(groups)
    return groups, draw(st.sampled_from(codes)), draw(st.sampled_from(codes))


@given(catalog_and_codes())
def test_T_CAL_1_label_follows_code_then_component_group(
    case: tuple[dict[str, str], str, str],
) -> None:
    groups, predicted, actual = case
    got = label(predicted, actual, groups)
    if predicted == actual:
        assert got is Label.MATCH
    elif groups[predicted] == groups[actual]:
        assert got is Label.PARTIAL
    else:
        assert got is Label.MISS
    # Agreement between two codes doesn't depend on which one was predicted.
    assert label(actual, predicted, groups) is got


@given(catalog_and_codes())
def test_T_CAL_1_no_prediction_whatever_was_found(case: tuple[dict[str, str], str, str]) -> None:
    groups, _, actual = case
    assert label(None, actual, groups) is Label.NO_PREDICTION


@given(catalog_and_codes(), st.text(min_size=1, max_size=20))
def test_T_CAL_1_unknown_predicted_code_is_a_miss(
    case: tuple[dict[str, str], str, str], stale: str
) -> None:
    groups, _, actual = case
    if stale in groups:
        return
    assert label(stale, actual, groups) is Label.MISS


@given(catalog_and_codes(), st.text(min_size=1, max_size=20))
def test_T_CAL_1_actual_code_must_be_in_the_catalog(
    case: tuple[dict[str, str], str, str], bogus: str
) -> None:
    groups, predicted, _ = case
    if bogus in groups:
        return
    with pytest.raises(UnknownActualCodeError):
        label(predicted, bogus, groups)
    with pytest.raises(UnknownActualCodeError):
        label(None, bogus, groups)


def test_T_CAL_1_fixture_examples() -> None:
    rtu = CATALOGS["RTU"]
    assert label("COMP-CONTACTOR", "COMP-CONTACTOR", rtu) is Label.MATCH
    assert label("COMP-CONTACTOR", "COMP-CAPACITOR", rtu) is Label.PARTIAL
    assert label("COMP-CONTACTOR", "REF-LEAK", rtu) is Label.MISS
    assert label(None, "REF-LEAK", rtu) is Label.NO_PREDICTION


def test_catalog_has_partial_and_miss_pairs_for_every_subtype() -> None:
    """The property test only means something if both outcomes are reachable."""
    for groups in CATALOGS.values():
        by_group: dict[str, int] = {}
        for g in groups.values():
            by_group[g] = by_group.get(g, 0) + 1
        assert len(by_group) >= 2
        assert max(by_group.values()) >= 2
