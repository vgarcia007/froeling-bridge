"""Failures distinguish invalid input, broken exchanges and uncertain writes."""


class ValidationError(ValueError):
    """Input is invalid; no write operation should be initiated."""


class ProtocolError(Exception):
    """The current exchange cannot safely continue."""


class FrameError(ProtocolError):
    pass


class InvalidStart(FrameError):
    pass


class InvalidEscape(FrameError):
    pass


class InvalidLength(FrameError):
    pass


class ChecksumError(FrameError):
    pass


class TruncatedFrame(FrameError):
    pass


class MalformedPayload(ProtocolError):
    pass


class UnexpectedReply(ProtocolError):
    pass


class UnexpectedData(ProtocolError):
    pass


class RequestTimeout(ProtocolError):
    pass


class TransportError(ProtocolError):
    pass


class SessionBroken(ProtocolError):
    """A new, clean transport/session is required; bytes must not be discarded blindly."""


class ListLimitExceeded(ProtocolError):
    pass


class WriteOutcomeUnknown(ProtocolError):
    """A write may have reached the controller, but confirmation is incomplete."""

    def __init__(self, operation, address, stage):
        self.operation = operation
        self.address = address
        self.stage = stage
        super().__init__(f"{operation} at 0x{address:04X}: outcome unknown during {stage}")


class WriteVerificationError(ProtocolError):
    """A valid readback differs from the intended change."""

    def __init__(self, operation, address, actual):
        self.operation = operation
        self.address = address
        self.actual = actual
        super().__init__(f"{operation} at 0x{address:04X}: readback differs from target")
