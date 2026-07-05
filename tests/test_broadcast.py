"""Offline tests for the Dahua broadcast (网络广播终端) /prod-api client."""
from __future__ import annotations

import base64

from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

from pydahua.broadcast import build_sip_edit_payload, rsa_encrypt_password

# A real-shaped device/info data blob (SIP pointed at the old SBC).
DEVINFO = {
    "sip": "on", "id": "1", "ip": "10.40.31.4",
    "sipAddress": "52.54.18.219", "sipUsername": "1802",
    "sipPassword": "ENC_PW_BLOB_A==", "sipPassword2": "ENC_PW_BLOB_B==",
    "mac": "00:e0:4c:f9:fb:a4", "dhcp": "on",  # extra keys must be ignored
}


def test_build_payload_swaps_only_sipaddress():
    p = build_sip_edit_payload(DEVINFO, "10.254.250.11")
    assert p["sipAddress"] == "10.254.250.11"
    assert p["sipUsername"] == "1802"
    assert p["sip"] == "on"
    assert p["id"] == "1" and p["ip"] == "10.40.31.4"


def test_build_payload_reuses_encrypted_passwords_verbatim():
    p = build_sip_edit_payload(DEVINFO, "10.254.250.11")
    assert p["sipPassword"] == "ENC_PW_BLOB_A=="
    assert p["sipPassword2"] == "ENC_PW_BLOB_B=="


def test_build_payload_only_edit_keys():
    p = build_sip_edit_payload(DEVINFO, "10.254.250.11")
    assert set(p) == {"sip", "id", "ip", "sipAddress", "sipUsername",
                      "sipPassword", "sipPassword2"}
    assert "mac" not in p and "dhcp" not in p


def test_build_payload_defaults_sip_on_when_missing():
    p = build_sip_edit_payload({"sipUsername": "1802"}, "10.254.250.11")
    assert p["sip"] == "on"


def test_build_payload_does_not_mutate_input():
    before = dict(DEVINFO)
    build_sip_edit_payload(DEVINFO, "10.254.250.11")
    assert before == DEVINFO


def test_rsa_encrypt_password_roundtrips():
    # generate a keypair, hand the public DER (base64) to the fn, decrypt with private
    key = rsa.generate_private_key(public_exponent=65537, key_size=1024)
    pub_der_b64 = base64.b64encode(
        key.public_key().public_bytes(Encoding.DER, PublicFormat.SubjectPublicKeyInfo)
    ).decode()
    ct = rsa_encrypt_password(pub_der_b64, "s3cret-pw")
    pt = key.decrypt(base64.b64decode(ct), padding.PKCS1v15())
    assert pt == b"s3cret-pw"


def test_rsa_encrypt_password_output_is_base64():
    key = rsa.generate_private_key(public_exponent=65537, key_size=1024)
    pub = base64.b64encode(
        key.public_key().public_bytes(Encoding.DER, PublicFormat.SubjectPublicKeyInfo)
    ).decode()
    out = rsa_encrypt_password(pub, "x")
    base64.b64decode(out)  # must not raise
