"""SDC Agents (SMB Edition): purpose-scoped ADK agents for SDC4 data operations."""

from importlib.metadata import PackageNotFoundError, version

# Derived from the installed distribution rather than written out here, so it
# cannot drift from pyproject.toml. The sibling repo had exactly that drift.
try:
    __version__ = version("sdc-agents-smb")
except PackageNotFoundError:  # running from a source tree that was never installed
    __version__ = "0.0.0+unknown"

__all__ = ["__version__"]
