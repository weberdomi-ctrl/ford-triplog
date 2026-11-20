"""Beta 7 R6: shared UI ownership is not tied to vehicle_id == 1.

No Home Assistant runtime required:
  python -m unittest discover -s test -p 'test_shared_entities_owner_beta7_r6.py' -v
"""
import ast
from pathlib import Path
from types import SimpleNamespace
import unittest

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "custom_components" / "ford_triplog"
CONTEXT = (SRC / "vehicle_context.py").read_text(encoding="utf-8")
TREE = ast.parse(CONTEXT)

HELPERS = {
    "_domain_data", "iter_vehicle_runtimes",
    "is_shared_entities_owner", "release_shared_entities_owner",
    "consume_unloaded_shared_entities_owner",
}
CONSTANTS = {
    "SHARED_ENTITIES_OWNER_KEY", "SHARED_ENTITIES_UNLOADED_KEY",
}
nodes = []
for node in TREE.body:
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        if node.name in HELPERS:
            nodes.append(node)
    elif isinstance(node, ast.Assign):
        if any(isinstance(target, ast.Name) and target.id in CONSTANTS
               for target in node.targets):
            nodes.append(node)

namespace = {"DOMAIN": "ford_triplog", "HomeAssistant": object, "Any": object}
exec(compile(ast.Module(body=nodes, type_ignores=[]),
             "<shared owner helpers>", "exec"), namespace)

claim = namespace["is_shared_entities_owner"]
release = namespace["release_shared_entities_owner"]
consume = namespace["consume_unloaded_shared_entities_owner"]
OWNER_KEY = namespace["SHARED_ENTITIES_OWNER_KEY"]


def hass_with(*items):
    return SimpleNamespace(data={
        "ford_triplog": {
            entry: {"vehicle_id": vehicle}
            for entry, vehicle in items
        }
    })


class SharedEntitiesOwnerR6Tests(unittest.TestCase):

    def test_fresh_single_vehicle_id_two_owns_all_shared_entities(self):
        hass = hass_with(("explorer", 2))
        self.assertTrue(claim(hass, "explorer"))
        self.assertTrue(claim(hass, "explorer"))
        self.assertEqual(hass.data["ford_triplog"][OWNER_KEY], "explorer")

    def test_first_loaded_vehicle_one_keeps_legacy_ownership(self):
        hass = hass_with(("extra", 3), ("legacy", 1))
        self.assertFalse(claim(hass, "extra"))
        self.assertTrue(claim(hass, "legacy"))
        self.assertEqual(hass.data["ford_triplog"][OWNER_KEY], "legacy")

    def test_multi_vehicle_without_id_one_elects_lowest_loaded(self):
        hass = hass_with(("jac", 5), ("explorer", 2), ("test", 7))
        self.assertFalse(claim(hass, "jac"))
        self.assertTrue(claim(hass, "explorer"))
        self.assertFalse(claim(hass, "test"))

    def test_owner_does_not_change_when_another_runtime_loads(self):
        hass = hass_with(("ford", 2))
        self.assertTrue(claim(hass, "ford"))
        hass.data["ford_triplog"]["legacy"] = {"vehicle_id": 1}
        self.assertTrue(claim(hass, "ford"))
        self.assertFalse(claim(hass, "legacy"))

    def test_unload_releases_owner_without_touching_vehicle_data(self):
        hass = hass_with(("ford", 2), ("second", 5))
        self.assertTrue(claim(hass, "ford"))
        self.assertTrue(release(hass, "ford"))
        self.assertNotIn(OWNER_KEY, hass.data["ford_triplog"])
        self.assertTrue(consume(hass, "ford"))
        self.assertFalse(consume(hass, "ford"))
        hass.data["ford_triplog"].pop("ford")
        self.assertTrue(claim(hass, "second"))
        self.assertEqual(hass.data["ford_triplog"]["second"]["vehicle_id"], 5)

    def test_non_owner_unload_must_not_trigger_takeover(self):
        hass = hass_with(("ford", 2), ("jac", 3))
        self.assertTrue(claim(hass, "ford"))
        self.assertFalse(release(hass, "jac"))
        self.assertFalse(consume(hass, "jac"))
        self.assertEqual(hass.data["ford_triplog"][OWNER_KEY], "ford")

    def test_options_reload_reclaims_without_permanent_removal(self):
        hass = hass_with(("ford", 2), ("jac", 5))
        self.assertTrue(claim(hass, "ford"))
        self.assertTrue(release(hass, "ford"))
        self.assertTrue(claim(hass, "ford"))
        self.assertFalse(consume(hass, "ford"))

    def test_never_claims_unloaded_entry_or_empty_runtime(self):
        hass = hass_with(("ford", 2))
        self.assertFalse(claim(hass, "missing"))
        hass.data["ford_triplog"].pop("ford")
        self.assertFalse(claim(hass, "ford"))

    def test_all_shared_platforms_use_the_same_owner_guard(self):
        for filename in ("sensor.py", "binary_sensor.py", "select.py"):
            source = (SRC / filename).read_text(encoding="utf-8")
            tree = ast.parse(source)
            setup = next(node for node in tree.body
                         if isinstance(node, ast.AsyncFunctionDef)
                         and node.name == "async_setup_entry")
            calls = [node for node in ast.walk(setup)
                     if isinstance(node, ast.Call)
                     and isinstance(node.func, ast.Name)
                     and node.func.id == "is_shared_entities_owner"]
            self.assertEqual(len(calls), 1, filename)
            self.assertNotIn("if vehicle_id != 1:", source, filename)

    def test_owner_release_and_permanent_removal_rehome_are_wired(self):
        integration = (SRC / "__init__.py").read_text(encoding="utf-8")
        self.assertIn("release_shared_entities_owner(hass, entry.entry_id)",
                      integration)
        self.assertIn("consume_unloaded_shared_entities_owner(hass, entry.entry_id)",
                      integration)
        self.assertIn("await hass.config_entries.async_reload(successor_id)",
                      integration)

    def test_tco_units_follow_contract_currency_in_beta_seven(self):
        source = (SRC / "sensor.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        functions = [
            node for node in tree.body if isinstance(node, ast.FunctionDef)
            and node.name in {"_tco_currency", "_tco_month_unit"}
        ]
        currency_ns = {"Any": object}
        exec(compile(ast.Module(body=functions, type_ignores=[]),
                     "<tco currency helpers>", "exec"), currency_ns)
        self.assertEqual(currency_ns["_tco_month_unit"](
            currency_ns["_tco_currency"]("eur")), "EUR/month")
        self.assertEqual(currency_ns["_tco_month_unit"](
            currency_ns["_tco_currency"]("CHF")), "CHF/month")
        for klass in ("FordTriplogInsuranceTCOSensor",
                      "FordTriplogRoadTaxTCOSensor",
                      "FordTriplogFinancingTCOSensor"):
            node = next(node for node in tree.body
                        if isinstance(node, ast.ClassDef) and node.name == klass)
            self.assertIn("_attr_native_unit_of_measurement", ast.unparse(node))
        self.assertNotIn('"CHF/month"', source)
        self.assertIn('"status": "no_active_policy"', source)
        self.assertIn('"status": "no_active_tax"', source)


if __name__ == "__main__":
    unittest.main()
