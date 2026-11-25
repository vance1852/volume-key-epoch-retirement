"""核对设备资料中的字节、事件引用和设备回包。"""

import hashlib
import http.client
import json
from pathlib import Path
import threading
import time
import unittest

from device_fixture import FixtureServer


class FixtureTest(unittest.TestCase):
    def test_device_files(self):
        folders = sorted((Path(__file__).parent / "fixtures").iterdir())
        self.assertGreaterEqual(len(folders), 2)
        for folder in folders:
            with self.subTest(folder=folder.name):
                self.check_fixture(folder)

    def check_fixture(self, folder):
        server = FixtureServer(("127.0.0.1", 0), folder)
        worker = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.02})
        worker.start()
        try:
            record = server.record
            status, data = self.request(server, "GET", "/fixture/events")
            self.assertEqual(status, 200)
            self.assertEqual(json.loads(data), {key: record[key] for key in ("policy", "events", "objects")})
            times = [event["at"] for event in record["events"]]
            self.assertEqual(times, sorted(times))
            self.assertTrue(times)
            self.assertEqual(set(record["objects"]), {path.name for path in (folder / "objects").iterdir()})
            for event in record["events"]:
                if "file" in event:
                    self.assertIn(event["file"], record["objects"])
            for name, metadata in record["objects"].items():
                status, data = self.request(server, "GET", "/fixture/objects/" + name)
                self.assertEqual(status, 200)
                self.assertEqual(data, (folder / "objects" / name).read_bytes())
                self.assertEqual(metadata, {"bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()})
            for packet in record["packets"]:
                body = server.blob(packet["body"]) if packet["body"] is not None else None
                args = server, packet["method"], packet["path"], body
                start = time.monotonic()
                if packet["drop"]:
                    with self.assertRaises(http.client.RemoteDisconnected):
                        self.request(*args)
                else:
                    status, data = self.request(*args)
                    self.assertEqual((status, json.loads(data)), (packet["status"], packet["reply"]))
                self.assertGreaterEqual(time.monotonic() - start + .005, packet["lag_ms"] / 1000)
            status, data = self.request(server, "GET", "/fixture/journal")
            self.assertEqual(status, 200)
            journal = json.loads(data)
            self.assertEqual(len(journal), len(record["packets"]))
            self.assertEqual([entry["drop"] for entry in journal], [packet["drop"] for packet in record["packets"]])
            self.assertEqual(self.request(server, "GET", "/fixture/objects/missing")[0], 404)
        finally:
            server.shutdown()
            worker.join(timeout=3)
            server.server_close()

    @staticmethod
    def request(server, method, path, body=None):
        connection = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=3)
        try:
            connection.request(method, path, body=body)
            response = connection.getresponse()
            return response.status, response.read()
        finally:
            connection.close()


if __name__ == "__main__":
    unittest.main()
