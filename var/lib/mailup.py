from __future__ import annotations

import datetime
import logging
import time
from typing import Any, Dict, Iterator, Optional, Protocol

import httpx
from httpx import Client, HTTPStatusError

from var.lib.pianoESP import timeout_backoff
from var.lib.utils import APIClientInterface, APIException


class MailUpException(APIException):
    pass


class MailUpAuthException(MailUpException):
    pass


class TokenStore(Protocol):
    def get(self) -> Optional[Dict[str, Any]]: ...

    def set(self, token: Dict[str, Any]) -> None: ...


class MemoryTokenStore:
    def __init__(self):
        self._token = None

    def get(self):
        return self._token

    def set(self, token):
        self._token = token


def parse_date(value: str | None) -> Optional[datetime.datetime]:
    """
    Parse a MailUp date ("2014-11-27 10:35:49Z", ISO 8601 or WCF "/Date(ms)/") into an aware UTC datetime.
    """
    if not value:
        return None
    value = value.strip()

    if value.startswith("/Date("):
        millis = int(value[6:].split(")")[0].split("+")[0].split("-")[0])
        return datetime.datetime.fromtimestamp(millis / 1000, tz=datetime.timezone.utc)

    normalized = value.replace("Z", "+00:00").replace("T", " ")
    try:
        parsed = datetime.datetime.fromisoformat(normalized)
    except ValueError:
        parsed = None
        for fmt in ("%d/%m/%Y %H:%M:%S", "%m/%d/%Y %H:%M:%S", "%Y/%m/%d %H:%M:%S"):
            try:
                parsed = datetime.datetime.strptime(value.rstrip("Z"), fmt)
                break
            except ValueError:
                continue
        if parsed is None:
            raise ValueError(f"Unsupported MailUp date format: {value!r}")

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=datetime.timezone.utc)
    return parsed.astimezone(datetime.timezone.utc)


def format_filter_date(value: datetime.datetime) -> str:
    """Format an aware datetime as a MailUp filterby literal (always UTC)."""
    return value.astimezone(datetime.timezone.utc).strftime("#%Y-%m-%d %H:%M:%SZ#")


