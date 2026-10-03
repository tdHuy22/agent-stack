"""Chạy nhiều luồng chuyển tiền ngẫu nhiên rồi kiểm tổng tiền."""
import random
import threading

from bank import Bank, InsufficientFunds

NAMES = ["a", "b", "c", "d"]


def worker(bank, seed):
    rnd = random.Random(seed)
    for _ in range(200):
        src, dst = rnd.sample(NAMES, 2)
        try:
            bank.transfer(src, dst, rnd.randint(1, 30))
        except InsufficientFunds:
            pass


def main():
    bank = Bank({n: 1000 for n in NAMES})
    threads = [threading.Thread(target=worker, args=(bank, i)) for i in range(6)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    print("tổng:", bank.total(), "(phải là 4000)")


if __name__ == "__main__":
    main()
