import unittest

from overlay_events import normalize_overlay_event


class OverlayEventsTests(unittest.TestCase):
    def test_hitmarker_event_is_cosmetic(self):
        evt = normalize_overlay_event(
            "event",
            {"event_type": "hitmarker", "filename": "hm.png"},
            seq=1,
        )
        self.assertEqual(evt["category"], "cosmetic")
        self.assertEqual(evt["dedupe_key"], "")

    def test_critical_event_is_critical(self):
        evt = normalize_overlay_event(
            "event",
            {"event_type": "death", "filename": "death.png"},
            seq=2,
        )
        self.assertEqual(evt["category"], "critical")

    def test_state_event_has_state_keys(self):
        evt = normalize_overlay_event("stats", {"html": "ok"}, seq=3)
        self.assertEqual(evt["category"], "state")
        self.assertEqual(evt["coalesce_key"], "stats")
        self.assertEqual(evt["dedupe_key"], "stats")


if __name__ == "__main__":
    unittest.main()
