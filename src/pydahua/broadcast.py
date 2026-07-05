"""Client for the Dahua/generic **网络广播终端** ("network broadcast terminal") IP speaker.

These broadcast/paging speakers (lighttpd + a Vue/Element-UI SPA whose ``app.js`` is
JSFuck-obfuscated) do **not** speak the standard Dahua CGI (``configManager.cgi`` —
see :mod:`pydahua.client`). Instead they expose a JSON REST API under ``/prod-api``:

* ``GET  /prod-api/key/info``   → ``{"rsaPublicKey": "<base64 DER SPKI>"}``
* ``POST /prod-api/uer/login``  (note the vendor's "uer" typo) body
  ``{"username":"admin","password":"<RSA-PKCS1v15(pw) base64>"}`` → ``{"data":{"token":...}}``
* all other calls send the token as header ``x-token: <token>``
* ``GET  /prod-api/device/info`` → flat config incl. ``sip``, ``sipAddress``,
  ``sipUsername`` (= the extension), ``sipPassword``, ``sipPassword2``
* ``POST /prod-api/device/edit`` with ``{sip,id,ip,sipAddress,sipUsername,sipPassword,
  sipPassword2}`` — set the SIP registrar. The ``sipPassword*`` fields are RSA blobs;
  **echo them back verbatim from device/info** (no decrypt/re-encrypt needed).

Typical use — repoint a public/SBC-registered speaker onto the WG tunnel::

    c = DahuaBroadcastClient("10.40.31.4", password="...")
    c.login()
    print(c.get_sip())                 # {'sipAddress': '52.54.18.219', 'sipUsername': '1802'...}
    c.set_sip_server("10.254.250.11")   # -> re-registers to the tunnel
"""
from __future__ import annotations

import base64
from typing import Any

import requests
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives.serialization import load_der_public_key

from .client import DahuaError

PROD_API = "/prod-api"
# device/info keys that make up the SIP-registrar config on device/edit.
_SIP_EDIT_KEYS = ("sip", "id", "ip", "sipAddress", "sipUsername", "sipPassword", "sipPassword2")


class DahuaBroadcastError(DahuaError):
    """Raised on a broadcast-terminal /prod-api failure."""


def rsa_encrypt_password(rsa_public_key_b64: str, password: str) -> str:
    """RSA-PKCS1v15-encrypt *password* with the base64 DER public key from key/info.

    Returns the base64 ciphertext the login endpoint expects. Pure function.
    """
    key = load_der_public_key(base64.b64decode(rsa_public_key_b64))
    ct = key.encrypt(password.encode(), padding.PKCS1v15())  # type: ignore[call-arg]
    return base64.b64encode(ct).decode("ascii")


def build_sip_edit_payload(device_info: dict[str, Any], sip_address: str) -> dict[str, str]:
    """Build the ``/prod-api/device/edit`` body to point SIP at *sip_address*.

    Pure function: copies the SIP-registrar keys from a ``device/info`` ``data`` dict
    (reusing the encrypted ``sipPassword``/``sipPassword2`` verbatim) and overrides
    ``sipAddress``. ``sip`` defaults to ``"on"`` so registration is enabled.
    """
    out = {k: str(device_info.get(k, "")) for k in _SIP_EDIT_KEYS}
    out["sip"] = device_info.get("sip") or "on"
    out["sipAddress"] = sip_address
    return out


class DahuaBroadcastClient:
    """Login + SIP-registrar read/write for a 网络广播终端 broadcast speaker."""

    def __init__(self, host: str, username: str = "admin", password: str = "",
                 *, timeout: float = 8.0, use_ssl: bool = False) -> None:
        self.host = host
        self._user = username
        self._password = password
        self._timeout = timeout
        self._base = f"{'https' if use_ssl else 'http'}://{host}"
        self._session = requests.Session()
        self._session.verify = False
        self._token: str | None = None

    @property
    def token(self) -> str | None:
        return self._token

    def _url(self, path: str) -> str:
        return f"{self._base}{PROD_API}{path}"

    def login(self) -> str:
        """Authenticate; store + return the session token. Raises on failure."""
        r = self._session.get(self._url("/key/info"), timeout=self._timeout)
        r.raise_for_status()
        pub = (r.json() or {}).get("rsaPublicKey")
        if not pub:
            raise DahuaBroadcastError(f"{self.host}: no rsaPublicKey from key/info")
        enc = rsa_encrypt_password(pub, self._password)
        r = self._session.post(self._url("/uer/login"), timeout=self._timeout,
                               json={"username": self._user, "password": enc})
        body = r.json() if r.content else {}
        tok = (body.get("data") or {}).get("token")
        if r.status_code != 200 or not tok:
            msg = body.get("message", r.status_code)
            raise DahuaBroadcastError(f"{self.host}: login failed ({msg})")
        self._token = tok
        self._session.headers["x-token"] = tok
        return tok

    def _require_token(self) -> None:
        if not self._token:
            raise DahuaBroadcastError(f"{self.host}: not logged in — call login() first")

    def get_device_info(self) -> dict[str, Any]:
        """Full ``/prod-api/device/info`` ``data`` object."""
        self._require_token()
        r = self._session.get(self._url("/device/info"), timeout=self._timeout)
        r.raise_for_status()
        return (r.json() or {}).get("data", {}) or {}

    def get_sip(self) -> dict[str, str]:
        """SIP-registrar view: sip, sipAddress, sipUsername (=ext), ports."""
        d = self.get_device_info()
        return {k: d.get(k) for k in ("sip", "sipAddress", "sipUsername", "serverIp", "serverPort")
                if k in d}

    def set_sip_server(self, sip_address: str) -> dict[str, Any]:
        """Point SIP registration at *sip_address* (e.g. the WG tunnel PBX). Verifies.

        No-op-safe: reads current config, rewrites only ``sipAddress``, POSTs
        ``device/edit`` (reusing the encrypted password fields), and re-reads to confirm.
        """
        self._require_token()
        info = self.get_device_info()
        if info.get("sipAddress") == sip_address:
            return {"changed": False, "sipAddress": sip_address}
        payload = build_sip_edit_payload(info, sip_address)
        r = self._session.post(self._url("/device/edit"), json=payload, timeout=self._timeout)
        body = r.json() if r.content else {}
        if r.status_code != 200 or body.get("code") not in (200, "200"):
            msg = body.get("message", r.status_code)
            raise DahuaBroadcastError(f"{self.host}: device/edit failed ({msg})")
        now = self.get_device_info().get("sipAddress")
        if now != sip_address:
            raise DahuaBroadcastError(f"{self.host}: sipAddress did not stick (={now})")
        return {"changed": True, "sipAddress": now, "ext": info.get("sipUsername")}

    def close(self) -> None:
        self._session.close()

    def __enter__(self) -> DahuaBroadcastClient:
        self.login()
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()
