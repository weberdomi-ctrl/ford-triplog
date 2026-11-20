"""Beta 6 R2 regression tests: real-world-style vehicle expense receipts."""
import importlib.util
from pathlib import Path
import unittest

MODULE = Path(__file__).resolve().parents[1] / "custom_components" / "ford_triplog" / "expense_receipt_parser.py"
SPEC = importlib.util.spec_from_file_location("expense_receipt_parser", MODULE)
PARSER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(PARSER)
extract = PARSER.extract_expense_fields
compare = PARSER.compare_receipt_registration


class VehicleExpenseReceiptTests(unittest.TestCase):
    def test_swiss_tyre_invoice_all_fields(self):
        # Synthetic, privacy-safe copy of the form/layout used for field testing.
        receipt = (
            "RECHNUNG\n"
            "Garage Muster AG - Werkstrasse 47 - CH-8640 Rapperswil\n"
            "Herr\nKunde Muster\n"
            "Rechnungsdatum: 31.10.2026\nFAHRZEUGANGABEN\n"
            "Marke/Modell: JAC E30X Electric\n"
            "Fahrgestell-Nr.: ABCDEFGHIJKLM1234\n"
            "Kontrollschild: SZ 47118\n"
            "Km-Stand: 12’619 km\n"
            "Reparaturdatum: 31.10.2026\n"
            "BEZEICHNUNG MENGE PREIS ANT. TOTAL\n"
            "4 Reifen wechseln und auswuchten eingelagert\n"
            "Reifeneinlagerung 6 Mt. 11.56 69.36\n"
            "Betrag exkl. MwSt. 185.01\n"
            "3) Normalsatz 185.01 8.1 % 14.99\n"
            "Betrag inkl. MwSt. 200.00\n"
            "Zu bezahlender Betrag 200.00\n"
            "Alle Beträge in CHF\n"
        )
        result = extract(receipt, "maintenance")
        self.assertEqual(result["amount"], "200.00")
        self.assertEqual(result["expense_date"], "2026-10-31")
        self.assertEqual(result["currency"], "CHF")
        self.assertEqual(result["provider"], "Garage Muster AG")
        self.assertEqual(result["country"], "CH")
        self.assertEqual(result["odometer_km"], "12619")
        self.assertEqual(result["category"], "tires")
        self.assertEqual(result["description"], "Reifenwechsel, Auswuchten und Reifeneinlagerung")
        self.assertEqual(result["receipt_registration"], "SZ 47118")
        self.assertEqual(result["receipt_vehicle_model"], "JAC E30X Electric")

    def test_registration_match_ignores_spacing_and_hyphens(self):
        self.assertEqual(compare("SZ 47118", "sz-47118"), "match")
        self.assertEqual(compare("SZ 47118", "ZH 47118"), "mismatch")
        self.assertEqual(compare("SZ 47118", None), "unverified")
        self.assertEqual(compare(None, "SZ 47118"), "not_found")

    def test_no_country_from_chf_or_swiss_plates(self):
        receipt = "Werkstatt Test GmbH\nKontrollschild: SZ 47118\nTotal CHF 90.00"
        result = extract(receipt, "maintenance")
        self.assertNotIn("country", result)
        self.assertEqual(result["receipt_registration"], "SZ 47118")

    def test_de_merchant_country_not_vehicle_nationality(self):
        receipt = (
            "Autowerk GmbH - Werkstrasse 21 - DE-10115 Berlin\n"
            "Kennzeichen: SZ 12345\nKm-Stand: 20.123 km\n"
            "Rechnungsdatum: 06.11.2026\n"
            "Service und Inspektion\nRechnungsbetrag EUR 120,00"
        )
        result = extract(receipt, "maintenance")
        self.assertEqual(result["country"], "DE")
        self.assertEqual(result["category"], "service")
        self.assertEqual(result["odometer_km"], "20123")
        self.assertEqual(result["description"], "Service / Wartung")
        self.assertEqual(result["amount"], "120.00")

    def test_reparaturdatum_not_assumed_repair(self):
        receipt = "Garage Muster AG\nReparaturdatum: 01.11.2026\nTotal CHF 100.00"
        result = extract(receipt, "maintenance")
        self.assertNotIn("category", result)
        self.assertNotIn("description", result)

    def test_category_is_limited_to_selected_group(self):
        receipt = "Mautstelle Schweiz\nVignette 2027\nTotal CHF 40.00"
        self.assertEqual(extract(receipt, "toll")["category"], "vignette")
        self.assertNotIn("category", extract(receipt, "maintenance"))

    def test_no_expense_is_booked_by_parser(self):
        receipt = "Garage Muster AG - Werkstrasse 1 - CH-8000 Zürich\n"
        result = extract(receipt + "Kontrollschild: ZH 22222\nTotal CHF 45.00", "maintenance")
        self.assertNotIn("expense_id", result)
        self.assertNotIn("expense_group", result)

    def test_zero_and_large_odometer_are_not_inferred_from_invoice_number(self):
        result = extract("Garage Muster AG\nRechnungsnummer: 63193\nTotal CHF 99.90", "maintenance")
        self.assertNotIn("odometer_km", result)


if __name__ == "__main__":
    unittest.main()
