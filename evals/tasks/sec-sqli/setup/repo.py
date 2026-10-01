import sqlite3

DB = sqlite3.connect(":memory:")


def get_user(username):
    query = f"SELECT id, email FROM users WHERE name = '{username}'"
    return DB.execute(query).fetchone()


def get_order(order_id):
    return DB.execute("SELECT * FROM orders WHERE id = ?", (order_id,)).fetchone()
