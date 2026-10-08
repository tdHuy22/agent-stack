from .model import Row


def _apply(row, scored, conceded):
    row.played += 1
    row.gf += scored
    row.ga += conceded
    row.gd = row.gf - row.ga
    if scored > conceded:
        row.won += 1
        row.points += 3
    elif scored == conceded:
        row.drawn += 1
        row.points += 1
    else:
        row.lost += 1


def build_table(roster, matches):
    rows = {name: Row(name) for name in roster}
    for home, hg, away, ag in matches:
        if home not in rows or away not in rows:
            raise ValueError("đội ngoài danh sách")
        _apply(rows[home], hg, ag)
        _apply(rows[away], ag, hg)
    ordered = list(rows.values())  # dict giữ thứ tự roster; sort ổn định
    ordered.sort(key=lambda r: (-r.points, -r.gd, -r.gf, r.name.casefold()))
    return ordered
