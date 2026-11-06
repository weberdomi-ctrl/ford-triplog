"""Beta 6 R4: expense form controls and translations remain consistent."""
from __future__ import annotations

import ast
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1] / "custom_components" / "ford_triplog"
SOURCE = (ROOT / "config_flow.py").read_text(encoding="utf-8")
AST = ast.parse(SOURCE)


def method_code(name: str) -> str:
    funcs = [
        node
        for node in ast.walk(AST)
        if isinstance(node, ast.AsyncFunctionDef) and node.name == name
    ]
    if len(funcs) != 1:
        raise AssertionError(f"Expected exactly one {name}, got {len(funcs)}")
    return ast.get_source_segment(SOURCE, funcs[0]) or ""


class ExpenseDialogR4Tests(unittest.TestCase):
    def test_edit_delete_use_new_explicit_selector_key(self):
        for name in ("async_step_expense_edit", "async_step_expense_delete"):
            with self.subTest(step=name):
                code = method_code(name)
                self.assertIn('vol.Required("expense_selection")', code)
                self.assertIn('user_input["expense_selection"]', code)
                self.assertNotIn('vol.Required("expense_id")', code)
                self.assertIn("format_expense_choice", code)
                self.assertIn("expense_sort_key", code)

    def test_receipt_check_visible_once_without_useless_radio(self):
        code = method_code("async_step_expense_form")
        self.assertNotIn("receipt_vehicle_status", code)
        self.assertIn('description_placeholders={"vehicle_check": check_text}', code)
        self.assertIn('if vehicle_check == "mismatch":', code)
        self.assertIn('"confirm_receipt_vehicle"', code)
        self.assertIn("expense_vehicle_mismatch_unconfirmed", code)
        self.assertIn("Kein Kontrollschild auf dem Beleg erkannt", code)

    def test_translations_use_new_select_key_and_no_status_radio(self):
        for filename in ("strings.json", "translations/de.json", "translations/en.json", "translations/pl.json"):
            with self.subTest(filename=filename):
                data = json.loads((ROOT / filename).read_text(encoding="utf-8"))
                steps = data["options"]["step"]
                for name in ("expense_edit", "expense_delete"):
                    self.assertTrue(steps[name]["data"].get("expense_selection"))
                    self.assertNotIn("expense_id", steps[name]["data"])
                self.assertNotIn("receipt_vehicle_status", steps["expense_form"]["data"])

    def test_version_matches_build(self):
        version = json.loads((ROOT / "manifest.json").read_text(encoding="utf-8"))["version"]
        constants = (ROOT / "const.py").read_text(encoding="utf-8")
        self.assertEqual(version, "2.7.0-beta.6-r4")
        self.assertIn('VERSION: Final = "2.7.0-beta.6-r4"', constants)
        self.assertIn('BUILD: Final = "27026"', constants)


if __name__ == "__main__":
    unittest.main()
