import importlib
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

if "astrbot" not in sys.modules:
    astrbot_module = types.ModuleType("astrbot")
    api_module = types.ModuleType("astrbot.api")
    api_module.logger = types.SimpleNamespace(debug=lambda *args, **kwargs: None, warning=lambda *args, **kwargs: None, info=lambda *args, **kwargs: None, error=lambda *args, **kwargs: None)
    astrbot_module.api = api_module
    sys.modules["astrbot"] = astrbot_module
    sys.modules["astrbot.api"] = api_module

package_module = types.ModuleType("astrbot_plugin_disaster_warning")
package_module.__path__ = [str(ROOT)]
sys.modules.setdefault("astrbot_plugin_disaster_warning", package_module)


def test_fan_studio_adapter_normalizes_local_authority_and_emsc_payloads():
    adapter_module = importlib.import_module("core.network.fan_studio_adapter")
    adapter = adapter_module.FanStudioAdapter

    local_payload = {
        "type": "update",
        "source": "cea-pr",
        "Data": {
            "id": "local-1",
            "latitude": "31.2",
            "longitude": "121.5",
            "depth": "10",
            "magnitude": "4.8",
            "epiIntensity": "Ⅳ",
            "placeName": "上海",
            "province": "上海市",
            "shockTime": "2024-01-01T00:00:00+00:00",
        },
    }

    emsc_payload = {
        "type": "update",
        "source": "emsc",
        "Data": {
            "event_id": "emsc-1",
            "lat": "38.0",
            "lon": "-122.0",
            "depth_km": "14",
            "mag": "5.5",
            "time": "2024-01-01T00:00:00Z",
            "agency": "EMSC",
        },
    }

    local_norm = adapter.normalize(local_payload)
    emsc_norm = adapter.normalize(emsc_payload)

    assert local_norm["magnitude"] == 4.8
    assert local_norm["latitude"] == 31.2
    assert local_norm["longitude"] == 121.5
    assert local_norm["source"] == "cea-pr"
    assert local_norm["raw"]["Data"]["placeName"] == "上海"

    assert emsc_norm["magnitude"] == 5.5
    assert emsc_norm["latitude"] == 38.0
    assert emsc_norm["longitude"] == -122.0
    assert emsc_norm["depth"] == 14.0
    assert emsc_norm["source"] == "emsc"


def test_fan_studio_adapter_preserves_zero_values():
    adapter_module = importlib.import_module("core.network.fan_studio_adapter")
    adapter = adapter_module.FanStudioAdapter

    payload = {
        "type": "update",
        "source": "emsc",
        "Data": {
            "lat": 0.0,
            "lon": 0.0,
            "depth_km": 0.0,
            "mag": 0.0,
            "time": "2024-01-01T00:00:00Z",
        },
    }

    normalized = adapter.normalize(payload)

    assert normalized["latitude"] == 0.0
    assert normalized["longitude"] == 0.0
    assert normalized["depth"] == 0.0
    assert normalized["magnitude"] == 0.0


def test_message_formatting_honors_enable_emoji_setting():
    from utils.formatters import format_earthquake_message

    class DummyEarthquake:
        def __init__(self):
            self.magnitude = 5.0
            self.intensity = "Ⅳ"
            self.place_name = "上海"
            self.province = None
            self.shock_time = None
            self.updates = 1
            self.is_final = False
            self.raw_data = {}
            self.latitude = 31.2
            self.longitude = 121.5
            self.depth = 10.0

    earthquake = DummyEarthquake()

    enabled_text = format_earthquake_message("cea_fanstudio", earthquake, options={"enable_emoji": True})
    disabled_text = format_earthquake_message("cea_fanstudio", earthquake, options={"enable_emoji": False})

    assert "💥" in enabled_text
    assert "💥" not in disabled_text
