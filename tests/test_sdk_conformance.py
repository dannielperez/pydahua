"""Contract tests for the pydahua surface imported by UniqueOS.

The response bodies are sanitized recordings of the two probes performed by
``identify()``.  All HTTP is replaced locally; these tests never contact a
device.
"""

from dataclasses import fields
from types import SimpleNamespace

import pytest

import pydahua
from pydahua import DahuaClient, DahuaDevice, DahuaError, identify, is_dahua_mac
from pydahua import client as client_module

CONSUMED_EXPORTS = {
    "DahuaClient",
    "DahuaDevice",
    "DahuaError",
    "identify",
    "is_dahua_mac",
}
RECORDED_RPC_LOGIN = '{"id":1,"result":false,"session":123456789}'
RECORDED_DEVICE_TYPE = "type=IPC-HDW1230T1\r\n"


def test_uniqueos_consumed_names_are_public_exports():
    assert set(pydahua.__all__) >= CONSUMED_EXPORTS
    for name in CONSUMED_EXPORTS:
        assert getattr(pydahua, name) is not None


def test_dahua_device_dto_shape_is_stable():
    assert [field.name for field in fields(DahuaDevice)] == [
        "host",
        "reachable",
        "is_dahua",
        "device_type",
        "raw",
    ]

    device = DahuaDevice(host="192.0.2.40")
    assert device == DahuaDevice(
        host="192.0.2.40",
        reachable=False,
        is_dahua=False,
        device_type="",
        raw="",
    )


def test_identify_replays_recorded_probe_responses(monkeypatch):
    calls = []

    def fake_post(url, **kwargs):
        calls.append(("POST", url, kwargs))
        return SimpleNamespace(text=RECORDED_RPC_LOGIN)

    def fake_get(url, **kwargs):
        calls.append(("GET", url, kwargs))
        return SimpleNamespace(status_code=200, text=RECORDED_DEVICE_TYPE)

    monkeypatch.setattr(client_module.requests, "post", fake_post)
    monkeypatch.setattr(client_module.requests, "get", fake_get)

    device = identify("192.0.2.40", username="operator", password="secret", timeout=2.5)

    assert isinstance(device, DahuaDevice)
    assert device == DahuaDevice(
        host="192.0.2.40",
        reachable=True,
        is_dahua=True,
        device_type="IPC-HDW1230T1",
        raw=RECORDED_RPC_LOGIN,
    )
    assert [(method, kwargs["timeout"]) for method, _url, kwargs in calls] == [
        ("POST", 2.5),
        ("GET", 2.5),
    ]


def test_client_raises_public_error_for_auth_failure(monkeypatch):
    client = DahuaClient("192.0.2.40", timeout=1.5)
    response = SimpleNamespace(status_code=401, text="Unauthorized")
    monkeypatch.setattr(client._s, "get", lambda *args, **kwargs: response)

    with pytest.raises(DahuaError, match="401"):
        client.device_type()


def test_mac_helper_remains_callable_from_public_surface():
    assert is_dahua_mac("3c:ef:8c:11:22:33") is True
