import re


def slugify(text):
    """Chữ thường, thay mọi chuỗi ký tự không phải chữ hoặc số bằng một dấu gạch ngang, bỏ gạch ở hai đầu."""
    text = text.lower()
    text = re.sub(r"[^a-z0-9]+", "-", text)
    return text.strip("-")
