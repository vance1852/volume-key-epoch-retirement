"""读取本地设备事实和字节，回放合成设备交互。"""

import argparse
import hashlib
import json
import re
import socket
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit


class FixtureServer(ThreadingHTTPServer):
    def __init__(self, address, directory):
        super().__init__(address, DeviceHandler)
        self.directory = Path(directory)
        self.record = json.loads((self.directory / "events.json").read_bytes())
        self.pending = list(self.record["packets"])
        self.journal = []
        self.lock = threading.Lock()

    def blob(self, name):
        if name not in self.record["objects"]:
            raise KeyError(name)
        return (self.directory / "objects" / name).read_bytes()

    def exchange(self, method, path, body):
        with self.lock:
            for index, item in enumerate(self.pending):
                if item["method"] != method or item["path"] != path:
                    continue
                if item["body"] is None and body or item["body"] is not None and body != self.blob(item["body"]):
                    continue
                reply = self.pending.pop(index)
                break
            else:
                reply = {"status": 404, "reply": {"state": "unmatched"}, "drop": False, "lag_ms": 0}
            self.journal.append({"method": method, "path": path, "bytes": len(body),
                                 "sha256": hashlib.sha256(body).hexdigest(), "drop": reply["drop"],
                                 "status": reply["status"]})
        return reply


class DeviceHandler(BaseHTTPRequestHandler):
    def send_bytes(self, status, data, content_type):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        if data:
            self.wfile.write(data)

    def send_json(self, status, data):
        self.send_bytes(status, json.dumps(data, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")

    def dispatch(self):
        path = urlsplit(self.path).path
        if self.command == "GET" and path == "/fixture/events":
            self.send_json(200, {key: self.server.record[key] for key in ("policy", "events", "objects")})
            return
        if self.command == "GET" and path == "/fixture/journal":
            with self.server.lock:
                journal = list(self.server.journal)
            self.send_json(200, journal)
            return
        if self.command == "GET" and (match := re.fullmatch(r"/fixture/objects/([a-zA-Z0-9_.-]+)", path)):
            try:
                blob = self.server.blob(match[1])
            except KeyError:
                self.send_json(404, {"state": "absent"})
            else:
                self.send_bytes(200, blob, "application/octet-stream")
            return
        try:
            size = int(self.headers.get("Content-Length", "0"))
            if not 0 <= size <= 1 << 20:
                raise ValueError
        except ValueError:
            self.send_json(400, {"state": "invalid_length"})
            return
        item = self.server.exchange(self.command, path, self.rfile.read(size))
        if item["lag_ms"]:
            time.sleep(item["lag_ms"] / 1000)
        if item["drop"]:
            self.close_connection = True
            self.connection.shutdown(socket.SHUT_WR)
            return
        try:
            self.send_json(item["status"], item["reply"])
        except (BrokenPipeError, ConnectionResetError):
            return

    do_GET = dispatch
    do_POST = dispatch
    do_PUT = dispatch
    do_DELETE = dispatch

    def log_message(self, *_):
        pass


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path, help="设备记录目录")
    parser.add_argument("--port", type=int, default=8090)
    args = parser.parse_args()
    with FixtureServer(("127.0.0.1", args.port), args.directory) as server:
        print(f"http://127.0.0.1:{server.server_port}", flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
