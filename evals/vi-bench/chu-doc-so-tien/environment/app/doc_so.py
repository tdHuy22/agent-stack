"""Đọc số tiền thành chữ cho phiếu chi."""

CHU = ["không", "một", "hai", "ba", "bốn", "năm", "sáu", "bảy", "tám", "chín"]


def _doc_ba_so(n):
    tram, chuc, dv = n // 100, n // 10 % 10, n % 10
    out = []
    if tram:
        out.append(CHU[tram] + " trăm")
    if chuc:
        out.append(CHU[chuc] + " mươi")
    if dv:
        out.append(CHU[dv])
    return " ".join(out)


def doc_so_tien(n):
    """Đọc số tiền (số nguyên đồng) thành chữ, ví dụ 24 -> 'Hai mươi bốn đồng'."""
    n = int(n)
    if n == 0:
        return "Không đồng"
    nhom = []
    for ten in ("", " nghìn", " triệu", " tỷ"):
        nhom.append((n % 1000, ten))
        n //= 1000
    chu = " ".join(_doc_ba_so(g) + t for g, t in reversed(nhom) if g)
    return chu.capitalize() + " đồng"


if __name__ == "__main__":
    for so in (0, 24, 1250005, 2000000000):
        print(so, "->", doc_so_tien(so))
