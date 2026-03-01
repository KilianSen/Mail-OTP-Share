"""
Tests for OTP extraction logic.
"""
import pytest
from app.otp_extractor import extract_otp, looks_like_otp_email


@pytest.mark.parametrize("text,expected", [
    ("Your OTP is 123456", "123456"),
    ("Verification code: 789012", "789012"),
    ("Your PIN: 4321", "4321"),
    ("123456 is your login code", "123456"),
    ("Your authentication code is 654321", "654321"),
    ("Use code 111222 to log in", "111222"),
    ("Hello world", None),
    ("No digits here", None),
])
def test_extract_otp(text, expected):
    assert extract_otp(text) == expected


@pytest.mark.parametrize("subject,body,expected", [
    ("Your OTP is ready", "Use 123456 to verify your account", True),
    ("Verification code", "Your code is 789012", True),
    ("Hello", "How are you?", False),
    ("Invoice #123", "Please pay 1000 USD", False),
    ("Login verification", "Your one-time code: 445566", True),
])
def test_looks_like_otp_email(subject, body, expected):
    assert looks_like_otp_email(subject, body) == expected
