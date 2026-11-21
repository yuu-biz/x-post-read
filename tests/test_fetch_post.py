"""Offline behavior checks; synthetic posts only."""

import contextlib
import http.client
import io
import json
from pathlib import Path
import ssl
import sys
import unittest
from unittest.mock import Mock, patch
import urllib.error

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import fetch_post as reader


def status(**fields):
    return {"type": "status", "id": "20", "text": "hello", **fields}


class ReaderTests(unittest.TestCase):
    def test_permalink_forms(self):
        for value in ("20", "https://x.com/jack/status/20",
                      "https://mobile.twitter.com/jack/status/20?s=1#top",
                      "https://www.x.com/i/web/status/20/",
                      "https://twitter.com/jack/status/20/photo/1"):
            with self.subTest(value=value):
                self.assertEqual(reader.parse_post(value), "20")

    def test_rejects_unsafe_or_nonpost_inputs_before_network(self):
        bad = ("1", "0", "020", "123456789012345678901", "２０",
               "http://x.com/jack/status/20", "https://x.com.evil/jack/status/20",
               "https://x.com@evil/jack/status/20", "https://x.com:443/jack/status/20",
               "https://x.com/search?q=test", "https://x.com/jack/status/20/extra",
               "https://x.com/jack/status/20\n", "https://x.com/jack/status/20?x= bad",
               "https://x.com/jack/status/20;echo", "file:///20",
               "https://twİtter.com/jack/status/20", "https://x.com/K/status/20",
               "https://x.com/jack/status/20?x=\x00")
        with patch.object(reader, "fetch") as fetch:
            for value in bad:
                with self.subTest(value=value), contextlib.redirect_stderr(io.StringIO()):
                    self.assertNotEqual(reader.main([value]), 0)
            fetch.assert_not_called()

    def test_full_unicode_text_and_compact_output(self):
        text = "日本語🙂\n" * 2000 + "END"
        post = status(text=text, url="https://twitter.com/jack/status/20",
                      author={"name": "名前", "screen_name": "jack", "followers": 999},
                      created_at="Wed Mar 21 20:50:14 +0000 2007", likes=999)
        output, errors = io.StringIO(), io.StringIO()
        with patch.object(reader, "fetch", return_value={"code": 200, "status": post}), \
                contextlib.redirect_stdout(output), contextlib.redirect_stderr(errors):
            self.assertEqual(reader.main(["20"]), 0)
        result = json.loads(output.getvalue())
        self.assertEqual(result["text"], text)
        self.assertIn("日本語🙂", output.getvalue())
        self.assertEqual(result["url"], "https://x.com/jack/status/20")
        self.assertEqual(result["author"], {"name": "名前", "screen_name": "jack"})
        self.assertNotIn("likes", result)
        self.assertEqual(errors.getvalue(), "")

    def test_missing_optional_fields(self):
        result = reader.read_payload({"code": 200, "status": status()}, "20")
        self.assertEqual(result, {"url": "https://x.com/i/web/status/20", "text": "hello"})
        for media in (None, [], {"photos": None, "videos": [None, {}]}):
            self.assertNotIn("media", reader.summarize(status(media=media), "20"))

    def test_quote_and_media(self):
        quote = status(id="21", text="引用🙂", media={"photos": [{"url": "https://example.org/q.jpg"}]})
        post = status(quote=quote, media={
            "photos": [{"url": "https://example.org/a.jpg"}, {"url": "javascript:bad"}],
            "videos": [{"url": "https://example.org/a.mp4"}],
            "external": {"url": "https://example.org/external.mp4"}})
        result = reader.read_payload({"code": 200, "status": post}, "20")
        self.assertEqual(result["quote"]["text"], "引用🙂")
        self.assertEqual(len(result["media"]), 3)
        self.assertEqual(result["quote"]["media"][0]["type"], "image")
        post["quote"] = {"type": "tombstone", "reason": "private"}
        self.assertEqual(reader.read_payload({"code": 200, "status": post}, "20")["quote"],
                         {"unavailable": "private"})

    def test_invalid_payloads_and_api_errors(self):
        for payload in (None, [], {}, {"code": "200"}, {"code": 200},
                        {"code": 200, "status": status(id="21")},
                        {"code": 200, "status": status(text=None)},
                        {"code": 200, "status": status(quote={})}):
            with self.subTest(payload=payload), self.assertRaises(ValueError):
                reader.read_payload(payload, "20")
        for code in (401, 404, 429, 500):
            with self.assertRaisesRegex(ValueError, f"API code {code}.*unknown"):
                reader.read_payload({"code": code}, "20")

    def test_tombstones_only_report_explicit_reason(self):
        for reason in ("deleted", "private", "unavailable", None):
            with self.assertRaisesRegex(ValueError, "reports post unavailable") as raised:
                reader.read_payload({"code": 200, "status": {
                    "type": "tombstone", "reason": reason}}, "20")
            if reason != "deleted":
                self.assertNotIn("deleted", str(raised.exception))

    def test_http_and_transport_errors(self):
        for code in (302, 404, 429, 500):
            error = urllib.error.HTTPError(reader.ENDPOINT + "20", code, "error", {}, None)
            with patch("urllib.request.OpenerDirector.open", side_effect=error), \
                    self.assertRaisesRegex(ValueError, f"HTTP {code}.*unknown"):
                reader.fetch("20")
        for reason, kind in ((ssl.SSLError("test"), "TLS"), (TimeoutError(), "network/timeout")):
            with patch("urllib.request.OpenerDirector.open", side_effect=urllib.error.URLError(reason)), \
                    self.assertRaisesRegex(ValueError, f"local transport failure.*{kind}"):
                reader.fetch("20")
        with patch("urllib.request.OpenerDirector.open", side_effect=http.client.IncompleteRead(b"")), \
                self.assertRaisesRegex(ValueError, "local transport failure"):
            reader.fetch("20")
        self.assertIsNone(reader.NoRedirect().redirect_request(None, None, 302, "", {}, "http://example.org"))

    def test_json_and_size_failures(self):
        for raw in (b"not json", b"\xff", b"x" * (reader.MAX_BYTES + 1)):
            response = Mock(status=200)
            response.read.return_value = raw
            response.__enter__ = Mock(return_value=response)
            response.__exit__ = Mock(return_value=False)
            with patch("urllib.request.OpenerDirector.open", return_value=response), \
                    self.assertRaises(ValueError):
                reader.fetch("20")

    def test_failure_has_no_stdout(self):
        out, err = io.StringIO(), io.StringIO()
        with patch.object(reader, "fetch", return_value={"code": 404}), \
                contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            self.assertEqual(reader.main(["20"]), 1)
        self.assertEqual(out.getvalue(), "")
        self.assertIn("unknown", err.getvalue())


if __name__ == "__main__":
    unittest.main()
