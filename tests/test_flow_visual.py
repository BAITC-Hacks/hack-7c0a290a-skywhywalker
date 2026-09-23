"""The display must preserve the identity, amount and direction of real edges."""

from base64 import b64decode
import unittest
import xml.etree.ElementTree as ET

import networkx as nx
import pandas as pd

from flow_visual import render_flow_html, render_flow_svg


NS = {"svg": "http://www.w3.org/2000/svg"}


class FlowVisualTests(unittest.TestCase):
    gid = 100000008603629100

    def roles(self, graph):
        return pd.DataFrame([
            {"gid": node, "role": "coordinator" if node == self.gid else "transit", "is_seed": node == 1}
            for node in graph
        ]).set_index("gid")

    def render(self, graph, roles=None):
        svg = render_flow_svg(graph, roles if roles is not None else self.roles(graph), self.gid)
        return svg, ET.fromstring(svg)

    def test_exact_ids_amounts_and_directed_links(self):
        graph = nx.DiGraph()
        graph.add_edge(100000000000000001, self.gid, sum_kzt=1250000, n_tx=12)
        graph.add_edge(self.gid, 100000000000000002, sum_kzt=87500, n_tx=2)
        svg, root = self.render(graph)
        self.assertEqual(root.attrib["viewBox"], "0 0 780 340")
        self.assertIn("1,25 млн ₸", svg)
        self.assertIn("1 250 000 ₸", svg)
        self.assertIn("87,5 тыс. ₸", svg)
        links = [link.attrib["href"] for link in root.findall("svg:a", NS)]
        self.assertIn("?gid=100000000000000001&section=investigation", links)
        self.assertIn(f"?gid={self.gid}&section=investigation", links)
        edges = root.findall("svg:g[@class='mm-flow-edge']", NS)
        self.assertEqual([(e.attrib["data-src"], e.attrib["data-dst"]) for e in edges], [
            ("100000000000000001", str(self.gid)), (str(self.gid), "100000000000000002")])

    def test_rank_caps_and_mutual_edges(self):
        graph = nx.DiGraph()
        for node in range(1, 7):
            graph.add_edge(node, self.gid, sum_kzt=node * 10)
            graph.add_edge(self.gid, node, sum_kzt=node * 20)
        # Edges between counterparties must not be shown in this excerpt.
        graph.add_edge(6, 5, sum_kzt=999999999)
        _, root = self.render(graph)
        edges = root.findall("svg:g[@class='mm-flow-edge']", NS)
        incoming = [e.attrib["data-src"] for e in edges if e.attrib["data-dst"] == str(self.gid)]
        outgoing = [e.attrib["data-dst"] for e in edges if e.attrib["data-src"] == str(self.gid)]
        self.assertEqual(incoming, ["6", "5", "4"])
        self.assertEqual(outgoing, ["6", "5", "4", "3"])
        self.assertEqual(len(edges), 7)

    def test_self_loop_shown_once_without_fake_counterparty(self):
        graph = nx.DiGraph()
        graph.add_edge(self.gid, self.gid, sum_kzt=5000)
        svg, root = self.render(graph)
        self.assertEqual(len(root.findall("svg:g[@class='mm-flow-self']", NS)), 1)
        self.assertEqual(len(root.findall("svg:g[@class='mm-flow-edge']", NS)), 0)
        self.assertEqual(len(root.findall("svg:a", NS)), 1)
        self.assertIn("5 тыс. ₸", svg)

    def test_isolated_source_and_sink(self):
        graph = nx.DiGraph()
        graph.add_node(self.gid)
        svg, root = self.render(graph)
        self.assertIn("нет наблюдаемых переводов", svg)
        self.assertEqual(len(root.findall("svg:path", NS)), 0)
        graph.add_edge(self.gid, 1, sum_kzt=10000)
        svg, _ = self.render(graph)
        self.assertIn("Нет входящих в выгрузке", svg)
        self.assertNotIn("Нет исходящих в выгрузке", svg)
        svg, _ = self.render(graph.reverse(copy=True))
        self.assertNotIn("Нет входящих в выгрузке", svg)
        self.assertIn("Нет исходящих в выгрузке", svg)

    def test_dynamic_text_is_escaped(self):
        graph = nx.DiGraph()
        graph.add_edge(1, self.gid, sum_kzt=50, n_tx='<script>alert("x")</script>')
        roles = self.roles(graph)
        roles.at[self.gid, "role"] = '<script>alert("x")</script>'
        svg, root = self.render(graph, roles)
        self.assertNotIn("<script>", svg)
        self.assertIn("&lt;script&gt;", svg)
        self.assertEqual(len(root.findall(".//svg:script", NS)), 0)

    def test_missing_node_is_explicit_error(self):
        with self.assertRaisesRegex(ValueError, "not in the graph"):
            render_flow_svg(nx.DiGraph(), pd.DataFrame(), self.gid)

    def test_missing_amount_is_not_displayed_as_zero(self):
        graph = nx.DiGraph()
        graph.add_edge(1, self.gid)
        svg, _ = self.render(graph)
        self.assertIn("Сумма не указана", svg)
        self.assertNotIn("0 ₸", svg)

    def test_html_embeds_svg_image_and_full_id_navigation(self):
        graph = nx.DiGraph()
        source, destination = 100000000000000001, 100000000000000002
        graph.add_edge(source, self.gid, sum_kzt=1250000)
        graph.add_edge(self.gid, destination, sum_kzt=87500)
        roles = self.roles(graph)
        html = render_flow_html(graph, roles, self.gid)
        root = ET.fromstring(html)
        self.assertEqual(root.attrib["class"], "mm-flow-interactive")
        self.assertIn("aspect-ratio:780 / 340", root.attrib["style"])
        image = root.find("img")
        self.assertEqual(image.attrib["class"], "mm-flow-image")
        self.assertTrue(image.attrib["src"].startswith("data:image/svg+xml;base64,"))
        decoded = b64decode(image.attrib["src"].split(",", 1)[1]).decode()
        self.assertEqual(decoded, render_flow_svg(graph, roles, self.gid))
        self.assertNotIn("<svg", html)
        links = root.findall("a")
        self.assertEqual([link.attrib["href"] for link in links], [
            f"?gid={source}&section=investigation",
            f"?gid={destination}&section=investigation",
            f"?gid={self.gid}&section=investigation",
        ])
        for node, link in zip((source, destination, self.gid), links):
            self.assertEqual(link.attrib["target"], "_self")
            self.assertIn(str(node), link.attrib["title"])
            self.assertIn(str(node), link.attrib["aria-label"])
            self.assertIn("position:absolute", link.attrib["style"])
        self.assertIn("Координатор", links[-1].attrib["title"])

    def test_html_targets_share_ranking_and_do_not_duplicate_self_loop(self):
        graph = nx.DiGraph()
        for node in range(1, 7):
            graph.add_edge(node, self.gid, sum_kzt=node * 10)
            graph.add_edge(self.gid, node, sum_kzt=node * 20)
        graph.add_edge(self.gid, self.gid, sum_kzt=99999999)
        root = ET.fromstring(render_flow_html(graph, self.roles(graph), self.gid))
        links = root.findall("a")
        self.assertEqual([link.attrib["data-node-gid"] for link in links], ["6", "5", "4", "6", "5", "4", "3", str(self.gid)])
        self.assertEqual(sum(link.attrib["data-node-gid"] == str(self.gid) for link in links), 1)

    def test_html_overlay_titles_escape_untrusted_text(self):
        graph = nx.DiGraph()
        graph.add_node(self.gid)
        roles = self.roles(graph)
        roles.at[self.gid, "role"] = '\"><script>alert("x")</script>'
        html = render_flow_html(graph, roles, self.gid)
        root = ET.fromstring(html)
        self.assertNotIn("<script>", html)
        self.assertNotIn("onclick=", html)
        self.assertEqual(len(root.findall("a")), 1)
        self.assertIn('<script>', root.find("a").attrib["title"])


if __name__ == "__main__":
    unittest.main()
