"""pydahua — small Python helpers for Dahua devices (HTTP CGI + RPC2) + broadcast terminals (/prod-api)."""

from .client import (
    DAHUA_OUIS,
    DahuaClient,
    DahuaDevice,
    DahuaError,
    identify,
    is_dahua_mac,
)
from .config import parse_config, to_setconfig_params
from .broadcast import (
    DahuaBroadcastClient,
    DahuaBroadcastError,
    build_sip_edit_payload,
    rsa_encrypt_password,
)

__all__ = [
    "DahuaClient",
    "DahuaDevice",
    "DahuaError",
    "identify",
    "is_dahua_mac",
    "DAHUA_OUIS",
    "parse_config",
    "to_setconfig_params",
    "DahuaBroadcastClient",
    "DahuaBroadcastError",
    "build_sip_edit_payload",
    "rsa_encrypt_password",
]
