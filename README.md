# pydahua

Small Python helpers for **Dahua** devices — IP speakers, intercoms/VTO, and
cameras — over the HTTP **CGI** API and **RPC2** (JSON-RPC), alongside the
sibling `pyakuvox` / `pyalgo` / `pyfanvil` wrappers.

## Scope (v0.1)

- **Identify** a host as Dahua (`identify()`, `is_dahua_mac()`): RPC2 login
  challenge + `magicBox` device type; MAC-OUI check.
- **Device info** — `device_type()`, `system_info()` (`magicBox.cgi`).
- **Config get/set** — `get_config("SIP")` / `set_config({...})`
  (`configManager.cgi`), with the flat `Table[i].Key=value` format parsed for
  you.
- **SIP convenience** — `get_sip()` / `set_sip_server(address, port)` to point a
  bare-bones IP speaker's registration at a new SIP server.
- **Control** — `reboot()`; `rpc_login()` for the RPC2 MD5 challenge when a
  method has no CGI equivalent.

ONVIF (used to attach a speaker to an NVR's audio-out) is out of scope here.

## Quick example

```python
from pydahua import DahuaClient, identify

print(identify("192.0.2.9"))                 # DahuaDevice(is_dahua=True, device_type="VCS-SH30")

d = DahuaClient("192.0.2.9", "admin", "...")
print(d.device_type())
print(d.get_sip())                            # {"SIP[0].Enable": "true", ...}
d.set_sip_server("192.0.2.10", port=5060)     # repoint registration
```

## Auth

All CGI + RPC2 calls use HTTP **Digest** auth (Dahua default user `admin`).
Config values are strings; Dahua expects literal `true`/`false`.

## Notes

- Dahua IP speakers are frequently deployed on an NVR's **camera-side LAN**
  (e.g. `192.168.1.0/24`) and attached to the recorder over ONVIF rather than
  registered to a PBX — so locate them via the NVR's device list / MAC OUI, not
  by SIP registration.
- This package is intentionally generic; site inventory and credentials live in
  the private consumers.

## Testing

```bash
pip install -e ".[dev]"
pytest -q
```

## License

[MIT](LICENSE).
