"""
OTP extraction from email content using regex patterns.
"""
import re

# Common OTP patterns
OTP_PATTERNS = [
    # "Your OTP is 123456"
    r'\b(?:otp|one.time.password|verification.code|auth(?:entication)?.code|code)\s*(?:is|:|\s)\s*(\d{4,8})\b',
    # "123456 is your code"
    r'\b(\d{4,8})\s+is\s+your\s+(?:otp|code|verification|auth(?:entication)?.code)',
    # Standalone 6-digit code on its own line or with minimal context
    r'(?:^|\s)(\d{6})(?:\s|$)',
    # PIN codes like "Your PIN: 1234"
    r'\bpin\s*(?:is|:|\s)\s*(\d{4,8})\b',
    # Hyphen-separated: "code: 123-456"
    r'\bcode\s*[:\-]\s*(\d{3}[-\s]\d{3})\b',
]

COMPILED = [re.compile(p, re.IGNORECASE | re.MULTILINE) for p in OTP_PATTERNS]


def extract_otp(text: str) -> str | None:
    """Extract OTP from email body/subject text. Returns the first match."""
    for pattern in COMPILED:
        m = pattern.search(text)
        if m:
            code = m.group(1).replace("-", "").replace(" ", "")
            if code.isdigit() and 4 <= len(code) <= 8:
                return code
    return None


def looks_like_otp_email(subject: str, body: str) -> bool:
    """Heuristic: does this email look like an OTP/verification email?"""
    otp_keywords = [
        "otp", "one-time", "one time", "verification code", "auth code",
        "authentication code", "login code", "security code", "passcode",
        "access code", "confirm", "verify", "2fa", "two-factor",
    ]
    combined = (subject + " " + body[:500]).lower()
    keyword_match = any(kw in combined for kw in otp_keywords)
    has_code = extract_otp(subject + " " + body) is not None
    return keyword_match and has_code
