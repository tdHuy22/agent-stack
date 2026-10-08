def render(rows):
    lines = []
    prev, rank = None, 0
    for index, row in enumerate(rows):
        key = (row.points, row.gd, row.gf)
        if key != prev:
            rank = index + 1
            prev = key
        lines.append(f"{rank:>2}. {row.name:<12}{row.played:>3}{row.points:>4}")
    return "\n".join(lines)
