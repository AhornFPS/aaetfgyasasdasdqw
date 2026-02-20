import unittest
from collections import deque

from overlay_server import OverlayServer


class OverlayServerPolicyTests(unittest.TestCase):
    def setUp(self):
        self.server = OverlayServer()

    def test_max_cosmetic_pending_is_bounded(self):
        self.server._max_transient_pending = 2048
        self.assertEqual(self.server._max_cosmetic_pending(), 256)
        self.server._max_transient_pending = 120
        self.assertEqual(self.server._max_cosmetic_pending(), 20)
        self.server._max_transient_pending = 64
        self.assertEqual(self.server._max_cosmetic_pending(), 16)

    def test_dedupe_ignores_critical(self):
        now = 1_700_000_000_000
        self.assertFalse(self.server._should_dedupe_transient("critical", "k", now))
        self.assertFalse(self.server._should_dedupe_transient("normal", "", now))

    def test_dedupe_matches_within_window(self):
        now = 1_700_000_000_000
        self.assertFalse(self.server._should_dedupe_transient("normal", "a", now))
        self.assertTrue(self.server._should_dedupe_transient("normal", "a", now + 50))
        self.assertFalse(self.server._should_dedupe_transient("normal", "a", now + 500))

    def test_make_room_prefers_dropping_cosmetic(self):
        self.server._pending_transient = deque(
            [
                ({"category": "hitmarker"}, "cosmetic", "c1"),
                ({"category": "event"}, "normal", "n1"),
            ]
        )
        ok = self.server._make_transient_room_for_lane("normal")
        self.assertTrue(ok)
        lanes = [item[1] for item in self.server._pending_transient]
        self.assertEqual(lanes, ["normal"])

    def test_hitmarker_event_counts_as_cosmetic_lane(self):
        # Works without running server: input lane metrics are updated before send path.
        self.server.event_pipeline_v2 = True
        self.server.broadcast("event", {"event_type": "hitmarker", "filename": "hm.png"})
        self.assertEqual(self.server._metrics["events_in_cosmetic"], 1)
        self.assertEqual(self.server._metrics["events_in_normal"], 0)


if __name__ == "__main__":
    unittest.main()
