"""Tách họ tên cho phần mềm nhân sự."""


def tach_ho_ten(ho_va_ten):
    """Tách họ tên đầy đủ thành họ, đệm, tên."""
    chu = ho_va_ten.split()
    return {"ho": chu[0], "dem": " ".join(chu[1:-1]), "ten": chu[-1]}


if __name__ == "__main__":
    print(tach_ho_ten("Nguyễn Văn An"))
    print(tach_ho_ten("Tôn Nữ Thị Hạnh"))
