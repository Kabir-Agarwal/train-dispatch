"""Gate: validation unit. Bad input rejected with a clear error, never a crash."""

import pytest

from engine.errors import DisconnectedPathError, UnknownSegmentError, ValidationError
from engine.model import Network, Segment, Train
from engine.scheduler import validate_path


def network():
    return Network(
        stations=["S1", "S2", "S3", "S4"],
        segments=[
            Segment("SEG-12", ("S1", "S2"), 10),
            Segment("SEG-23", ("S2", "S3"), 8),
            Segment("SEG-34", ("S3", "S4"), 12),
        ],
    )


def test_valid_path_passes():
    train = Train("T1", "S1", "S4", ("SEG-12", "SEG-23", "SEG-34"), 0)
    validate_path(network(), train)  # must not raise


def test_nonexistent_segment_rejected_with_clear_error():
    train = Train("TX", "S1", "S4", ("SEG-12", "SEG-99", "SEG-34"), 0)
    with pytest.raises(UnknownSegmentError, match="SEG-99"):
        validate_path(network(), train)


def test_disconnected_path_rejected_with_clear_error():
    # SEG-12 ends at S2; SEG-34 connects S3-S4 — gap at S2.
    train = Train("TX", "S1", "S4", ("SEG-12", "SEG-34"), 0)
    with pytest.raises(DisconnectedPathError, match="breaks at 'S2'"):
        validate_path(network(), train)


def test_path_not_reaching_destination_rejected():
    # Path is connected but stops at S3, not the declared destination S4.
    train = Train("TX", "S1", "S4", ("SEG-12", "SEG-23"), 0)
    with pytest.raises(DisconnectedPathError, match="ends at 'S3'"):
        validate_path(network(), train)


def test_path_not_starting_at_origin_rejected():
    # First segment SEG-23 does not touch the origin S1.
    train = Train("TX", "S1", "S3", ("SEG-23",), 0)
    with pytest.raises(DisconnectedPathError, match="breaks at 'S1'"):
        validate_path(network(), train)


def test_empty_path_rejected():
    train = Train("TX", "S1", "S4", (), 0)
    with pytest.raises(ValidationError, match="empty path"):
        validate_path(network(), train)


def test_unknown_origin_rejected():
    train = Train("TX", "S9", "S4", ("SEG-12",), 0)
    with pytest.raises(ValidationError, match="S9"):
        validate_path(network(), train)
