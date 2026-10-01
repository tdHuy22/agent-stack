import sys


def count(path):
    text = open(path, encoding="utf-8").read()
    return len(text.splitlines()), len(text.split())


def main(argv):
    lines, words = count(argv[-1])
    print(f"{lines} dòng, {words} từ")


if __name__ == "__main__":
    main(sys.argv[1:])
