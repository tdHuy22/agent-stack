import os

BASE = "/srv/uploads"


def download(filename):
    path = os.path.join(BASE, filename)
    with open(path, "rb") as fh:
        return fh.read()


def list_files():
    return sorted(os.listdir(BASE))
