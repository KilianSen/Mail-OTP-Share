"""
Tests for email command parsing.
"""
import pytest
from app.scheduler import parse_command


@pytest.mark.parametrize("subject,expected", [
    ("SHARE REQUEST user@test.com", {"command": "SHARE_REQUEST", "arg": "user@test.com"}),
    ("share request user@test.com", {"command": "SHARE_REQUEST", "arg": "user@test.com"}),
    ("APPROVE 42", {"command": "APPROVE", "arg": "42"}),
    ("approve 42", {"command": "APPROVE", "arg": "42"}),
    ("DECLINE 7", {"command": "DECLINE", "arg": "7"}),
    ("STOP 15", {"command": "STOP", "arg": "15"}),
    ("Hello world", None),
    ("Re: random email", None),
    ("", None),
])
def test_parse_command(subject, expected):
    assert parse_command(subject) == expected
