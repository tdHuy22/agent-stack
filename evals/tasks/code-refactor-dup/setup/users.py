import re

EMAIL_RE = r"^[^@\s]+@[^@\s]+\.[a-z]{2,}$"


def create_user(email, name):
    email = email.strip().lower()
    if not re.match(EMAIL_RE, email):
        raise ValueError(f"Email không hợp lệ: {email}")
    return {"email": email, "name": name}


def change_email(user, email):
    email = email.strip().lower()
    if not re.match(EMAIL_RE, email):
        raise ValueError(f"Email không hợp lệ: {email}")
    return dict(user, email=email)
