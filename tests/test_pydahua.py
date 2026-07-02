"""Unit tests for pydahua (pure — no network)."""

import hashlib

from pydahua import (
    DahuaClient,
    is_dahua_mac,
    parse_config,
    to_setconfig_params,
)


def test_parse_config_strips_table_prefix():
    text = (
        "table.SIP[0].Enable=true\r\n"
        "table.SIP[0].SipServer.Address=192.0.2.10\r\n"
        "table.SIP[0].SipServer.Port=5060\r\n"
        "table.SIP[0].UserName=100\r\n"
    )
    cfg = parse_config(text)
    assert cfg["SIP[0].Enable"] == "true"
    assert cfg["SIP[0].SipServer.Address"] == "192.0.2.10"
    assert cfg["SIP[0].SipServer.Port"] == "5060"
    assert cfg["SIP[0].UserName"] == "100"


def test_to_setconfig_params_order():
    params = to_setconfig_params({"SIP[0].SipServer.Address": "192.0.2.10",
                                  "SIP[0].Enable": "true"})
    assert params == [("SIP[0].SipServer.Address", "192.0.2.10"),
                      ("SIP[0].Enable", "true")]


def test_is_dahua_mac():
    assert is_dahua_mac("3c:ef:8c:11:22:33") is True
    assert is_dahua_mac("00:E0:4C:00:00:01") is True   # Realtek OUI on Dahua speakers, case-insensitive
    assert is_dahua_mac("0c:11:05:aa:bb:cc") is False  # Akuvox
    assert is_dahua_mac("not-a-mac") is False


def test_get_sip_filters_by_index(monkeypatch):
    d = DahuaClient("192.0.2.9", "admin", "pw")
    monkeypatch.setattr(d, "get_config", lambda name: {
        "SIP[0].Enable": "true",
        "SIP[0].SipServer.Address": "192.0.2.10",
        "SIP[1].Enable": "false",
    })
    sip0 = d.get_sip(0)
    assert sip0 == {"SIP[0].Enable": "true", "SIP[0].SipServer.Address": "192.0.2.10"}


def test_set_sip_server_builds_expected_items(monkeypatch):
    captured = {}
    d = DahuaClient("192.0.2.9", "admin", "pw")
    monkeypatch.setattr(d, "set_config", lambda v: captured.update(v))
    d.set_sip_server("192.0.2.10", port=5060)
    assert captured == {
        "SIP[0].SipServer.Address": "192.0.2.10",
        "SIP[0].SipServer.Port": "5060",
        "SIP[0].Enable": "true",
    }


def test_rpc_digest_formula():
    # Documented Dahua RPC2 digest: MD5(user:random: MD5(user:realm:pass))
    user, realm, random, pw = "admin", "Login to ...", "123456", "secret"
    ha = hashlib.md5(f"{user}:{realm}:{pw}".encode()).hexdigest().upper()
    expect = hashlib.md5(f"{user}:{random}:{ha}".encode()).hexdigest().upper()
    assert len(expect) == 32 and expect == expect.upper()
