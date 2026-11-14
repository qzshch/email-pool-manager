from .addressing import generate_email
from .imap_otp import get_verification_code
from .mailtm import create_mailtm_inbox
from .tempmail import create_tempmail_inbox

__all__ = [
    "generate_email",
    "get_verification_code",
    "create_tempmail_inbox",
    "create_mailtm_inbox",
]
