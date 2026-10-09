"""What both checkers share: a client that talks like the scale, and a report.

The client sends header auth, follows no redirects, asks for identity encoding
and records every status it saw, so a checker can judge the redirect rule at
the end. The report prints one line per check and counts MUST failures and
SHOULD warnings. Standard library only.
"""
from __future__ import annotations

import base64
import json
import ssl
import urllib.error
import urllib.request
from typing import Any, Dict, List, Optional, Tuple

# ("must" | "should", message), the shape every rules module returns.
Finding = Tuple[str, str]

MAX_FINDINGS_SHOWN = 5


class NoRedirect(urllib.request.HTTPRedirectHandler):
    """Hands a 3xx back as the answer: the scale never follows one."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class Response:
    def __init__(self, status: int, headers: Dict[str, str], body: bytes):
        self.status = status
        self.headers = {k.lower(): v for k, v in headers.items()}
        self.body = body

    @property
    def json(self) -> Any:
        try:
            return json.loads(self.body.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            return None

    def __str__(self) -> str:
        text = self.body.decode("utf-8", "replace").strip()
        return f"HTTP {self.status} {text[:160]}"


class Client:
    """Talks like the scale: header auth, no redirects, identity encoding."""

    def __init__(self, base: str, auth: Optional[Dict[str, str]], timeout: float, insecure: bool):
        self.base = base.rstrip("/")
        self.auth = auth
        self.timeout = timeout
        self.seen: List[Tuple[str, str, int]] = []   # (method, path, status)
        handlers: List[Any] = [NoRedirect()]
        if insecure:
            handlers.append(urllib.request.HTTPSHandler(context=ssl._create_unverified_context()))
        self.opener = urllib.request.build_opener(*handlers)

    def _add_auth(self, req: urllib.request.Request) -> None:
        if not self.auth:
            return
        kind, secret = self.auth["kind"], self.auth["secret"]
        if kind == "key":
            req.add_header("X-API-Key", secret)
        elif kind == "bearer":
            req.add_header("Authorization", "Bearer " + secret)
        elif kind == "basic":
            req.add_header("Authorization", "Basic " + base64.b64encode(secret.encode()).decode())

    def request(self, method: str, path: str, body: Any = None, with_auth: bool = True) -> Response:
        req = urllib.request.Request(self.base + path, method=method)
        req.add_header("Accept-Encoding", "identity")
        data = None
        if body is not None:
            data = json.dumps(body).encode("utf-8")
            req.add_header("Content-Type", "application/json")
        if with_auth:
            self._add_auth(req)
        response = self._send(req, data)
        self.seen.append((method, path, response.status))
        return response

    def _send(self, req: urllib.request.Request, data: Optional[bytes]) -> Response:
        try:
            with self.opener.open(req, data=data, timeout=self.timeout) as resp:
                return Response(resp.status, dict(resp.headers), resp.read())
        except urllib.error.HTTPError as err:
            return Response(err.code, dict(err.headers), err.read())
        except (urllib.error.URLError, OSError, ValueError) as err:
            return Response(0, {}, str(err).encode("utf-8"))

    def get(self, path: str, with_auth: bool = True) -> Response:
        return self.request("GET", path, None, with_auth)

    def redirects_seen(self) -> List[str]:
        return [f"{m} {p} -> {s}" for m, p, s in self.seen if 300 <= s < 400]


class Report:
    def __init__(self, verbose: bool):
        self.verbose = verbose
        self.failed = 0
        self.warned = 0

    def _line(self, mark: str, number: Any, title: str, detail: Any) -> None:
        print(f"{mark:<5}{str(number):>3}  {title}")
        if detail and (mark != "ok" or self.verbose):
            for line in str(detail).splitlines():
                print(f"          {line}")

    def must(self, number: Any, title: str, ok: bool, detail: Any = "") -> None:
        if not ok:
            self.failed += 1
        self._line("ok" if ok else "FAIL", number, title, detail)

    def should(self, number: Any, title: str, ok: bool, detail: Any = "") -> None:
        if not ok:
            self.warned += 1
        self._line("ok" if ok else "warn", number, title, detail)

    def skip(self, number: Any, title: str, why: str) -> None:
        self._line("skip", number, title, why)

    def findings(self, number: Any, title: str, found: List[Finding]) -> None:
        musts = sorted({m for level, m in found if level == "must"})
        shoulds = sorted({m for level, m in found if level == "should"})
        detail = "\n".join((musts + shoulds)[:MAX_FINDINGS_SHOWN])
        if musts:
            self.must(number, title, False, detail)
        elif shoulds:
            self.should(number, title, False, detail)
        else:
            self.must(number, title, True)

    def summary(self) -> str:
        return f"\n{self.failed} MUST failed, {self.warned} SHOULD warnings"


def auth_from(args: Any) -> Optional[Dict[str, str]]:
    """The one credential given on the command line, or None."""
    for kind in ("key", "bearer", "basic"):
        secret = getattr(args, kind, None)
        if secret:
            return {"kind": kind, "secret": secret}
    return None
