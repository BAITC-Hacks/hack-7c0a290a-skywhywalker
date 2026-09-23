"""Run from repo root: python -m unittest discover -s tests -v.

Requires the supplied parquet files in data/. Missing CSV outputs are generated
by the application, just as on a first normal launch. No API call is made.
"""
from pathlib import Path
import unittest

from streamlit.testing.v1 import AppTest


ROOT = Path(__file__).resolve().parents[1]


class WorkspaceTests(unittest.TestCase):
    def app(self):
        app = AppTest.from_file(str(ROOT / "app.py"), default_timeout=30).run()
        self.assertEqual(len(app.exception), 0)
        return app

    def assert_clean(self, app):
        self.assertEqual(len(app.exception), 0, str(app.exception))

    def test_overview_and_primary_action(self):
        app = self.app()
        html = app.get("html")[0].proto.body
        self.assertIn("Кого проверить следующим?", html)
        self.assertEqual(html.count('class="mm-stat"'), 4)
        gid = app.sidebar.text_input[0].value
        self.assertIn(f'section=investigation&amp;gid={gid}', html)
        app.query_params["section"] = "investigation"
        app.query_params["gid"] = gid
        app.run()
        self.assert_clean(app)
        self.assertEqual(app.sidebar.radio[0].value, "Расследование")
        self.assertEqual(app.title[0].value, "Связи и основания")
        for density in (9, 33, 65):
            app.selectbox[0].set_value(density).run()
            self.assert_clean(app)
        app.radio[0].set_value(2).run()
        self.assert_clean(app)

    def test_each_section(self):
        app = self.app()
        for section in ("Приоритеты", "Кластеры", "Методика", "Обзор"):
            app.sidebar.radio[0].set_value(section).run()
            self.assert_clean(app)

    def test_candidates_and_orphan(self):
        app = self.app()
        import pandas as pd
        top = pd.read_csv(ROOT / "out" / "top_nodes.csv", dtype={"gid": str})
        gid = top.iloc[1].gid
        self.assertIn(f'aria-label="Изучить узел {gid}"', app.get("html")[0].proto.body)
        app.query_params["section"] = "investigation"
        app.query_params["gid"] = gid
        app.run()
        self.assert_clean(app)
        self.assertEqual(app.sidebar.text_input[0].value, gid)
        # Find real edge cases from outputs instead of hardcoding a GID.
        roles = pd.read_csv(ROOT / "out" / "nodes_roles.csv", dtype={"gid": str})
        orphan = roles[(roles.in_deg == 0) & (roles.out_deg == 0)].iloc[0]
        app.sidebar.text_input[0].set_value(orphan.gid).run()
        self.assert_clean(app)
        self.assertTrue(any("нет наблюдаемых" in info.value for info in app.info))
        truncated = roles[roles.truncated_by_depth].iloc[0]
        app.sidebar.text_input[0].set_value(truncated.gid).run()
        self.assert_clean(app)
        self.assertTrue(any("обрезаны" in warning.value for warning in app.warning))


if __name__ == "__main__":
    unittest.main()
