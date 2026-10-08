import sys, unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from rankings import build_table, render


class TestTable(unittest.TestCase):
    def test_win(self):
        rows = build_table(["Anh", "Bac"], [("Anh", 2, "Bac", 0)])
        self.assertEqual([r.name for r in rows], ["Anh", "Bac"])
        self.assertEqual((rows[0].points, rows[0].gd), (3, 2))
        self.assertEqual((rows[1].points, rows[1].gd), (0, -2))

    def test_draw_gives_both_a_point(self):
        rows = build_table(["Anh", "Bac"], [("Anh", 1, "Bac", 1)])
        self.assertEqual([r.points for r in rows], [1, 1])

    def test_unknown_team(self):
        with self.assertRaises(ValueError):
            build_table(["Anh"], [("Anh", 1, "Zed", 0)])

    def test_render_line(self):
        rows = build_table(["Anh", "Bac"], [("Anh", 2, "Bac", 0)])
        self.assertEqual(render(rows).splitlines()[0], " 1. Anh           1   3")


if __name__ == "__main__":
    unittest.main()
