"""Pure-python tests for Beta 6 R1 expense PDF/OCR suggestion parser."""
import importlib.util
from pathlib import Path
import unittest

MODULE = Path(__file__).resolve().parents[1] / "custom_components" / "ford_triplog" / "expense_receipt_parser.py"
SPEC = importlib.util.spec_from_file_location("expense_receipt_parser", MODULE)
PARSER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(PARSER)
extract = PARSER.extract_expense_fields


class ExpenseReceiptTests(unittest.TestCase):
    def test_swiss_service_invoice_with_net_vat_and_total(self):
        result = extract("Garage Muster AG\nRechnungsdatum 05.11.2026\n"
                         "Netto CHF 450.00\nMWST CHF 36.45\nRechnungsbetrag CHF 486.45")
        self.assertEqual(result["amount"], "486.45")
        self.assertEqual(result["expense_date"], "2026-11-05")
        self.assertEqual(result["currency"], "CHF")
        self.assertEqual(result["provider"], "Garage Muster AG")

    def test_euro_amount_with_german_grouping(self):
        result = extract("Autohaus Test GmbH\nRechnungsdatum: 02.11.2026\n"
                         "Zwischensumme 1.020,00\nZahlbetrag 1.219,88 EUR")
        self.assertEqual(result["amount"], "1219.88")
        self.assertEqual(result["currency"], "EUR")

    def test_swiss_apostrophe_and_zero_cents(self):
        result = extract("Verkehrsamt\nDatum: 06.11.2026\nTotal CHF 1'234.–")
        self.assertEqual(result["amount"], "1234.00")

    def test_chooses_invoice_date_not_due_date(self):
        result = extract("Invoice\nDue date: 30.11.2026\nInvoice Date: 06.11.2026\nTotal USD 75.20")
        self.assertEqual(result["expense_date"], "2026-11-06")

    def test_total_from_next_line(self):
        result = extract("Rechnung\nRechnungsdatum 06.11.2026\nTotal\nCHF 82.50")
        self.assertEqual(result["amount"], "82.50")

    def test_no_total_rejects_ambiguous_costs(self):
        result = extract("Netto CHF 200.00\nMWST CHF 16.20\nBrutto ohne Totalangabe")
        self.assertNotIn("amount", result)

    def test_blank_scan(self):
        self.assertEqual(extract("  "), {})

    def test_no_automatic_booking_data(self):
        result = extract("Garage Muster AG\nTotal CHF 345.00")
        self.assertEqual(result["amount"], "345.00")
        self.assertNotIn("expense_id", result)
        self.assertNotIn("expense_group", result)
        self.assertNotIn("category", result)


if __name__ == "__main__":
    unittest.main()
