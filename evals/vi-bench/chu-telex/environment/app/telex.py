"""Sửa chữ Telex còn sót trong văn bản nhập từ bộ gõ lỗi."""
import re

CAP = {"aa": "â", "aw": "ă", "ee": "ê", "oo": "ô", "ow": "ơ", "uw": "ư", "dd": "đ"}


def sua_telex(van_ban):
    """Đổi các chữ gõ Telex thô (như 'vieetj') thành chữ tiếng Việt."""
    def doi(m):
        w = m.group(0)
        for k, v in CAP.items():
            w = w.replace(k, v)
        return w
    return re.sub(r"[A-Za-z]+", doi, van_ban)


if __name__ == "__main__":
    print(sua_telex("Tooi ddang hocj tieengs Vieetj"))
