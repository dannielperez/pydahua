# Consumer contract replay fixtures

Sanitized Dahua CGI response bodies used to pin the wire shapes that
`DahuaClient` parses on behalf of the `dahua_sdk` boundary
(`uniqueos/devices/services/dahua_sdk.py`). They contain no credentials,
customer hostnames, or real device identifiers.

- `get_device_type.txt` — `magicBox.cgi?action=getDeviceType` success body.
- `modify_password_ok.txt` — `userManager.cgi?action=modifyPassword` success body.
- `modify_password_error.txt` — the same endpoint's non-OK failure body.

Tests replay these files entirely in-process by stubbing the client's
`requests.Session`; they never contact a device.
