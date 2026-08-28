"""HTTP client for Dahua devices (IP speakers, intercoms/VTO, cameras).

Dahua exposes two control surfaces; both use HTTP Digest auth:

  * **CGI API** (the workhorse) — ``/cgi-bin/*.cgi``:
      - ``magicBox.cgi?action=getDeviceType|getSystemInfo|getMachineName|reboot``
      - ``configManager.cgi?action=getConfig&name=<Table>`` / ``action=setConfig&<key>=<val>``
  * **RPC2** (JSON-RPC used by the web UI) — ``/RPC2_Login`` then ``/RPC2``;
      login is a two-step MD5 challenge (see :meth:`DahuaClient.rpc_login`).

IP speakers (e.g. DH-VCS-SH30) have a bare-bones API: SIP registration lives in
the ``SIP`` config table; audio/paging is a raw stream endpoint. This wrapper
covers device info + config get/set (incl. SIP) + reboot; ONVIF (used to attach
speakers to an NVR) is intentionally out of scope here.

Intentionally generic — no site inventory or credentials live in this package.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass

import requests
from requests.auth import HTTPDigestAuth

from .config import parse_config, to_setconfig_params

# Common Dahua IEEE OUIs (helpful for classifying a device by MAC). Dahua also
# ships hardware under Realtek-registered OUIs on some speaker/SoC lines.
DAHUA_OUIS = {
    "3c:ef:8c", "bc:32:5f", "e0:50:8b", "9c:14:63", "08:ed:ed",
    "38:af:29", "14:a7:8b", "24:52:6a", "a0:bd:1d", "00:e0:4c",  # 00:e0:4c = Realtek (seen on Dahua speakers)
}


class DahuaError(RuntimeError):
    pass


@dataclass
class DahuaDevice:
    host: str
    reachable: bool = False
    is_dahua: bool = False
    device_type: str = ""     # e.g. "IPC-...", "VTO...", "VCS-SH30"
    raw: str = ""


def _looks_dahua(text: str) -> bool:
    t = (text or "").lower()
    return any(s in t for s in ("dahua", '"result"', "rpc2", "devicetype", "magicbox"))


def identify(host: str, username: str = "admin", password: str = "",
             *, timeout: float = 5.0) -> DahuaDevice:
    """Best-effort Dahua fingerprint.

    Tries the unauthenticated ``RPC2_Login`` probe (Dahua answers with a JSON
    ``result``/``session`` challenge), then the Digest ``magicBox`` device-type
    CGI. Does not raise on non-Dahua hosts.
    """
    dev = DahuaDevice(host=host)
    # 1) RPC2 login challenge — no auth needed, distinctive JSON
    try:
        r = requests.post(f"http://{host}/RPC2_Login", timeout=timeout,
                          json={"method": "global.login", "params": {}, "id": 1})
        dev.reachable = True
        if _looks_dahua(r.text):
            dev.is_dahua = True
            dev.raw = r.text[:200]
    except requests.RequestException:
        pass
    # 2) magicBox device type (Digest) for the model string
    try:
        r = requests.get(f"http://{host}/cgi-bin/magicBox.cgi?action=getDeviceType",
                         auth=HTTPDigestAuth(username, password), timeout=timeout)
        dev.reachable = True
        if r.status_code == 200 and "=" in r.text:
            dev.is_dahua = True
            dev.device_type = r.text.split("=", 1)[1].strip()
    except requests.RequestException:
        pass
    return dev


class DahuaClient:
    """Digest-authenticated client for one Dahua device.

    Usage::

        d = DahuaClient("192.0.2.9", "admin", "...")
        d.device_type()                          # "VCS-SH30"
        sip = d.get_config("SIP")                # {"SIP[0].Enable": "true", ...}
        d.set_config({"SIP[0].SipServer.Address": "192.0.2.10"})
    """

    def __init__(self, host: str, username: str = "admin", password: str = "",
                 *, timeout: float = 8.0) -> None:
        self.host = host
        self._timeout = timeout
        self._base = f"http://{host}"
        self._s = requests.Session()
        self._s.auth = HTTPDigestAuth(username, password)
        self._user = username
        self._password = password

    def _cgi(self, path: str, params=None) -> str:
        r = self._s.get(f"{self._base}{path}", params=params, timeout=self._timeout)
        if r.status_code == 401:
            raise DahuaError(f"{self.host}: 401 (bad credentials)")
        if r.status_code != 200:
            raise DahuaError(f"{self.host}: {path} HTTP {r.status_code}: {r.text[:80]}")
        return r.text

    # ── device info ─────────────────────────────────────────────────
    def device_type(self) -> str:
        t = self._cgi("/cgi-bin/magicBox.cgi", {"action": "getDeviceType"})
        return t.split("=", 1)[1].strip() if "=" in t else t.strip()

    def system_info(self) -> dict[str, str]:
        return parse_config(self._cgi("/cgi-bin/magicBox.cgi", {"action": "getSystemInfo"}))

    # ── config get/set ──────────────────────────────────────────────
    def get_config(self, name: str) -> dict[str, str]:
        """Read a config table, e.g. ``get_config("SIP")``."""
        return parse_config(self._cgi("/cgi-bin/configManager.cgi",
                                      {"action": "getConfig", "name": name}))

    def set_config(self, values: dict[str, str]) -> None:
        """Write config items, e.g.
        ``{"SIP[0].SipServer.Address": "192.0.2.10", "SIP[0].Enable": "true"}``.
        """
        params = [("action", "setConfig")] + to_setconfig_params(values)
        text = self._cgi("/cgi-bin/configManager.cgi", params)
        if "OK" not in text and "ok" not in text:
            raise DahuaError(f"{self.host}: setConfig did not return OK: {text[:80]}")

    # ── SIP convenience (bare-bones IP-speaker registration) ────────
    def get_sip(self, index: int = 0) -> dict[str, str]:
        return {k: v for k, v in self.get_config("SIP").items() if k.startswith(f"SIP[{index}]")}

    def set_sip_server(self, address: str, port: int = 5060, index: int = 0) -> None:
        """Point the speaker's SIP registration at ``address``."""
        self.set_config({
            f"SIP[{index}].SipServer.Address": address,
            f"SIP[{index}].SipServer.Port": str(port),
            f"SIP[{index}].Enable": "true",
        })

    # ── control ─────────────────────────────────────────────────────
    def reboot(self) -> None:
        self._cgi("/cgi-bin/magicBox.cgi", {"action": "reboot"})

    def change_password(self, old_password: str, new_password: str) -> None:
        """Change this user's password per Dahua HTTP API V1.67, section 9.7.7.

        On success, rebinds this client's own Digest auth to ``new_password`` —
        the device now rejects the old one, so a caller that reuses this client
        (e.g. to verify the change) must not have to know that internally.
        """
        text = self._cgi(
            "/cgi-bin/userManager.cgi",
            {
                "action": "modifyPassword",
                "name": self._user,
                "pwd": new_password,
                "pwdOld": old_password,
            },
        )
        if text.strip().upper() != "OK":
            raise DahuaError(f"{self.host}: modifyPassword did not return OK")
        self._password = new_password
        self._s.auth = HTTPDigestAuth(self._user, new_password)

    # ── RPC2 (for methods with no CGI equivalent) ───────────────────
    def rpc_login(self) -> str:
        """Perform the Dahua RPC2 two-step MD5 login; returns the session id.

        Step 1 posts ``global.login`` with an empty password to obtain the
        ``realm`` + ``random`` challenge; step 2 posts the MD5 digest
        ``MD5( user:random: MD5(user:realm:password) )`` (hex, uppercase).
        """
        r1 = self._s.post(f"{self._base}/RPC2_Login", timeout=self._timeout, json={
            "method": "global.login", "id": 1,
            "params": {"userName": self._user, "password": "",
                       "clientType": "Web3.0", "loginType": "Direct"},
        }).json()
        params = r1.get("params", {})
        realm, random = params.get("realm", ""), params.get("random", "")
        session = r1.get("session")
        ha = hashlib.md5(f"{self._user}:{realm}:{self._password}".encode()).hexdigest().upper()
        resp = hashlib.md5(f"{self._user}:{random}:{ha}".encode()).hexdigest().upper()
        r2 = self._s.post(f"{self._base}/RPC2_Login", timeout=self._timeout, json={
            "method": "global.login", "id": 2, "session": session,
            "params": {"userName": self._user, "password": resp,
                       "clientType": "Web3.0", "authorityType": "Default",
                       "passwordType": "Default"},
        }).json()
        if not r2.get("result"):
            raise DahuaError(f"{self.host}: RPC2 login failed: {r2.get('error')}")
        return str(session)


_MAC_RE = re.compile(r"([0-9a-f]{2}(?::[0-9a-f]{2}){5})", re.IGNORECASE)


def is_dahua_mac(mac: str) -> bool:
    """True if ``mac``'s OUI is a known Dahua/Dahua-SoC prefix."""
    m = _MAC_RE.search(mac or "")
    if not m:
        return False
    return m.group(1).lower()[:8] in DAHUA_OUIS
