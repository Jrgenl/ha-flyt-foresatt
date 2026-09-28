"""Minimal async client for the (unofficial) Flyt Foresatt API.

The parent portal (https://foresatt.visma.no) talks to https://api.foresatt.visma.no/
using a cookie-based session that is created after logging in with ID-porten via
Visma Connect. This client re-uses such a session: the user copies the ``Cookie``
header from a logged-in browser once, and the client keeps it up to date with any
``Set-Cookie`` headers the API sends back (sliding expiration).
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, date, datetime
from http.cookies import SimpleCookie
import json
import logging
from typing import Any

import aiohttp

from .const import API_URL, FRONTEND_URL

_LOGGER = logging.getLogger(__name__)

_TIMEOUT = aiohttp.ClientTimeout(total=30)


class FlytError(Exception):
    """Base error for the Flyt Foresatt client."""


class FlytAuthError(FlytError):
    """The session is missing, expired or rejected."""


class FlytConnectionError(FlytError):
    """Network or server error."""


class FlytNotFoundError(FlytError):
    """The endpoint returned 404 (typically: feature not available for this child)."""


def parse_cookie_header(raw: str) -> dict[str, str]:
    """Parse a pasted ``Cookie`` header (``a=b; c=d``) into a dict.

    Accepts an optional leading ``Cookie:`` and ignores whitespace/newlines.
    """
    raw = raw.strip()
    if raw.lower().startswith("cookie:"):
        raw = raw[len("cookie:") :]
    cookies: dict[str, str] = {}
    for part in raw.replace("\n", ";").split(";"):
        name, sep, value = part.strip().partition("=")
        if sep and name:
            cookies[name.strip()] = value.strip()
    return cookies


def format_date(value: date | datetime) -> str:
    """Format a date the way the portal does (``YYYY-MM-DDTHH:mm:ss``, local)."""
    if not isinstance(value, datetime):
        value = datetime(value.year, value.month, value.day)
    return value.strftime("%Y-%m-%dT%H:%M:%S")


class FlytClient:
    """Client for api.foresatt.visma.no."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        cookies: Mapping[str, str],
        culture: str = "nb-NO",
    ) -> None:
        """Initialize the client."""
        self._session = session
        self._cookies: dict[str, str] = dict(cookies)
        self._culture = culture
        self.cookies_changed = False

    @property
    def cookies(self) -> dict[str, str]:
        """Return the current session cookies."""
        return dict(self._cookies)

    def _cookie_header(self) -> str:
        return "; ".join(f"{k}={v}" for k, v in self._cookies.items())

    def _absorb_set_cookie(self, response: aiohttp.ClientResponse) -> None:
        """Merge Set-Cookie headers from the API into our cookie dict."""
        for header in response.headers.getall("Set-Cookie", []):
            parsed: SimpleCookie = SimpleCookie()
            try:
                parsed.load(header)
            except Exception:  # noqa: BLE001 - malformed cookie, ignore it
                continue
            for name, morsel in parsed.items():
                expired = morsel.value == "" or morsel["max-age"] == "0"
                if not expired and morsel["expires"]:
                    try:
                        expires = datetime.strptime(
                            morsel["expires"], "%a, %d %b %Y %H:%M:%S GMT"
                        ).replace(tzinfo=UTC)
                        expired = expires < datetime.now(UTC)
                    except ValueError:
                        pass
                if expired:
                    if self._cookies.pop(name, None) is not None:
                        self.cookies_changed = True
                elif self._cookies.get(name) != morsel.value:
                    self._cookies[name] = morsel.value
                    self.cookies_changed = True

    async def _request(
        self,
        method: str,
        path: str,
        params: Mapping[str, Any] | None = None,
    ) -> Any:
        if not self._cookies:
            raise FlytAuthError("No session cookies configured")
        headers = {
            "Accept": "application/json, text/plain, */*",
            "Requested-By": "XMLHttpRequest",
            "Origin": FRONTEND_URL,
            "Referer": f"{FRONTEND_URL}/",
            "Cookie": self._cookie_header(),
        }
        query = {k: v for k, v in (params or {}).items() if v is not None}
        query.setdefault("culture", self._culture)
        url = API_URL + path.lstrip("/")
        try:
            async with self._session.request(
                method,
                url,
                params=query,
                headers=headers,
                timeout=_TIMEOUT,
                allow_redirects=False,
            ) as resp:
                self._absorb_set_cookie(resp)
                if resp.status in (401, 403) or 300 <= resp.status < 400:
                    raise FlytAuthError(f"{method} {path}: HTTP {resp.status}")
                if resp.status == 404:
                    raise FlytNotFoundError(f"{method} {path}: HTTP 404")
                if resp.status >= 400:
                    raise FlytConnectionError(f"{method} {path}: HTTP {resp.status}")
                text = await resp.text()
        except (aiohttp.ClientError, TimeoutError) as err:
            raise FlytConnectionError(f"{method} {path}: {err}") from err
        if not text:
            return None
        try:
            return json.loads(text)
        except ValueError:
            return text

    async def get(self, path: str, params: Mapping[str, Any] | None = None) -> Any:
        """GET an API path and return decoded JSON."""
        return await self._request("GET", path, params)

    # --- Session / guardian -------------------------------------------------

    async def get_session(self) -> dict[str, Any]:
        """Return the session info. Raises FlytAuthError if not logged in."""
        return await self.get("v1/session")

    async def get_profile(self) -> dict[str, Any]:
        """Return the guardian profile."""
        return await self.get("v1/guardian/profile")

    async def get_children(self) -> list[dict[str, Any]]:
        """Return all children of the logged-in guardian."""
        data = await self.get("v2/children")
        if isinstance(data, dict):
            return list(data.get("children") or [])
        return list(data or [])

    async def get_badges(self) -> Any:
        """Return unread/badge counters for all school children."""
        return await self.get("vfs/v1/badge")

    async def get_digital_forms_not_answered(self) -> Any:
        """Return the number of unanswered digital forms."""
        return await self.get("vfs/v1/digital-forms/not-answered-count")

    # --- School child (pupil) -----------------------------------------------

    async def get_timetable(self, pupil_id: int | str, selected: date) -> Any:
        """Return the timetable for the week containing ``selected``."""
        return await self.get(
            f"vfs/v1/pupils/{pupil_id}/timetable",
            {"selectedDate": format_date(selected)},
        )

    async def get_notifications_unread_count(self, pupil_id: int | str) -> Any:
        """Return the number of unread notifications (kunngjøringer)."""
        return await self.get(f"vfs/v1/pupils/{pupil_id}/notifications/unread-count")

    async def get_direct_messages(self, pupil_id: int | str) -> Any:
        """Return direct conversation summaries."""
        return await self.get(f"vfs/v1/pupils/{pupil_id}/messages/direct")

    async def get_group_messages(self, pupil_id: int | str) -> Any:
        """Return group conversation summaries."""
        return await self.get(f"vfs/v1/pupils/{pupil_id}/messages/group")

    async def get_absence_years(self, pupil_id: int | str) -> Any:
        """Return school years that have absence data."""
        return await self.get(f"vfs/v1/pupils/{pupil_id}/absences/years")

    async def get_absence_summary(
        self, pupil_id: int | str, year_id: int | str, term: str | None = None
    ) -> Any:
        """Return an absence summary for a school year."""
        return await self.get(
            f"vfs/v1/pupils/{pupil_id}/absences/{year_id}/summary", {"term": term}
        )

    async def get_absences(
        self, pupil_id: int | str, year_id: int | str, term: str | None = None
    ) -> Any:
        """Return all absence records for a school year."""
        return await self.get(
            f"vfs/v1/pupils/{pupil_id}/absences/{year_id}", {"term": term}
        )

    async def get_sfo_presence(
        self, pupil_id: int | str, day: date, whole_week: bool = False
    ) -> Any:
        """Return SFO presence details (check-in/out, comments)."""
        return await self.get(
            f"vfs/v1/pupils/{pupil_id}/sfo-presence/details",
            {"date": format_date(day), "wholeWeek": str(whole_week).lower()},
        )

    async def get_sfo_week_summary(self, pupil_id: int | str, day: date) -> Any:
        """Return SFO presence summary for the week containing ``day``."""
        return await self.get(
            f"vfs/v1/pupils/{pupil_id}/sfo-presence/summary",
            {"date": format_date(day)},
        )
