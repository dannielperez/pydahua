"""pydahua — small Python helpers for Dahua devices (HTTP CGI + RPC2)."""

from .client import (
    DAHUA_OUIS,
    DahuaClient,
    DahuaDevice,
    DahuaError,
    identify,
    is_dahua_mac,
)
from .config import parse_config, to_setconfig_params

__all__ = [
    "DahuaClient",
    "DahuaDevice",
    "DahuaError",
    "identify",
    "is_dahua_mac",
    "DAHUA_OUIS",
    "parse_config",
    "to_setconfig_params",
]
