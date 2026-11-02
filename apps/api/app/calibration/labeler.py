"""Pure calibration labeler (FR-7.5).

- **NO_PREDICTION**: there was no prediction (no packet).
- **MATCH**: the contractor's code is the predicted code.
- **PARTIAL**: different code, same component group.
- **MISS**: different component group, or a predicted code the catalog no longer knows.

`groups` is the asset subtype's catalog (`code -> component_group`, `catalog.component_groups`).
The actual code must be in it: completion validates it first (FR-7.1), so anything else is a bug.
"""

from collections.abc import Mapping
from enum import StrEnum


class Label(StrEnum):
    MATCH = "MATCH"
    PARTIAL = "PARTIAL"
    MISS = "MISS"
    NO_PREDICTION = "NO_PREDICTION"


class UnknownActualCodeError(ValueError):
    """The submitted code isn't in the subtype's catalog."""


def label(predicted: str | None, actual: str, groups: Mapping[str, str]) -> Label:
    actual_group = groups.get(actual)
    if actual_group is None:
        raise UnknownActualCodeError(actual)
    if predicted is None:
        return Label.NO_PREDICTION
    if predicted == actual:
        return Label.MATCH
    if groups.get(predicted) == actual_group:
        return Label.PARTIAL
    return Label.MISS
