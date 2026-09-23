"""Overview HTML regression checks against the supplied dataset; no API calls."""

from html.parser import HTMLParser
from pathlib import Path
import unittest
from urllib.parse import parse_qs

import pandas as pd

from overview_workspace import render_overview
from pipeline import load_data, make_graph


ROOT = Path(__file__).resolve().parents[1]


class _Links(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            self.links.append(dict(attrs))


class OverviewWorkspaceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.roles = pd.read_csv(ROOT / "out" / "nodes_roles.csv").set_index("gid", drop=False)
        cls.top = pd.read_csv(ROOT / "out" / "top_nodes.csv")
        nodes, edges, cls.tx = load_data(ROOT / "data")
        cls.graph = make_graph(nodes, edges)

    def render(self, roles=None, top=None):
        return render_overview(
            self.graph, self.roles if roles is None else roles,
            self.top if top is None else top, self.tx,
        )

    def test_data_backed_overview_and_lossless_navigation(self):
        html = self.render()
        self.assertIn("Кого проверить следующим?", html)
        self.assertIn("2 248", html)
        self.assertIn("4 840", html)
        self.assertIn("Июль 2026 · 4 колена", html)
        self.assertEqual(html.count('class="mm-stat"'), 4)
        self.assertEqual(html.count('class="mm-signal"'), 3)
        self.assertEqual(html.count('class="mm-step"'), 3)
        self.assertEqual(html.count("<tr>"), 4)
        parser = _Links()
        parser.feed(html)
        investigation_gids = []
        for link in parser.links:
            self.assertEqual(link["target"], "_self")
            params = parse_qs(link["href"].removeprefix("?"))
            if params["section"] == ["investigation"]:
                gid = params["gid"][0]
                self.assertIn(int(gid), self.graph)
                self.assertEqual(gid, str(int(gid)))
                investigation_gids.append(gid)
        for gid in self.top.head(3).gid:
            self.assertIn(str(gid), investigation_gids)

    def test_unknown_role_is_escaped_in_text_and_attributes(self):
        roles, top = self.roles.copy(), self.top.copy()
        malicious = '<script>alert("not HTML")</script>'
        gid = int(top.iloc[0]["gid"])
        roles.loc[gid, "role"] = malicious
        top.loc[top.index[0], "role"] = malicious
        html = self.render(roles, top)
        self.assertNotIn("<script>", html)
        self.assertIn("&lt;script&gt;", html)

    def test_empty_queue(self):
        html = self.render(top=self.top.iloc[:0])
        self.assertIn("Очередь проверки пуста", html)
        self.assertNotIn("mm-score-panel", html)


if __name__ == "__main__":
    unittest.main()
