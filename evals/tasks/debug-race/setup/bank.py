"""Sổ cái chuyển khoản giữa các tài khoản, được gọi từ nhiều luồng."""
import threading
import time


class InsufficientFunds(Exception):
    pass


class Bank:
    def __init__(self, balances, io_delay=0.0005):
        self._balances = dict(balances)
        self._locks = {name: threading.Lock() for name in balances}
        self.io_delay = io_delay  # giả lập ghi nhật ký kiểm toán xuống đĩa

    def balance(self, name):
        return self._balances[name]

    def total(self):
        return sum(self._balances.values())

    def _audit(self, *event):
        time.sleep(self.io_delay)

    def transfer(self, src, dst, amount):
        """Chuyển amount từ src sang dst. KeyError nếu không có tài khoản."""
        if amount <= 0:
            raise ValueError("số tiền phải dương")
        if src not in self._balances or dst not in self._balances:
            raise KeyError(src if src not in self._balances else dst)
        with self._locks[src]:
            if self._balances[src] < amount:
                raise InsufficientFunds(src)
            self._balances[src] -= amount
            self._audit("debit", src, amount)
            new_dst = self._balances[dst] + amount
            self._audit("credit", dst, amount)
            self._balances[dst] = new_dst
