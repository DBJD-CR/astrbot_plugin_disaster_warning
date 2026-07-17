"""Async reconciliation behavior tests for China Weather snapshots."""

from __future__ import annotations

import unittest

from test_china_weather_reconciliation import (
    REF_A,
    REF_B,
    REF_C,
    WARNING_ID_B,
    ChinaWeatherReconciler,
    WarningReference,
    _detail_script,
    _index_script,
)


class ChinaWeatherReconcilerAsyncTests(unittest.IsolatedAsyncioTestCase):
    @staticmethod
    def _reconciler(detail_concurrency: int = 4):
        return ChinaWeatherReconciler(detail_concurrency=detail_concurrency)

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
