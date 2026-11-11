"""Beta 7 R7 regression: end physical plug session at unplug, not COMPLETED.

Run: python -m unittest discover -s test -p 'test_plug_out_charge_end_beta7_r7.py' -v
The coordinator's actual methods are extracted via AST to run without Home Assistant.
"""
import ast
import asyncio
from datetime import datetime, timedelta, timezone
import logging
from pathlib import Path
from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase, TestCase
from unittest.mock import AsyncMock, Mock

ROOT = Path(__file__).resolve().parents[1]
SOURCE = (ROOT / "custom_components/ford_triplog/coordinator.py").read_text(
    encoding="utf-8"
)
TREE = ast.parse(SOURCE)
COORD = next(n for n in TREE.body if isinstance(n, ast.ClassDef)
             and n.name == "FordTriplogCoordinator")

END = datetime(2026, 11, 10, 5, 38, 16, tzinfo=timezone.utc)
COMPLETED = datetime(2026, 11, 10, 3, 20, 47, tzinfo=timezone.utc)
START = datetime(2026, 11, 9, 16, 25, 42, tzinfo=timezone.utc)


class FakeDtUtil:
    UTC = timezone.utc

    @staticmethod
    def now():
        return END

    @staticmethod
    def parse_datetime(value):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except (TypeError, ValueError):
            return None


names = {
    "finish_charge", "_snapshot_attribute", "_parse_fordpass_datetime",
    "_fordpass_snapshot_times", "_last_charge_matches_current_charge",
}
methods = [n for n in COORD.body
           if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
           and n.name in names]
sandbox = {
    "dt_util": FakeDtUtil,
    "optional_float": lambda v: float(v) if v is not None else None,
    "timedelta": timedelta,
    "_LOGGER": logging.getLogger("ford_triplog_r7_tests"),
}
namespace = dict(sandbox)
module = ast.Module(
    body=[ast.ClassDef(name="MethodsUnderTest", bases=[], keywords=[],
                       body=methods, decorator_list=[])],
    type_ignores=[],
)
exec(compile(module, "<coordinator R7 methods>", "exec"), namespace)
MethodsUnderTest = namespace["MethodsUnderTest"]


class FakeCharge:
    def __init__(self, completion=COMPLETED):
        self.charge_id = "20261109T172542"
        self.pause_started_at = None
        self.pause_duration_seconds = 0.0
        self.completion_time = completion.isoformat() if completion else None
        self.completion_soc = 80
        self.last_live_charging_soc = 80
        self.charging_type = "AC_BASIC"
        self.charger_energy_output_kwh = 0.5
        self.end_time = None
        self.detected_end_time = None
        self.start_time = START.isoformat()
        self.last_charge_baseline_signature = "previous"
        self.fordpass_pending = False

    def finish(self, *, soc, latitude, longitude, address):
        self.end_time = END.isoformat()
        self.detected_end_time = self.end_time
        self.end_soc = soc

    def to_dict(self):
        return {
            "end_time": self.end_time,
            "detected_end_time": self.detected_end_time,
            "completion_time": self.completion_time,
        }


def fake_coordinator(*, plug_entity="sensor.fordpass_example_elvehplug",
                     completion=COMPLETED):
    c = MethodsUnderTest()
    c._charge_lock = asyncio.Lock()
    c.current_charge = FakeCharge(completion)
    c.plug_entity = plug_entity
    c.last_charge_entity = "sensor.fordpass_example_energytransferlogentry"
    c.waiting_for_last_charge = False
    c._parse_fordpass_datetime = Mock(side_effect=FakeDtUtil.parse_datetime)
    c._cancel_charge_start_soc_recheck = Mock()
    c._read_vehicle_state = Mock(return_value={
        "charging": "NOT_PLUGGED_IN", "charging_soc": 80, "soc": 80,
        "latitude": 47.1, "longitude": 8.9,
    })
    c._capture_charging_completion_snapshot = Mock(return_value=False)
    c._finish_external_meter = Mock()
    c._finish_dynamic_price = Mock()
    c._wait_for_stable_vehicle_state = AsyncMock(
        return_value=c._read_vehicle_state.return_value)
    c._get_address = AsyncMock(return_value={})
    c.storage = SimpleNamespace(save_current_charge=AsyncMock())
    c._start_waiting_for_last_charge = Mock()
    c._finalize_charge = AsyncMock()
    return c


FORD_LAST_CHARGE = {
    "attributes": {
        "energyTransferDuration": {
            "begin": "2026-11-09T16:25:28Z",
            "end": "2026-11-10T05:38:14Z",
            "totalTime": 16706,
        },
        "plugDetails": {
            "plugInTime": "2026-11-09T16:25:28Z",
            "plugOutTime": "2026-11-10T05:38:14Z",
        },
        "stateOfCharge": {"firstSOC": 19, "lastSOC": 80},
        "energyConsumed": 46.0,
        "timeStamp": "2026-11-10T05:39:17Z",
    },
}


class PlugOutTimestampTests(IsolatedAsyncioTestCase):
    async def test_plug_aware_session_ends_at_physical_unplug(self):
        c = fake_coordinator()
        await c.finish_charge()
        charge = c.current_charge
        self.assertEqual(charge.end_time, END.isoformat())
        self.assertEqual(charge.detected_end_time, END.isoformat())
        self.assertEqual(charge.completion_time, COMPLETED.isoformat())
        c.storage.save_current_charge.assert_awaited_once()
        self.assertEqual(
            c.storage.save_current_charge.await_args.args[0]["end_time"],
            END.isoformat(),
        )
        c._start_waiting_for_last_charge.assert_called_once()

    async def test_legacy_non_plug_source_keeps_completion_end(self):
        c = fake_coordinator(plug_entity=None)
        await c.finish_charge()
        charge = c.current_charge
        self.assertEqual(charge.end_time, COMPLETED.isoformat())
        self.assertEqual(charge.detected_end_time, COMPLETED.isoformat())

    async def test_plug_aware_without_completion_uses_unplug_end(self):
        c = fake_coordinator(completion=None)
        await c.finish_charge()
        self.assertEqual(c.current_charge.end_time, END.isoformat())


class FordPassMatchingTests(TestCase):
    def test_november_tenth_ford_last_charge_matches_unplug_time(self):
        c = MethodsUnderTest()
        c.current_charge = FakeCharge()
        c.current_charge.end_time = END.isoformat()
        c.last_charge_signature = "new"
        c.current_charge.last_charge_baseline_signature = "old"
        self.assertTrue(c._last_charge_matches_current_charge(
            FORD_LAST_CHARGE
        ))
        # The old bug incorrectly used the energy-transfer completion time.
        c.current_charge.end_time = COMPLETED.isoformat()
        self.assertFalse(c._last_charge_matches_current_charge(
            FORD_LAST_CHARGE
        ))

    def test_ford_timestamp_selection_uses_reported_unplug_with_reference(self):
        start, end = MethodsUnderTest._fordpass_snapshot_times(
            FORD_LAST_CHARGE, reference_end=END,
        )
        self.assertEqual(
            start, datetime(2026, 11, 9, 16, 25, 28, tzinfo=timezone.utc))
        self.assertEqual(
            end, datetime(2026, 11, 10, 5, 38, 14, tzinfo=timezone.utc))
