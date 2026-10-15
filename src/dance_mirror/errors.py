"""Domain exceptions used across application boundaries."""


class DanceMirrorError(Exception):
    """Base exception for expected application failures."""


class ConfigurationError(DanceMirrorError):
    """Raised when application configuration is invalid."""


class DependencyUnavailableError(DanceMirrorError):
    """Raised when an optional runtime dependency is not installed."""


class VideoSourceError(DanceMirrorError):
    """Raised when a video source cannot be opened or read."""


class PoseEstimationError(DanceMirrorError):
    """Raised when pose estimation fails for a complete source."""


class MotionFormatError(DanceMirrorError):
    """Raised when a motion package has an invalid format."""


class CloudServiceError(DanceMirrorError):
    """Raised when an external model service fails."""
