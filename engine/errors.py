"""Custom errors. Bad input must raise one of these — never crash with a bare traceback."""


class DispatchError(Exception):
    """Base class for all engine errors."""


class ValidationError(DispatchError):
    """Invalid network or train definition."""


class UnknownSegmentError(ValidationError):
    """A train path references a segment id that does not exist."""


class DisconnectedPathError(ValidationError):
    """A train path's segments do not form a connected route from origin to destination."""


class BaselineConflictError(DispatchError):
    """The baseline schedule contains segment-occupancy conflicts."""

    def __init__(self, conflicts):
        self.conflicts = conflicts
        lines = ", ".join(
            f"{c.train_a}/{c.train_b} on {c.segment_id} during [{c.start},{c.end}]"
            for c in conflicts
        )
        super().__init__(f"baseline schedule has {len(conflicts)} conflict(s): {lines}")
