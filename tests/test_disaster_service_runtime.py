"""Runtime orchestration tests for China Weather reconciliation."""

from __future__ import annotations

import asyncio
import importlib.util
import sys
import types
import unittest

from test_china_weather_reconciliation import (
    REF_A,
    REF_B,
    _NoOpLogger,
    _REPOSITORY_ROOT,
    _TEST_PACKAGE_NAME,
    _detail_script,
    _index_script,
    _install_test_package,
    _require_feature,
    resolve_fallback_config,
)


_install_test_package(
    f"{_TEST_PACKAGE_NAME}.core.app", _REPOSITORY_ROOT / "core" / "app"
)
_install_test_package(
    f"{_TEST_PACKAGE_NAME}.core.app.runtime",
    _REPOSITORY_ROOT / "core" / "app" / "runtime",
)
_install_test_package(
    f"{_TEST_PACKAGE_NAME}.core.services.query",
    _REPOSITORY_ROOT / "core" / "services" / "query",
)


class _SourceRuntimeQueryService:
    def __init__(self, config: dict[str, object] | None = None) -> None:
        self.config = config or {}

    def is_source_enabled(self, source_id: str) -> bool:
        if source_id != "china_weather_fanstudio":
            return False
        data_sources = self.config.get("data_sources", {})
        if not isinstance(data_sources, dict):
            return False
        fan_studio = data_sources.get("fan_studio", {})
        return bool(
            isinstance(fan_studio, dict)
            and fan_studio.get("enabled", False)
            and fan_studio.get("china_weather_alarm", False)
        )


_SOURCE_QUERY_MODULE_NAME = (
    f"{_TEST_PACKAGE_NAME}.core.services.query.source_runtime_query_service"
)
_SOURCE_QUERY_MODULE = types.ModuleType(_SOURCE_QUERY_MODULE_NAME)
_SOURCE_QUERY_MODULE.SourceRuntimeQueryService = _SourceRuntimeQueryService
sys.modules[_SOURCE_QUERY_MODULE_NAME] = _SOURCE_QUERY_MODULE

_ASTRBOT_MODULE = types.ModuleType("astrbot")
_ASTRBOT_API_MODULE = types.ModuleType("astrbot.api")
_ASTRBOT_API_MODULE.logger = _NoOpLogger()
_ASTRBOT_MODULE.api = _ASTRBOT_API_MODULE
sys.modules["astrbot"] = _ASTRBOT_MODULE
sys.modules["astrbot.api"] = _ASTRBOT_API_MODULE

_RUNTIME_PATH = (
    _REPOSITORY_ROOT / "core" / "app" / "runtime" / "disaster_service_runtime.py"
)
_RUNTIME_MODULE_NAME = f"{_TEST_PACKAGE_NAME}.core.app.runtime.disaster_service_runtime"
_RUNTIME_SPEC = importlib.util.spec_from_file_location(
    _RUNTIME_MODULE_NAME, _RUNTIME_PATH
)
if _RUNTIME_SPEC is None or _RUNTIME_SPEC.loader is None:
    raise RuntimeError("unable to load disaster service runtime module")
_RUNTIME_MODULE = importlib.util.module_from_spec(_RUNTIME_SPEC)
sys.modules[_RUNTIME_MODULE_NAME] = _RUNTIME_MODULE
_RUNTIME_SPEC.loader.exec_module(_RUNTIME_MODULE)

DisasterServiceRuntimeService = _RUNTIME_MODULE.DisasterServiceRuntimeService
CHINA_WEATHER_HEADERS = _RUNTIME_MODULE._CHINA_WEATHER_HEADERS
CHINA_WEATHER_INDEX_URL = _RUNTIME_MODULE._CHINA_WEATHER_INDEX_URL
CHINA_WEATHER_DETAIL_BASE = _RUNTIME_MODULE._CHINA_WEATHER_DETAIL_BASE


