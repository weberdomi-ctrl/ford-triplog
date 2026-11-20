"""R3 regression tests for native Home Assistant expense dialog presentation."""
from __future__ import annotations

import importlib.util
from pathlib import Path
import unittest

HELPER = Path(__file__).resolve().parents[1] / "custom_components" / "ford_triplog" / "expense_dialog.py"
spec = importlib.util.spec_from_file_location("expense_dialog", HELPER)
dialogs = importlib.util.module_from_spec(spec)
spec.loader.exec_module(dialogs)


class ExpenseDialogTests(unittest.TestCase):
    def test_sorted_newest_first_with_year_fallback(self):
        items = [
            {"expense_id": 1, "expense_date": "2025-10-04"},
            {"expense_id": 2, "expense_date": "2026-04-24"},
            {"expense_id": 3, "expense_date": "2026-10-31"},
            {"expense_id": 4, "expense_year": "2024"},
            {"expense_id": 5, "expense_date": "2026-10-31"},
        ]
        ordered = sorted(items, key=dialogs.expense_sort_key, reverse=True)
        self.assertEqual([x["expense_id"] for x in ordered], [5, 3, 2, 1, 4])

    def test_choice_renders_local_date_amount_category_and_provider(self):
        expense = {
            "expense_id": 4, "expense_date": "2026-10-31",
            "category": "tires", "amount": 200, "currency": "CHF",
            "provider": "Garage Muster AG",
        }
        label = dialogs.format_expense_choice(expense, "maintenance", "de-CH")
        self.assertEqual(label, "31.10.2026 · CHF 200.00 · Reifen / Räder · Garage Muster AG")
        self.assertNotIn("tires", label)
        self.assertIn("Tyres / wheels", dialogs.format_expense_choice(expense, "maintenance", "en"))

    def test_falls_back_for_year_only_unknown_category_and_bad_numbers(self):
        expense = {"expense_year": "2025", "amount": "unknown", "category": "custom"}
        result = dialogs.format_expense_choice(expense, "other", "de")
        self.assertTrue(result.startswith("2025 · CHF — · custom"))
        self.assertEqual(dialogs.expense_sort_key({"expense_year": "invalid"}), ("0000-01-01", 0))

    def test_receipt_match_mismatch_missing_and_unverified(self):
        match = dialogs.vehicle_check_label("match", "SZ 12345", "SZ 12345", "JAC E30X", "de")
        self.assertIn("stimmt überein", match)
        self.assertIn("JAC E30X", match)
        mismatch = dialogs.vehicle_check_label("mismatch", "SZ 12345", "ZH 999", "", "de")
        self.assertIn("Bestätigung nötig", mismatch)
        self.assertIn("ZH 999", mismatch)
        self.assertIn("kein Kennzeichen", dialogs.vehicle_check_label("unverified", "SZ 12345", "", "", "de"))
        self.assertIn("Kein Kontrollschild", dialogs.vehicle_check_label("not_found", "", "", "", "de"))


if __name__ == "__main__":
    unittest.main()
