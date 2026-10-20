"""Single data-access layer. Nothing outside this package knows where the mart lives."""

from .loader import MartData, load_mart

__all__ = ["MartData", "load_mart"]