class DisasterServiceRuntimeAsyncTests(unittest.IsolatedAsyncioTestCase):
    @staticmethod
    def _service(config: dict[str, object]) -> types.SimpleNamespace:
        return types.SimpleNamespace(
            config=config,
            running=False,
            scheduled_tasks=[],
        )

    def _weather_loop(self, runtime: DisasterServiceRuntimeService):
        return _require_feature(
            self,
            getattr(runtime, "_run_china_weather_loop", None),
            "DisasterServiceRuntimeService._run_china_weather_loop",
        )

    @staticmethod
    def _session_factory(events: list[object], response_provider):
        class FakeResponse:
            def __init__(self, url: str) -> None:
                self.url = url

            async def __aenter__(self):
                events.append(("response_enter", self.url))
                return self

            async def __aexit__(self, exc_type, exc, traceback) -> None:
                events.append(("response_exit", self.url))

            def raise_for_status(self) -> None:
                events.append(("raise_for_status", self.url))

            async def text(self) -> str:
                events.append(("text", self.url))
                response = response_provider(self.url)
                if isinstance(response, BaseException):
                    raise response
                return response

        class FakeSession:
            def __init__(self) -> None:
                self.closed = False

            async def __aenter__(self):
                events.append("session_enter")
                return self

            async def __aexit__(self, exc_type, exc, traceback) -> None:
                self.closed = True
                events.append("session_exit")

            def get(self, url: str) -> FakeResponse:
                events.append(("get", url))
                return FakeResponse(url)

        class FakeSessionFactory:
            def __init__(self) -> None:
                self.timeout = None
                self.headers = None
                self.session = FakeSession()

            def __call__(self, *, timeout, headers) -> FakeSession:
                self.timeout = timeout
                self.headers = dict(headers)
                events.append("session_create")
                return self.session

        return FakeSessionFactory()

    async def test_running_loop_fetches_immediately_with_bounded_client_contract(
        self,
    ) -> None:
        service = self._service({})
        service.running = True
        runtime = DisasterServiceRuntimeService(service)
        events: list[object] = []
        factory = self._session_factory(events, lambda url: _index_script())
        resolver = _require_feature(
            self, resolve_fallback_config, "resolve_fallback_config"
        )
        fallback = resolver(
            {"weather_alarm_fallback": {"request_timeout_seconds": 999}}
        )

        async def stop_after_first_cycle(seconds: float) -> None:
            events.append(("sleep", seconds))
            service.running = False

        await self._weather_loop(runtime)(
            fallback,
            session_factory=factory,
            sleep=stop_after_first_cycle,
        )

        self.assertLess(
            events.index(("get", CHINA_WEATHER_INDEX_URL)),
            events.index(("sleep", 180)),
        )
        self.assertEqual(factory.timeout.total, 30)
        self.assertEqual(factory.headers, CHINA_WEATHER_HEADERS)
        self.assertEqual(factory.headers["Referer"], "http://www.weather.com.cn/alarm/")
        self.assertIn("Mozilla/5.0", factory.headers["User-Agent"])
        self.assertTrue(factory.session.closed)

    async def test_running_loop_closes_session_and_propagates_cancellation(
        self,
    ) -> None:
        service = self._service({})
        service.running = True
        runtime = DisasterServiceRuntimeService(service)
        events: list[object] = []
        factory = self._session_factory(events, lambda url: asyncio.CancelledError())
        resolver = _require_feature(
            self, resolve_fallback_config, "resolve_fallback_config"
        )

        async def unexpected_sleep(seconds: float) -> None:
            self.fail("cancelled index fetch must not sleep")

        with self.assertRaises(asyncio.CancelledError):
            await self._weather_loop(runtime)(
                resolver({}),
                session_factory=factory,
                sleep=unexpected_sleep,
            )

        self.assertTrue(factory.session.closed)
        self.assertNotIn(("sleep", 180), events)

    async def test_none_parse_result_skips_handler_and_is_consumed(self) -> None:
        service = self._service({})
        service.running = True
        parse_calls: list[tuple[str, str]] = []
        handled_events: list[object] = []
        service.parse_event = lambda source, payload: (
            parse_calls.append((source, payload)) or None
        )

        async def handle_event(event: object) -> None:
            handled_events.append(event)

        service._handle_disaster_event = handle_event
        runtime = DisasterServiceRuntimeService(service)
        events: list[object] = []
        index_scripts = [
            _index_script(REF_A),
            _index_script(REF_A, REF_B),
            _index_script(REF_A, REF_B),
        ]
        detail_fetch_count = 0

        def response_provider(url: str):
            nonlocal detail_fetch_count
            if url == CHINA_WEATHER_INDEX_URL:
                return index_scripts.pop(0)
            if url == f"{CHINA_WEATHER_DETAIL_BASE}b.html":
                detail_fetch_count += 1
                return _detail_script(REF_B)
            raise AssertionError(f"unexpected URL: {url}")

        factory = self._session_factory(events, response_provider)
        cycle_count = 0

        async def stop_after_three_cycles(seconds: float) -> None:
            nonlocal cycle_count
            cycle_count += 1
            if cycle_count == 3:
                service.running = False

        resolver = _require_feature(
            self, resolve_fallback_config, "resolve_fallback_config"
        )
        await self._weather_loop(runtime)(
            resolver({}),
            session_factory=factory,
            sleep=stop_after_three_cycles,
        )

        self.assertEqual(len(parse_calls), 1)
        self.assertEqual(parse_calls[0][0], "china_weather_fanstudio")
        self.assertEqual(handled_events, [])
        self.assertEqual(detail_fetch_count, 1)
        self.assertEqual(index_scripts, [])
        self.assertTrue(factory.session.closed)

    async def test_china_weather_uses_verified_public_alarm_referer(self) -> None:
        self.assertEqual(
            CHINA_WEATHER_HEADERS["Referer"],
            "http://www.weather.com.cn/alarm/",
        )
        self.assertIn("Mozilla/5.0", CHINA_WEATHER_HEADERS["User-Agent"])

    async def test_disabled_fallback_preserves_only_wolfx_task(self) -> None:
        service = self._service(
            {
                "data_sources": {
                    "fan_studio": {
                        "enabled": True,
                        "china_weather_alarm": True,
                    }
                }
            }
        )

        await DisasterServiceRuntimeService(service).start_scheduled_http_fetch()
        task_names = [task.get_name() for task in service.scheduled_tasks]
        await asyncio.gather(*service.scheduled_tasks)

        self.assertEqual(task_names, ["dw_http_fetch_wolfx"])

    async def test_enabled_fallback_adds_exactly_one_named_task_and_keeps_wolfx(
        self,
    ) -> None:
        service = self._service(
            {
                "weather_alarm_fallback": {"enabled": True},
                "data_sources": {
                    "fan_studio": {
                        "enabled": True,
                        "china_weather_alarm": True,
                    }
                },
            }
        )

        await DisasterServiceRuntimeService(service).start_scheduled_http_fetch()
        task_names = [task.get_name() for task in service.scheduled_tasks]
        await asyncio.gather(*service.scheduled_tasks)

        self.assertEqual(
            task_names,
            ["dw_http_fetch_wolfx", "dw_http_fetch_china_weather"],
        )


if __name__ == "__main__":
    unittest.main()