class MailUpClient(APIClientInterface):
    ENDPOINT = "https://services.mailup.com"
    TOKEN_PATH = "/Authorization/OAuth/Token"
    CONSOLE = "/API/v1.1/Rest/ConsoleService.svc"
    STATS = "/API/v1.1/Rest/MailStatisticsService.svc"

    PAGE_SIZE = 100
    # refresh the token a bit before the real expiration
    TOKEN_LEEWAY = 60

    def __init__(self,
                 client_id: str,
                 client_secret: str,
                 username: str = None,
                 password: str = None,
                 *,
                 refresh_token: str = None,
                 http_client: Optional[Client] = None,
                 token_store: Optional[TokenStore] = None,
                 logger: logging.Logger = None):
        if not client_id or not client_secret:
            raise MailUpAuthException("MailUp credentials are incomplete (client_id, client_secret)")

        self._client_id = client_id
        self._client_secret = client_secret
        self._username = username
        self._password = password
        self._refresh_token = refresh_token
        self._retry_sleep = 0
        self._owns_client = http_client is None
        self._http_client = http_client or Client(base_url=self.ENDPOINT, timeout=30)
        self._token_store = token_store or MemoryTokenStore()
        self._logger = logger or logging.getLogger(f"{__name__}.{self.__class__.__name__}")

    def close(self):
        if self._owns_client and not self._http_client.is_closed:
            self._http_client.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    # --- OAuth2 ---------------------------------------------------------

    def _request_token(self, data: Dict[str, str]) -> Dict[str, Any]:
        response = self._http_client.post(
            self.TOKEN_PATH,
            data={**data, "client_id": self._client_id, "client_secret": self._client_secret},
            auth=(self._client_id, self._client_secret),
        )
        if response.status_code != 200:
            raise MailUpAuthException(f"MailUp token request failed ({response.status_code}): {response.text[:200]}")

        payload = response.json()
        token = {
            "access_token": payload["access_token"],
            "refresh_token": payload.get("refresh_token"),
            "expires_at": time.time() + int(payload.get("expires_in", 900)),
        }
        self._token_store.set(token)
        return token

    def authenticate(self) -> Dict[str, Any]:
        """
        Prefer a refresh token from the authorization-code grant: on this account
        password/client_credentials tokens are issued but every resource call is 403.
        """
        stored = (self._token_store.get() or {}).get("refresh_token") or self._refresh_token
        if stored:
            try:
                self._logger.info("MailUp: requesting a new access token (refresh_token)")
                return self._request_token({"grant_type": "refresh_token", "refresh_token": stored})
            except MailUpAuthException as e:
                self._logger.warning(f"MailUp: stored refresh token refused: {e}")

        try:
            self._logger.info("MailUp: requesting a new access token (client_credentials)")
            return self._request_token({"grant_type": "client_credentials"})
        except MailUpAuthException as e:
            if not (self._username and self._password):
                raise MailUpAuthException(
                    "MailUp non emette un token con soli client_id/client_secret "
                    "(grant client_credentials non supportato). Servono anche username "
                    f"(mXXXXX della console) e password. Dettaglio: {e}"
                ) from e
            self._logger.info("MailUp: client_credentials refused, falling back to password grant")
            return self._request_token({
                "grant_type": "password",
                "username": self._username,
                "password": self._password,
            })

    def refresh(self, token: Dict[str, Any] = None) -> Dict[str, Any]:
        token = token or self._token_store.get() or {}
        if token.get("refresh_token"):
            try:
                self._logger.info("MailUp: refreshing access token")
                return self._request_token({"grant_type": "refresh_token", "refresh_token": token["refresh_token"]})
            except MailUpAuthException as e:
                self._logger.warning(f"MailUp: refresh failed, re-authenticating: {e}")
        return self.authenticate()

    def _access_token(self) -> str:
        token = self._token_store.get()
        if not token:
            token = self.authenticate()
        elif token.get("expires_at", 0) - self.TOKEN_LEEWAY <= time.time():
            token = self.refresh(token)
        return token["access_token"]

    # --- HTTP -----------------------------------------------------------

    @timeout_backoff(max_retries=5, multiplier=2)
    def call_api(self, path: str, method: str = "GET", **kwargs) -> Any:
        if method.upper() not in ("GET", "POST", "PUT", "DELETE"):
            raise ValueError(f"Invalid HTTP method: {method!r}")

        response = None
        for retry in range(4):
            for attempt in range(2):
                headers = {"Authorization": f"Bearer {self._access_token()}", "Accept": "application/json"}
                response = self._http_client.request(method.upper(), path, headers=headers, **kwargs)
                self._logger.info(f"API call: {method.upper()} {path} -> {response.status_code}")
                if response.status_code != 401 or attempt:
                    break
                self.refresh()
            if response is not None and response.status_code in (429, 500, 502, 503, 504) and retry < 3:
                self._logger.info(f"MailUp: retry {retry + 1} after HTTP {response.status_code} on {path}")
                time.sleep(self._retry_sleep * (retry + 1))
                continue
            break

        try:
            response.raise_for_status()
        except HTTPStatusError as e:
            # Status only: response bodies of list calls contain recipient addresses.
            raise MailUpException(f"MailUp HTTP {response.status_code} for {path}") from e

        if not response.content:
            return None
        try:
            return response.json()
        except ValueError as e:
            raise MailUpException(f"MailUp response is not JSON for {path}") from e

    def paginate(self, path: str, *, params: Dict[str, Any] = None, page_size: int = None) -> Iterator[Dict[str, Any]]:
        page_size = page_size or self.PAGE_SIZE
        page = 0
        seen = 0
        while True:
            data = self.call_api(path, params={**(params or {}), "pageSize": page_size, "pageNumber": page})
            items = (data or {}).get("Items") or []
            yield from items

            seen += len(items)
            total = (data or {}).get("TotalElementsCount")
            if not items or (total is not None and seen >= total) or (total is None and len(items) < page_size):
                return
            # the server may cap the page size: the next page number must follow the real one
            page_size = (data or {}).get("PageSize") or page_size
            page += 1

    def count(self, path: str, *, filterby: str = None) -> int:
        params = {"pageSize": 1, "pageNumber": 0}
        if filterby:
            params["filterby"] = filterby
        data = self.call_api(path, params=params) or {}
        total = data.get("TotalElementsCount")
        if isinstance(total, bool) or not isinstance(total, int):
            raise MailUpException(f"MailUp page has no TotalElementsCount for {path}")
        return total

    # --- Console --------------------------------------------------------

    def get_lists(self) -> list[Dict[str, Any]]:
        return list(self.paginate(f"{self.CONSOLE}/Console/User/Lists"))

    def get_send_history(self, list_id: int,
                         start: datetime.datetime = None,
                         end: datetime.datetime = None) -> list[Dict[str, Any]]:
        """
        Sendings of a list whose StartDate falls in [start, end).
        History is requested newest first and reading stops at the first sending older than `start`,
        as long as the server actually returned the items in descending order.
        """
        path = f"{self.CONSOLE}/Console/List/{list_id}/Emails/SendHistory"
        params = {"orderby": "StartDate desc"}
        if start and end:
            params["filterby"] = (
                f"StartDate >= {format_filter_date(start)} && StartDate < {format_filter_date(end)}"
            )
        try:
            return self._collect_history(self.paginate(path, params=params), start, end)
        except MailUpException as e:
            self._logger.warning(f"MailUp: ordered send history not available for list {list_id}, full scan: {e}")
            return self._collect_history(self.paginate(path), start, end, early_stop=False)

    @staticmethod
    def _collect_history(items, start, end, *, early_stop: bool = True) -> list[Dict[str, Any]]:
        result = []
        previous = None
        ordered = early_stop
        seen = 0
        for item in items:
            sent_at = parse_date(item.get("StartDate"))
            if sent_at is None:
                continue
            if previous is not None and sent_at > previous:
                ordered = False
            previous = sent_at
            seen += 1

            if start and sent_at < start:
                if ordered and seen > 1:
                    break
                continue
            if end and sent_at >= end:
                continue
            result.append({**item, "StartDate": sent_at, "EndDate": parse_date(item.get("EndDate"))})
        return result

    def get_message(self, list_id: int, message_id: int) -> Optional[Dict[str, Any]]:
        data = self.call_api(f"{self.CONSOLE}/Console/List/{list_id}/Emails",
                             params={"filterby": f"idMessage=={int(message_id)}", "pageSize": 1, "pageNumber": 0})
        items = (data or {}).get("Items") or []
        return items[0] if items else None

    def count_subscribed(self, list_id: int) -> int:
        return self.count(f"{self.CONSOLE}/Console/List/{list_id}/Recipients/Subscribed")

    def count_all_recipients(self, list_id: int) -> int:
        """Subscribed and unsubscribed recipients of a list."""
        return self.count(f"{self.CONSOLE}/Console/List/{list_id}/Recipients/EmailOptins")

    def count_optins(self, list_id: int, start: datetime.datetime, end: datetime.datetime, *,
                     field: str = "Optin_Date") -> int:
        """Recipients of a list whose opt-in (or opt-out with field="Optout_Date") happened in [start, end)."""
        return self.count(
            f"{self.CONSOLE}/Console/List/{list_id}/Recipients/EmailOptins",
            filterby=f"{field} >= {format_filter_date(start)} && {field} < {format_filter_date(end)}",
        )

    # --- Statistics -----------------------------------------------------

    def count_list_recipients(self, list_id: int) -> int:
        value = self.call_api(f"{self.STATS}/List/{list_id}/Count/Recipients")
        if isinstance(value, bool) or not isinstance(value, int):
            raise MailUpException(f"MailUp List/{list_id}/Count/Recipients is not an integer")
        return value

    def count_message_sendings(self, list_id: int, message_id: int) -> int:
        """How many dispatches this message has. One newsletter id is sent again every day."""
        return self.count(
            f"{self.CONSOLE}/Console/List/{int(list_id)}/Email/{int(message_id)}/SendHistory"
        )

    def get_message_stats(self, message_id: int) -> Dict[str, int]:
        """Lifetime counts for one message.

        `sent` is Count/SendingRecipients (help: recipients to whom the email has been sent).
        `delivered` is that number minus Count/Bounces.
        `opened` and `clicked` are the unique readers and unique clickers: TotalElementsCount of
        List/Views and List/Clicks. Those are the numerators of the console rates
        (tasso di aperture, tasso di clic), both divided by recapitate. Count/Views and
        Count/Clicks are the totals with repeats (Aperture totali, Clic totali) and are not used.
        """
        endpoints = {
            "sent": "SendingRecipients",
            "bounced": "Bounces",
            "unsubscribed": "Unsubscriptions",
        }
        out = {}
        for key, endpoint in endpoints.items():
            value = self.call_api(f"{self.STATS}/Message/{message_id}/Count/{endpoint}")
            if isinstance(value, bool) or not isinstance(value, (int, float)) or isinstance(value, float) and value != int(value):
                raise MailUpException(
                    f"MailUp Count/{endpoint} for message {message_id} is not an integer"
                )
            out[key] = int(value)
        out["opened"] = self.count(f"{self.STATS}/Message/{message_id}/List/Views")
        out["clicked"] = self.count(f"{self.STATS}/Message/{message_id}/List/Clicks")
        out["delivered"] = max(0, out["sent"] - out["bounced"])
        return out

    def __repr__(self):
        return f"<{self.__class__.__name__}(client_id={self._client_id!r})>"


__all__ = ["MailUpClient", "MailUpException", "MailUpAuthException", "MemoryTokenStore", "parse_date",
           "format_filter_date"]
