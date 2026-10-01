import re

EMAIL_RE = r"^[^@\s]+@[^@\s]+\.[a-z]{2,}$"


def normalize_email(email):
    email = email.strip().lower()
    if not re.match(EMAIL_RE, email):
        raise ValueError(f"Email không hợp lệ: {email}")
    return email


def create_user(email, name):
    return {"email": normalize_email(email), "name": name}


def change_email(user, email):
    return dict(user, email=normalize_email(email))
