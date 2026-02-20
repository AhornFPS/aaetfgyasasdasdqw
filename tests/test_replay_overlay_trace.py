import os
import tempfile
import unittest

from tools.replay_overlay_trace import load_trace_events


class ReplayOverlayTraceTests(unittest.TestCase):
    def _write_trace(self, rows):
        fd, path = tempfile.mkstemp(suffix=".jsonl")
        os.close(fd)
        with open(path, "w", encoding="utf-8") as f:
            for row in rows:
                f.write(row + "\n")
        return path

    def test_load_trace_events_uses_server_trace_timestamp(self):
        path = self._write_trace(
            [
                '{"ts_server_trace_ms": 1000, "category":"event", "data":{"event_type":"kill"}}',
                '{"ts_server_trace_ms": 1300, "category":"event", "data":{"event_type":"death"}}',
            ]
        )
        try:
            events = load_trace_events(path)
            self.assertEqual(len(events), 2)
            self.assertEqual(events[0]["ts_ms"], 1000)
            self.assertEqual(events[1]["ts_ms"], 1300)
            self.assertEqual(events[0]["message"]["category"], "event")
        finally:
            os.unlink(path)

    def test_load_trace_events_falls_back_to_payload_timestamps(self):
        path = self._write_trace(
            [
                '{"category":"event", "data":{"event_type":"kill","ts_server_rx_ms":2000}}',
                '{"category":"event", "data":{"event_type":"death","ts_source_ms":2500}}',
            ]
        )
        try:
            events = load_trace_events(path)
            self.assertEqual(len(events), 2)
            self.assertEqual(events[0]["ts_ms"], 2000)
            self.assertEqual(events[1]["ts_ms"], 2500)
        finally:
            os.unlink(path)

    def test_load_trace_events_skips_invalid_lines_and_respects_limit(self):
        path = self._write_trace(
            [
                '{"category":"event", "data":{"event_type":"a","ts_source_ms":1}}',
                'not-json',
                '{"foo":"bar"}',
                '{"category":"event", "data":{"event_type":"b","ts_source_ms":2}}',
            ]
        )
        try:
            events = load_trace_events(path, max_events=1)
            self.assertEqual(len(events), 1)
            self.assertEqual(events[0]["message"]["data"]["event_type"], "a")
        finally:
            os.unlink(path)


if __name__ == "__main__":
    unittest.main()

