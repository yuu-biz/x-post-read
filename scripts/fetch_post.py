#!/usr/bin/env python3
"""Read one public X post through FxEmbed; Python standard library only."""

import argparse
import http.client
import json
import re
import ssl
import sys
import urllib.error
import urllib.request
from urllib.parse import urlsplit

ID = r"[1-9][0-9]{1,19}"
PERMALINK = re.compile(
    rf"https://(?:www\.|mobile\.)?(?:x\.com|twitter\.com)/"
    rf"(?:[A-Za-z0-9_]{{1,15}}/status|i/web/status)/({ID})"
    r"(?:/(?:photo|video)/[1-9][0-9]*)?/?(?:\?[^\s#]*)?(?:#[^\s]*)?",
    re.IGNORECASE | re.ASCII,
)
ENDPOINT = "https://api.fxtwitter.com/2/status/"
TIMEOUT = 20
MAX_BYTES = 4 * 1024 * 1024


def parse_post(value):
    if any(ord(c) < 32 or ord(c) == 127 for c in value):
        raise ValueError("post input contains control characters")
    match = PERMALINK.fullmatch(value)
    if match:
        return match.group(1)
    if re.fullmatch(ID, value):
        return value
    raise ValueError("expected an HTTPS x.com/twitter.com post permalink or 2-20 digit ID")


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def fetch(post_id):
    request = urllib.request.Request(
        ENDPOINT + post_id,
        headers={"User-Agent": "x-post-read/1.0 (+https://github.com/yuu-biz/x-post-read)",
                 "Accept": "application/json"},
    )
    try:
        with urllib.request.build_opener(NoRedirect).open(request, timeout=TIMEOUT) as response:
            if response.status != 200:
                raise ValueError(f"FxEmbed HTTP {response.status}; post availability unknown")
            raw = response.read(MAX_BYTES + 1)
    except urllib.error.HTTPError as exc:
        raise ValueError(f"FxEmbed HTTP {exc.code}; post availability unknown") from None
    except (urllib.error.URLError, OSError, http.client.HTTPException) as exc:
        reason = getattr(exc, "reason", exc)
        kind = "TLS" if isinstance(reason, ssl.SSLError) else "network/timeout"
        raise ValueError(f"local transport failure ({kind}); no API result confirmed") from None
    if len(raw) > MAX_BYTES:
        raise ValueError("FxEmbed response too large; no truncated output returned")
    try:
        return json.loads(raw)
    except (ValueError, UnicodeError, RecursionError):
        raise ValueError("FxEmbed returned invalid JSON") from None


def obj(value):
    return value if isinstance(value, dict) else {}


def safe_url(value):
    if not isinstance(value, str) or any(c.isspace() for c in value):
        return None
    try:
        parts = urlsplit(value)
        if parts.scheme in ("https", "http") and parts.hostname and not parts.username:
            return value
    except ValueError:
        pass
    return None


def unavailable(post):
    reason = post.get("reason")
    return reason if reason in ("deleted", "suspended", "private", "blocked", "unavailable") else "unavailable"


def summarize(post, post_id):
    if post.get("type") == "tombstone":
        raise ValueError(f"FxEmbed reports post unavailable ({unavailable(post)})")
    if (post.get("type") != "status" or str(post.get("id")) != post_id
            or not isinstance(post.get("text"), str)):
        raise ValueError("FxEmbed returned an invalid or mismatched status")
    result = {"url": f"https://x.com/i/web/status/{post_id}", "text": post["text"]}
    try:
        original = post.get("url")
        if isinstance(original, str) and PERMALINK.fullmatch(original) and parse_post(original) == post_id:
            result["url"] = re.sub(r"https://(?:www\.|mobile\.)?(?:twitter|x)\.com/", "https://x.com/", original, flags=re.I)
    except ValueError:
        pass
    author = {key: value for key, value in obj(post.get("author")).items()
              if key in ("name", "screen_name") and isinstance(value, str)}
    if author:
        result["author"] = author
    if isinstance(post.get("created_at"), str):
        result["date"] = post["created_at"]
    media = obj(post.get("media"))
    links = []
    for group, label in (("photos", "image"), ("videos", "video")):
        entries = media.get(group)
        for entry in entries if isinstance(entries, list) else []:
            url = safe_url(obj(entry).get("url"))
            if url and {"type": label, "url": url} not in links:
                links.append({"type": label, "url": url})
    external = safe_url(obj(media.get("external")).get("url"))
    if external:
        links.append({"type": "video", "url": external})
    if links:
        result["media"] = links
    return result


def read_payload(payload, post_id):
    if not isinstance(payload, dict) or type(payload.get("code")) is not int:
        raise ValueError("FxEmbed returned an invalid response envelope")
    if payload["code"] != 200:
        raise ValueError(f"FxEmbed API code {payload['code']}; post availability unknown")
    post = obj(payload.get("status"))
    result = summarize(post, post_id)
    quote = post.get("quote")
    if quote is not None:
        quote = obj(quote)
        if quote.get("type") == "tombstone":
            result["quote"] = {"unavailable": unavailable(quote)}
        else:
            quote_id = str(quote.get("id", ""))
            if not re.fullmatch(ID, quote_id):
                raise ValueError("FxEmbed returned an invalid quote")
            result["quote"] = summarize(quote, quote_id)
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("post", help="HTTPS X/Twitter permalink or numeric post ID")
    args = parser.parse_args(argv)
    try:
        post_id = parse_post(args.post)
        result = read_payload(fetch(post_id), post_id)
    except ValueError as exc:
        print(f"x-post-read: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    sys.exit(main())
