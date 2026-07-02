"""Parser/serializer for the Dahua ``configManager.cgi`` config format.

``GET /cgi-bin/configManager.cgi?action=getConfig&name=SIP`` returns flat lines::

    table.SIP[0].Enable=true
    table.SIP[0].SipServer.Address=192.0.2.10
    table.SIP[0].SipServer.Port=5060
    table.SIP[0].UserName=100

This module turns that into / from a flat ``{key: value}`` dict (keys keep the
``SIP[0].SipServer.Address`` form, i.e. without the leading ``table.``). Values
are strings; ``true``/``false`` are left as-is (Dahua expects those literals).
"""

from __future__ import annotations


def parse_config(text: str) -> dict[str, str]:
    """Parse ``getConfig`` output into a flat dict (drops the ``table.`` prefix)."""
    out: dict[str, str] = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or "=" not in line:
            continue
        key, _, val = line.partition("=")
        key = key.strip()
        if key.startswith("table."):
            key = key[len("table."):]
        out[key] = val.strip()
    return out


def to_setconfig_params(values: dict[str, str]) -> list[tuple[str, str]]:
    """Build the query params for ``action=setConfig`` from a flat dict.

    Dahua expects each item as its own query param, e.g.
    ``SIP[0].SipServer.Address=192.0.2.10``. Returns a list of (key, value)
    tuples (order preserved) suitable for ``requests``' ``params=``.
    """
    return [(k, v) for k, v in values.items()]
