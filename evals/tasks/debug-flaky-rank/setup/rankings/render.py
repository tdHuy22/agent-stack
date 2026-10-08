def render(rows):
    lines = []
    for index, row in enumerate(rows):
        lines.append(f"{index + 1:>2}. {row.name:<12}{row.played:>3}{row.points:>4}")
    return "\n".join(lines) + "\n"
