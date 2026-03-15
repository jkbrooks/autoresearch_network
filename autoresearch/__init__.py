"""AutoResearch Network protocol package."""

from __future__ import annotations

__all__ = ["__version__", "__spec_version__"]

__version__ = "0.1.0"
_version_parts = __version__.split(".")
__spec_version__ = (
    (1000 * int(_version_parts[0]))
    + (10 * int(_version_parts[1]))
    + int(_version_parts[2])
)
