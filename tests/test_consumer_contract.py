"""Consumer-contract tests for pydahua's public API.

Pins the exact names, construction signature, and CGI response parsing that
``uniqueos/devices/services/dahua_sdk.py`` (the boundary seam) and
``uniqueos/devices/services/dahua.py`` (the read-first adapter) depend on. The
replay fixtures are sanitized and all HTTP is stubbed in-process — no network.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import requests

import pydahua
from pydahua import DahuaClient, DahuaDevice, DahuaError, identify, is_dahua_mac

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "consumer_contracts"


def _fixture_response(name: str, status_code: int = 200) -> requests.Response:
    resp = requests.Response()
    resp.status_code = status_code
    resp._content = (FIXTURE_DIR / name).read_bytes()
    return resp


class TestPublicApiContract:
    """Pin the names dahua_sdk.py re-exports and their error hierarchy."""

    def test_boundary_critical_names_are_exported(self) -> None:
        required = {"DahuaClient", "DahuaDevice", "DahuaError", "identify", "is_dahua_mac"}
        assert required <= set(pydahua.__all__)
        assert all(getattr(pydahua, name) is not None for name in required)

    def test_dahua_error_is_a_runtime_error(self) -> None:
        assert issubclass(DahuaError, RuntimeError)

    def test_dahua_device_carries_the_identify_fields(self) -> None:
        device = DahuaDevice(host="device.example.invalid")
        assert device.reachable is False
        assert device.is_dahua is False
        assert device.device_type == ""


class TestSupportedConstruction:
    """Pin the DahuaAdapter._build_client() keyword contract."""

    def test_client_accepts_the_adapter_keyword_contract(self) -> None:
        client = DahuaClient(
            "device.example.invalid",
            username="operator",
            password="synthetic-password",
            timeout=7,
        )
        assert client.host == "device.example.invalid"
        assert client._timeout == 7


class TestSanitizedReplay:
    """Replay recorded CGI response bodies through the real client parsing."""

    def test_device_type_replay_returns_typed_string(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        client = DahuaClient("device.example.invalid", username="admin", password="pw")
        monkeypatch.setattr(
            client._s,
            "get",
            lambda *a, **k: _fixture_response("get_device_type.txt"),
        )

        assert client.device_type() == "NVR608-32B-4KS2"

    def test_change_password_replay_rebinds_auth_on_success(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        client = DahuaClient("device.example.invalid", username="operator", password="old-secret")
        monkeypatch.setattr(
            client._s,
            "get",
            lambda *a, **k: _fixture_response("modify_password_ok.txt"),
        )

        client.change_password("old-secret", "new-secret")

        assert client._password == "new-secret"
        assert client._s.auth.password == "new-secret"

    def test_change_password_replay_raises_dahua_error_on_failure(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        client = DahuaClient("device.example.invalid", username="operator", password="old-secret")
        monkeypatch.setattr(
            client._s,
            "get",
            lambda *a, **k: _fixture_response("modify_password_error.txt"),
        )

        with pytest.raises(DahuaError):
            client.change_password("old-secret", "new-secret")

        # A rejected change must not rebind auth to the attempted new password.
        assert client._password == "old-secret"


class TestIdentifyContract:
    """Pin identify()'s degrade-safe, non-raising probe behavior."""

    def test_identify_never_raises_on_unreachable_host(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        def _raise(*args: object, **kwargs: object) -> None:
            raise requests.RequestException("simulated network failure")

        monkeypatch.setattr(requests, "post", _raise)
        monkeypatch.setattr(requests, "get", _raise)

        result = identify("device.example.invalid", timeout=1.0)

        assert isinstance(result, DahuaDevice)
        assert result.reachable is False
        assert result.is_dahua is False

    def test_is_dahua_mac_recognizes_a_known_oui(self) -> None:
        assert is_dahua_mac("3c:ef:8c:11:22:33") is True
        assert is_dahua_mac("00:00:00:00:00:00") is False
