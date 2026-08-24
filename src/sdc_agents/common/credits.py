"""
Credits display for the CLI.

SDCStudio denominates the wallet in USD but quotes users credits at 1,000 per
dollar. Showing dollars here made the CLI contradict every other surface: the
same wallet reads as "$20.00" in `sdc-agents` and "20,000 credits" in
SDCStudio.

Prefer a ``*_credits`` field from the server when one is present; convert only
when talking to a server that predates them.
"""

CREDITS_PER_USD = 1000


def to_credits(usd) -> int:
    """Convert a USD amount to whole credits. Credits are never fractional."""
    if usd in (None, ""):
        return 0
    return int(round(float(usd) * CREDITS_PER_USD))


def fmt_credits(usd) -> str:
    """Whole credits with thousands separators, for display."""
    return f"{to_credits(usd):,}"


def fmt_from(summary: dict, credits_key: str, usd_key: str) -> str:
    """
    Format a money field, preferring the server's credits value.

    Falls back to converting the USD field so this keeps working against an
    older SDCStudio.
    """
    if summary.get(credits_key) is not None:
        return f"{int(summary[credits_key]):,}"
    return fmt_credits(summary.get(usd_key, 0))
