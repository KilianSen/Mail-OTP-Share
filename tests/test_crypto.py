"""
Tests for encryption utilities.
"""
from app.crypto import encrypt, decrypt


def test_encrypt_decrypt_roundtrip():
    plaintext = "super-secret-password-123!"
    ciphertext = encrypt(plaintext)
    assert ciphertext != plaintext
    assert decrypt(ciphertext) == plaintext


def test_encrypt_empty_string():
    assert encrypt("") == ""
    assert decrypt("") == ""


def test_decrypt_invalid_returns_empty():
    result = decrypt("not-valid-ciphertext")
    assert result == ""
