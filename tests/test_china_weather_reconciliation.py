"""Unit tests for pure China Weather reconciliation primitives."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import FrozenInstanceError
import importlib.util
import json
from pathlib import Path
import sys
import types
from typing import Any, TypeVar
import unittest


_MODULE_PATH = (
    Path(__file__).resolve().parents[1]
    / "core"
    / "services"
    / "weather"
    / "china_weather_reconciliation.py"
)
_MODULE_SPEC = importlib.util.spec_from_file_location(
    "china_weather_reconciliation_under_test", _MODULE_PATH
)
if _MODULE_SPEC is None or _MODULE_SPEC.loader is None:
    raise RuntimeError("unable to load China Weather reconciliation module")
_RECONCILIATION_MODULE = importlib.util.module_from_spec(_MODULE_SPEC)
sys.modules[_MODULE_SPEC.name] = _RECONCILIATION_MODULE
_MODULE_SPEC.loader.exec_module(_RECONCILIATION_MODULE)

BoundedTTLSet = _RECONCILIATION_MODULE.BoundedTTLSet
WarningReference = _RECONCILIATION_MODULE.WarningReference
WarningSnapshotTracker = _RECONCILIATION_MODULE.WarningSnapshotTracker
build_fan_weather_event_id = _RECONCILIATION_MODULE.build_fan_weather_event_id
parse_warning_detail = _RECONCILIATION_MODULE.parse_warning_detail
parse_warning_index = _RECONCILIATION_MODULE.parse_warning_index
validate_detail_path = _RECONCILIATION_MODULE.validate_detail_path
ChinaWeatherReconciler = getattr(_RECONCILIATION_MODULE, "ChinaWeatherReconciler", None)
resolve_fallback_config = getattr(
    _RECONCILIATION_MODULE, "resolve_fallback_config", None
)


_REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
_TEST_PACKAGE_NAME = "disaster_warning_under_test"


def _install_test_package(name: str, path: Path) -> None:
    package = types.ModuleType(name)
    package.__path__ = [str(path)]
    sys.modules[name] = package


_install_test_package(_TEST_PACKAGE_NAME, _REPOSITORY_ROOT)
_install_test_package(f"{_TEST_PACKAGE_NAME}.core", _REPOSITORY_ROOT / "core")
_install_test_package(
    f"{_TEST_PACKAGE_NAME}.core.parsers", _REPOSITORY_ROOT / "core" / "parsers"
)
_install_test_package(
    f"{_TEST_PACKAGE_NAME}.core.services", _REPOSITORY_ROOT / "core" / "services"
)
_install_test_package(f"{_TEST_PACKAGE_NAME}.utils", _REPOSITORY_ROOT / "utils")


class _NoOpLogger:
    def debug(self, *args: object, **kwargs: object) -> None:
        pass

    def info(self, *args: object, **kwargs: object) -> None:
        pass

    def warning(self, *args: object, **kwargs: object) -> None:
        pass

    def error(self, *args: object, **kwargs: object) -> None:
        pass


_LOGGER_MODULE_NAME = f"{_TEST_PACKAGE_NAME}.utils.plugin_logger"
_LOGGER_MODULE = types.ModuleType(_LOGGER_MODULE_NAME)
_LOGGER_MODULE.plugin_logger = _NoOpLogger()
sys.modules[_LOGGER_MODULE_NAME] = _LOGGER_MODULE

_WEATHER_PARSER_PATH = _REPOSITORY_ROOT / "core" / "parsers" / "weather_parser.py"
_WEATHER_PARSER_MODULE_NAME = f"{_TEST_PACKAGE_NAME}.core.parsers.weather_parser"
_WEATHER_PARSER_SPEC = importlib.util.spec_from_file_location(
    _WEATHER_PARSER_MODULE_NAME, _WEATHER_PARSER_PATH
)
if _WEATHER_PARSER_SPEC is None or _WEATHER_PARSER_SPEC.loader is None:
    raise RuntimeError("unable to load weather parser module")
_WEATHER_PARSER_MODULE = importlib.util.module_from_spec(_WEATHER_PARSER_SPEC)
sys.modules[_WEATHER_PARSER_MODULE_NAME] = _WEATHER_PARSER_MODULE
_WEATHER_PARSER_SPEC.loader.exec_module(_WEATHER_PARSER_MODULE)

WeatherAlarmParser = _WEATHER_PARSER_MODULE.WeatherAlarmParser

WARNING_ID_A = "31000041600000_20260713100000"
WARNING_ID_B = "32000041600000_20260713100500"
REF_A = WarningReference(
    identifier=WARNING_ID_A,
    detail_path="a.html",
    longitude="121.47",
    latitude="31.23",
    title="Shanghai thunderstorm warning",
)
REF_B = WarningReference(
    identifier=WARNING_ID_B,
    detail_path="b.html",
    longitude="118.78",
    latitude="32.04",
    title="Jiangsu rainstorm warning",
)
WARNING_ID_C = "33000041600000_20260713101000"
REF_C = WarningReference(
    identifier=WARNING_ID_C,
    detail_path="c.html",
    longitude="120.15",
    latitude="30.28",
    title="Zhejiang hail warning",
)


def _index_script(*references: WarningReference) -> str:
    rows = [
        [
            "A",
            reference.detail_path,
            reference.longitude,
            reference.latitude,
            reference.identifier,
            "x",
            reference.title,
        ]
        for reference in references
    ]
    return f"var alarminfo={json.dumps({'count': str(len(rows)), 'data': rows})};"


def _detail_script(reference: WarningReference) -> str:
    return "var alarminfo=" + json.dumps(
        {
            "ISSUETIME": "2026-07-13 10:10:00",
            "head": reference.title,
            "ISSUECONTENT": "Expect severe weather.",
            "TYPECODE": "01",
            "LEVELCODE": "02",
            "identifier": reference.identifier,
        }
    )


_FeatureT = TypeVar("_FeatureT", bound=Callable[..., Any])


def _require_feature(
    test_case: unittest.TestCase, value: _FeatureT | None, name: str
) -> _FeatureT:
    if value is None:
        test_case.fail(f"Task 3 feature is missing: {name}")
    return value


class MutableClock:
    """A controllable monotonic-clock stand-in for TTL tests."""

    def __init__(self) -> None:
        self.value = 0.0

    def __call__(self) -> float:
        return self.value


class ChinaWeatherReconciliationTests(unittest.TestCase):
    def test_validate_detail_path_accepts_safe_file_names(self) -> None:
        for path in ("a.html", "warning_20260713.json", "index-01.txt"):
            with self.subTest(path=path):
                self.assertEqual(validate_detail_path(path), path)

    def test_validate_detail_path_rejects_unsafe_and_malformed_inputs(self) -> None:
        unsafe_paths = (
            "https://evil.example/a.html",
            "//evil.example/a.html",
            "/absolute.html",
            "../traversal.html",
            "nested/a.html",
            "nested\\a.html",
            "a.html?query=1",
            "a.html#fragment",
            " leading.html",
            "trailing.html ",
            "\ta.html",
            "\na.html",
            "%2e%2e%2fencoded.html",
            "%2E%2E%2Fencoded.html",
            "",
            " ",
            ".",
            "..",
            None,
            123,
        )

        for path in unsafe_paths:
            with self.subTest(path=path):
                with self.assertRaises(ValueError):
                    validate_detail_path(path)

    def test_fallback_config_defaults_off_and_is_immutable(self) -> None:
        resolver = _require_feature(
            self, resolve_fallback_config, "resolve_fallback_config"
        )

        fallback = resolver({})

        self.assertFalse(fallback.enabled)
        self.assertEqual(fallback.poll_interval_seconds, 180)
        self.assertEqual(fallback.request_timeout_seconds, 15)
        self.assertEqual(fallback.detail_concurrency, 4)
        with self.assertRaises(FrozenInstanceError):
            fallback.enabled = True

    def test_fallback_config_clamps_all_numeric_bounds(self) -> None:
        resolver = _require_feature(
            self, resolve_fallback_config, "resolve_fallback_config"
        )

        below = resolver(
            {
                "weather_alarm_fallback": {
                    "enabled": True,
                    "poll_interval_seconds": 0,
                    "request_timeout_seconds": 0,
                    "detail_concurrency": 0,
                }
            }
        )
        above = resolver(
            {
                "weather_alarm_fallback": {
                    "poll_interval_seconds": 999_999,
                    "request_timeout_seconds": 999_999,
                    "detail_concurrency": 999_999,
                }
            }
        )

        self.assertEqual(
            (
                below.poll_interval_seconds,
                below.request_timeout_seconds,
                below.detail_concurrency,
            ),
            (60, 3, 1),
        )
        self.assertEqual(
            (
                above.poll_interval_seconds,
                above.request_timeout_seconds,
                above.detail_concurrency,
            ),
            (3600, 30, 8),
        )

    def test_weather_parser_configures_dedup_cache_contract(self) -> None:
        cache = WeatherAlarmParser()._processed_weather_ids

        self.assertEqual(cache._ttl_seconds, 86_400)
        self.assertEqual(cache._max_entries, 4_096)

    def test_weather_parser_corrects_conflicting_standard_warning_code(self) -> None:
        parser = WeatherAlarmParser()

        event = parser._parse_data(
            {
                "id": "310000-20260714090800-11B0702",
                "effective": "2026-07-14 09:08:00",
                "title": "某区气象台发布高温黄色预警信号",
                "description": "预计最高气温将超过35摄氏度。",
                "type": "11B07_yellow",
            }
        )

        self.assertIsNotNone(event)
        self.assertEqual(event.metadata["weather_type"], "11B09_yellow")
        self.assertEqual(event.event.metadata["weather_code"], "11B09_yellow")

    def test_weather_parser_normalizes_common_cma_type_codes(self) -> None:
        cases = (
            ("台风", "11B01_yellow", "11B01_yellow"),
            ("暴雨", "11B02_yellow", "11B03_yellow"),
            ("暴雪", "11B03_yellow", "11B04_yellow"),
            ("寒潮", "11B04_yellow", "11B05_yellow"),
            ("大风", "11B05_yellow", "11B06_yellow"),
            ("沙尘暴", "11B06_yellow", "11B07_yellow"),
            ("高温", "11B07_yellow", "11B09_yellow"),
            ("干旱", "11B08_yellow", "11B22_yellow"),
            ("雷电", "11B09_yellow", "11B14_yellow"),
            ("冰雹", "11B10_yellow", "11B15_yellow"),
            ("霜冻", "11B11_yellow", "11B16_yellow"),
            ("大雾", "11B12_yellow", "11B17_yellow"),
            ("霾", "11B13_yellow", "11B19_yellow"),
            ("道路结冰", "11B14_yellow", "11B21_yellow"),
        )

        for index, (warning_type, source_code, expected_code) in enumerate(cases):
            with self.subTest(warning_type=warning_type):
                event = WeatherAlarmParser()._parse_data(
                    {
                        "id": f"310000-2026071409{index:02d}00-{source_code[:5]}02",
                        "effective": "2026-07-14 09:08:00",
                        "title": f"某区气象台发布{warning_type}黄色预警信号",
                        "description": "防御信息。",
                        "type": source_code,
                    }
                )

                self.assertIsNotNone(event)
                self.assertEqual(event.metadata["weather_type"], expected_code)

    def test_weather_parser_prefers_specific_standard_warning_names(self) -> None:
        cases = (
            ("雷雨大风", "11B05_yellow", "11B20_yellow"),
            ("高温中暑", "11B07_yellow", "11B24_yellow"),
            ("低温雨雪冰冻", "11B08_yellow", "11B30_yellow"),
            ("海上雷雨大风", "11B05_yellow", "11B52_yellow"),
        )

        for index, (warning_type, source_code, expected_code) in enumerate(cases):
            with self.subTest(warning_type=warning_type):
                event = WeatherAlarmParser()._parse_data(
                    {
                        "id": f"310000-2026071410{index:02d}00-{source_code[:5]}02",
                        "effective": "2026-07-14 10:00:00",
                        "title": f"某区气象台发布{warning_type}黄色预警信号",
                        "description": "防御信息。",
                        "type": source_code,
                    }
                )

                self.assertIsNotNone(event)
                self.assertEqual(event.metadata["weather_type"], expected_code)

    def test_weather_parser_preserves_unknown_warning_semantics(self) -> None:
        event = WeatherAlarmParser()._parse_data(
            {
                "id": "310000-20260714110000-11B9902",
                "effective": "2026-07-14 11:00:00",
                "title": "某区发布自定义气象风险提示",
                "description": "防御信息。",
                "type": "11B99_yellow",
            }
        )

        self.assertIsNotNone(event)
        self.assertEqual(event.metadata["weather_type"], "11B99_yellow")

    def test_weather_parser_retains_id_after_32_later_events(self) -> None:
        parser = WeatherAlarmParser()
        first_id = "310000-20260713100000-11B0102"

        first_event = parser._parse_data(self._weather_payload(first_id))
        self.assertIsNotNone(first_event)
        self.assertEqual(first_event.id, first_id)
        for offset in range(32):
            later_id = f"{320000 + offset:06d}-20260713110000-11B0102"
            self.assertIsNotNone(parser._parse_data(self._weather_payload(later_id)))

        self.assertIn(first_id, parser._processed_weather_ids)
        self.assertIsNone(parser._parse_data(self._weather_payload(first_id)))

    @staticmethod
    def _weather_payload(event_id: str) -> dict[str, str]:
        return {
            "id": event_id,
            "effective": "2026-07-13 10:00:00",
            "title": "Thunderstorm yellow warning",
            "description": "Expect lightning and strong winds.",
            "type": "11B01_yellow",
        }

    def test_parse_warning_index_skips_malformed_rows(self) -> None:
        script = (
            'var alarminfo={"count":"2","data":['
            '["A","a.html","121.47","31.23","31000041600000_20260713100000",'
            '"x","title"],["bad"]]};'
        )

        references = parse_warning_index(script)

        self.assertEqual(
            [reference.identifier for reference in references], [WARNING_ID_A]
        )
        self.assertEqual(references[0].detail_path, "a.html")
        self.assertEqual(references[0].longitude, "121.47")
        self.assertEqual(references[0].latitude, "31.23")
        self.assertEqual(references[0].title, "title")

    def test_parse_warning_index_rejects_non_index_wrapper(self) -> None:
        script = 'var other={"data":[["A","a.html","1","2","id","x","title"]]};'

        self.assertIsNone(parse_warning_index(script))

    def test_parse_warning_index_keeps_valid_empty_snapshot_distinct(self) -> None:
        script = 'var alarminfo={"count":"0","data":[]};'

        self.assertEqual(parse_warning_index(script), [])

    def test_alarminfo_wrapper_accepts_assignment_whitespace(self) -> None:
        index_script = 'var alarminfo = {"count":"0","data":[]};'
        detail_script = (
            'var   alarminfo\t=  {"TYPECODE":"01","LEVELCODE":"02",'
            f'"identifier":"{WARNING_ID_A}"}};'
        )

        self.assertEqual(parse_warning_index(index_script), [])
        self.assertEqual(
            parse_warning_detail(detail_script, REF_A)["id"],
            "310000-20260713100000-11B0102",
        )

    def test_all_malformed_index_rows_do_not_warm_snapshot_tracker(self) -> None:
        script = 'var alarminfo={"count":"1","data":[["bad"]]};'
        tracker = WarningSnapshotTracker(max_entries=100)

        self.assertEqual(tracker.observe(parse_warning_index(script)), [])
        self.assertEqual(tracker.observe([REF_A]), [])

    def test_parse_warning_index_rejects_overwide_rows(self) -> None:
        script = (
            'var alarminfo={"count":"1","data":['
            '["A","a.html","121.47","31.23","31000041600000_20260713100000",'
            '"x","title","unexpected"]]};'
        )

        self.assertIsNone(parse_warning_index(script))

    def test_failed_index_parse_does_not_warm_snapshot_tracker(self) -> None:
        tracker = WarningSnapshotTracker(max_entries=100)

        self.assertEqual(tracker.observe(parse_warning_index("not a CMA index")), [])
        self.assertEqual(tracker.observe([REF_A]), [])

    def test_parse_warning_detail_accepts_unterminated_fan_payload(self) -> None:
        script = (
            'var alarminfo={"ISSUETIME":"2026-07-13 10:00:00",'
            '"head":"Thunderstorm yellow warning",'
            '"ISSUECONTENT":"Expect lightning and strong winds.",'
            '"TYPECODE":"01","LEVELCODE":"02",'
            '"identifier":"31000041600000_20260713100000"}'
        )

        payload = parse_warning_detail(script, REF_A)

        self.assertEqual(payload["id"], "310000-20260713100000-11B0102")
        self.assertEqual(payload["effective"], "2026-07-13 10:00:00")
        self.assertEqual(payload["headline"], "Thunderstorm yellow warning")
        self.assertEqual(payload["title"], "Thunderstorm yellow warning")
        self.assertEqual(payload["description"], "Expect lightning and strong winds.")
        self.assertEqual(payload["longitude"], "121.47")
        self.assertEqual(payload["latitude"], "31.23")
        self.assertEqual(payload["type"], "11B01_yellow")
        self.assertEqual(payload["transport_metadata"]["identifier"], WARNING_ID_A)

    def test_parse_warning_detail_rejects_non_detail_wrapper(self) -> None:
        with self.assertRaises(ValueError):
            parse_warning_detail("var alarmdata={};", REF_A)

    def test_parse_warning_detail_rejects_trailing_garbage(self) -> None:
        script = 'var alarminfo={"TYPECODE":"01","LEVELCODE":"02"}; trailing'

        with self.assertRaises(ValueError):
            parse_warning_detail(script, REF_A)

    def test_parse_warning_detail_rejects_missing_or_unsupported_codes(self) -> None:
        missing_type_code = 'var alarminfo={"LEVELCODE":"02"};'
        unsupported_level_code = 'var alarminfo={"TYPECODE":"01","LEVELCODE":"06"};'

        with self.assertRaises(ValueError):
            parse_warning_detail(missing_type_code, REF_A)
        with self.assertRaises(ValueError):
            parse_warning_detail(unsupported_level_code, REF_A)

    def test_parse_warning_detail_rejects_mismatched_identifier(self) -> None:
        script = (
            'var alarminfo={"TYPECODE":"01","LEVELCODE":"02",'
            '"identifier":"32000041600000_20260713100500"};'
        )

        with self.assertRaises(ValueError):
            parse_warning_detail(script, REF_A)

    def test_parse_warning_detail_rejects_missing_identifier(self) -> None:
        script = 'var alarminfo={"TYPECODE":"01","LEVELCODE":"02"};'

        with self.assertRaises(ValueError):
            parse_warning_detail(script, REF_A)

    def test_build_fan_weather_event_id_matches_fan_shape(self) -> None:
        event_id = build_fan_weather_event_id(WARNING_ID_A, "01", "02")

        self.assertEqual(event_id, "310000-20260713100000-11B0102")

    def test_build_fan_weather_event_id_rejects_invalid_identifier(self) -> None:
        with self.assertRaises(ValueError):
            build_fan_weather_event_id("not-an-identifier", "01", "02")

    def test_build_fan_weather_event_id_rejects_corrupted_official_shapes(
        self,
    ) -> None:
        corrupted_identifiers = (
            "3100004160000_20260713100000",
            "310000416000000_20260713100000",
            "31000041600000_20261313100000",
            "31000041600000_20260713100000_extra",
            "3100004160000X_20260713100000",
        )

        for identifier in corrupted_identifiers:
            with self.subTest(identifier=identifier):
                with self.assertRaises(ValueError):
                    build_fan_weather_event_id(identifier, "01", "02")

    def test_snapshot_tracker_warms_without_emitting_then_returns_new_ids(self) -> None:
        tracker = WarningSnapshotTracker(max_entries=100)

        self.assertEqual(tracker.observe([REF_A]), [])
        self.assertEqual(tracker.observe([REF_A, REF_B]), [REF_B])

    def test_snapshot_tracker_retains_a_bounded_recent_snapshot(self) -> None:
        tracker = WarningSnapshotTracker(max_entries=2)

        tracker.observe([REF_A, REF_B])
        ref_c = WarningReference(
            identifier="33000041600000_20260713101000",
            detail_path="c.html",
            longitude="120.15",
            latitude="30.28",
            title="Zhejiang hail warning",
        )
        self.assertEqual(tracker.observe([REF_A, REF_B, ref_c]), [ref_c])
        self.assertEqual(tracker.observe([REF_A]), [REF_A])

    def test_bounded_ttl_set_expires_and_caps_entries(self) -> None:
        clock = MutableClock()
        cache = BoundedTTLSet(ttl_seconds=10, max_entries=2, clock=clock)

        cache.add("a")
        cache.add("b")
        cache.add("c")
        self.assertNotIn("a", cache)
        self.assertIn("b", cache)

        clock.value = 10.0
        self.assertNotIn("b", cache)
        self.assertNotIn("c", cache)


class ChinaWeatherReconcilerAsyncTests(unittest.IsolatedAsyncioTestCase):
    def _reconciler(self, detail_concurrency: int = 4):
        reconciler_type = _require_feature(
            self, ChinaWeatherReconciler, "ChinaWeatherReconciler"
        )
        return reconciler_type(detail_concurrency=detail_concurrency)

    async def test_first_cycle_is_baseline_then_only_new_warning_dispatches(
        self,
    ) -> None:
        reconciler = self._reconciler()
        fetched_paths: list[str] = []
        dispatched_payloads: list[dict[str, object]] = []

        async def fetch_detail(path: str) -> str:
            fetched_paths.append(path)
            return _detail_script(REF_B)

        async def dispatch(payload: dict[str, object]) -> None:
            dispatched_payloads.append(payload)

        first_result = await reconciler.reconcile(
            _index_script(REF_A), fetch_detail, dispatch
        )
        second_result = await reconciler.reconcile(
            _index_script(REF_A, REF_B), fetch_detail, dispatch
        )

        self.assertEqual(first_result.new_count, 0)
        self.assertEqual(fetched_paths, ["b.html"])
        self.assertEqual(second_result.dispatched_count, 1)
        self.assertEqual(len(dispatched_payloads), 1)
        self.assertEqual(dispatched_payloads[0]["id"], "320000-20260713100500-11B0102")
        self.assertEqual(
            dispatched_payloads[0]["transport_metadata"]["transport"],
            "china_weather_http",
        )

    async def test_failed_detail_is_isolated_and_retried_next_cycle(self) -> None:
        reconciler = self._reconciler(detail_concurrency=2)
        attempts: dict[str, int] = {}
        dispatched_ids: list[str] = []

        async def fetch_detail(path: str) -> str:
            attempts[path] = attempts.get(path, 0) + 1
            if path == "b.html" and attempts[path] == 1:
                raise TimeoutError("detail request timed out")
            return _detail_script(REF_B if path == "b.html" else REF_C)

        async def dispatch(payload: dict[str, object]) -> None:
            dispatched_ids.append(str(payload["id"]))

        await reconciler.reconcile(_index_script(REF_A), fetch_detail, dispatch)
        failed_cycle = await reconciler.reconcile(
            _index_script(REF_A, REF_B, REF_C), fetch_detail, dispatch
        )
        retry_cycle = await reconciler.reconcile(
            _index_script(REF_A, REF_B, REF_C), fetch_detail, dispatch
        )

        self.assertEqual(failed_cycle.dispatched_count, 1)
        self.assertEqual(failed_cycle.failed_identifiers, (WARNING_ID_B,))
        self.assertIn("330000-20260713101000-11B0102", dispatched_ids)
        self.assertEqual(retry_cycle.dispatched_count, 1)
        self.assertEqual(attempts, {"b.html": 2, "c.html": 1})
        self.assertEqual(dispatched_ids.count("320000-20260713100500-11B0102"), 1)

    async def _run_dispatch_consumption_case(self, *, fail_dispatch: bool):
        reconciler = self._reconciler()
        fetch_count = 0
        dispatch_count = 0

        async def fetch_detail(path: str) -> str:
            nonlocal fetch_count
            fetch_count += 1
            return _detail_script(REF_B)

        async def dispatch(payload: dict[str, object]) -> None:
            nonlocal dispatch_count
            dispatch_count += 1
            if fail_dispatch:
                raise RuntimeError("dispatch callback failed before consumption")

        await reconciler.reconcile(_index_script(REF_A), fetch_detail, dispatch)
        consumed_cycle = await reconciler.reconcile(
            _index_script(REF_A, REF_B), fetch_detail, dispatch
        )
        repeated_cycle = await reconciler.reconcile(
            _index_script(REF_A, REF_B), fetch_detail, dispatch
        )
        return consumed_cycle, repeated_cycle, fetch_count, dispatch_count

    async def test_escaped_dispatch_exception_is_consumed_at_most_once(self) -> None:
        (
            consumed_cycle,
            repeated_cycle,
            fetch_count,
            dispatch_count,
        ) = await self._run_dispatch_consumption_case(fail_dispatch=True)

        self.assertEqual(getattr(consumed_cycle, "consumed_count", None), 1)
        self.assertEqual(consumed_cycle.failed_identifiers, ())
        self.assertEqual(consumed_cycle.consumed_error_identifiers, (WARNING_ID_B,))
        self.assertEqual(repeated_cycle.new_count, 0)
        self.assertEqual(fetch_count, 1)
        self.assertEqual(dispatch_count, 1)

    async def test_none_returning_dispatch_is_consumed_at_most_once(self) -> None:
        (
            consumed_cycle,
            repeated_cycle,
            fetch_count,
            dispatch_count,
        ) = await self._run_dispatch_consumption_case(fail_dispatch=False)

        self.assertEqual(getattr(consumed_cycle, "consumed_count", None), 1)
        self.assertEqual(consumed_cycle.failed_identifiers, ())
        self.assertEqual(consumed_cycle.consumed_error_identifiers, ())
        self.assertEqual(repeated_cycle.new_count, 0)
        self.assertEqual(fetch_count, 1)
        self.assertEqual(dispatch_count, 1)

    async def test_invalid_index_does_not_warm_or_replace_tracker_state(self) -> None:
        reconciler = self._reconciler()
        fetched_paths: list[str] = []

        async def fetch_detail(path: str) -> str:
            fetched_paths.append(path)
            return _detail_script(REF_B)

        async def dispatch(payload: dict[str, object]) -> None:
            pass

        invalid_cold = await reconciler.reconcile(
            "not a China Weather index", fetch_detail, dispatch
        )
        await reconciler.reconcile(_index_script(REF_A), fetch_detail, dispatch)
        invalid_warm = await reconciler.reconcile(
            "still not a China Weather index", fetch_detail, dispatch
        )
        await reconciler.reconcile(_index_script(REF_A, REF_B), fetch_detail, dispatch)

        self.assertFalse(invalid_cold.index_valid)
        self.assertFalse(invalid_warm.index_valid)
        self.assertEqual(fetched_paths, ["b.html"])

    async def test_unsafe_detail_paths_are_rejected_before_fetch(self) -> None:
        reconciler = self._reconciler()
        fetched_paths: list[str] = []
        unsafe_paths = (
            "https://evil.example/a.html",
            "//evil.example/a.html",
            "/absolute.html",
            "../traversal.html",
            "nested/a.html",
            "nested\\a.html",
            "a.html?query=1",
            "a.html#fragment",
            "%2e%2e%2fencoded.html",
        )
        unsafe_references = tuple(
            WarningReference(
                identifier=f"{34000000000000 + offset:014d}_2026071311{offset:02d}00",
                detail_path=path,
                longitude="116.40",
                latitude="39.90",
                title="Unsafe path warning",
            )
            for offset, path in enumerate(unsafe_paths)
        )

        async def fetch_detail(path: str) -> str:
            fetched_paths.append(path)
            raise AssertionError("unsafe paths must not reach the network callback")

        async def dispatch(payload: dict[str, object]) -> None:
            raise AssertionError("unsafe paths must not dispatch")

        await reconciler.reconcile(_index_script(), fetch_detail, dispatch)
        result = await reconciler.reconcile(
            _index_script(*unsafe_references), fetch_detail, dispatch
        )

        self.assertEqual(fetched_paths, [])
        self.assertEqual(result.dispatched_count, 0)
        self.assertEqual(
            set(result.failed_identifiers),
            {reference.identifier for reference in unsafe_references},
        )


if __name__ == "__main__":
    unittest.main()
