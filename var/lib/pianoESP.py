from __future__ import annotations
import datetime
import functools
import time
from typing import Dict, Any, List
import httpx
from httpx import Client, HTTPStatusError, Timeout
import logging
from var.lib.utils import camel_to_snake, Singleton, APIClientInterface, APIException


class PianoESPException(APIException):
    pass


def timeout_backoff(max_retries: int = 3, multiplier: float = 2, *, base_delay = None):
    logger = logging.getLogger(__name__)
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            delay = base_delay
            for iter in range(1, max_retries + 1):
                try:
                    logger.debug(f"trying {func.__name__} with {args ,kwargs}")
                    return func(*args, **kwargs)
                except httpx.TimeoutException as e:

                    kwargs["timeout"] = kwargs.pop("timeout", 5) + (multiplier * iter)

                    logger.info(f"Timeout exception: {e} => "
                                f"{args[0]} call {args[1] if len(args) > 1 else kwargs.get('path', '')!r}: "
                                f"{iter}/{max_retries} next retry with timeout {kwargs.get('timeout')!r}")

                    if base_delay is not None:
                        time.sleep(delay)
                        delay *= multiplier

                    if iter == max_retries + 1:
                        raise

            return func(*args, **kwargs)
        return wrapper

    return decorator


class ESPAPIClient(APIClientInterface):

    ENDPOINT = "https://api-esp.piano.io"

    def __init__(self, site_id: int, api_key: str, *, http_client=None, logger: logging.Logger = None):
        self.site_id = site_id
        self._api_key = api_key
        self._http_client = http_client or Client(base_url=self.ENDPOINT, timeout=10, params={"api_key": self._api_key})
        self._logger = logger or logging.getLogger(f"{__name__}.{self.__class__.__name__}")

    @timeout_backoff(max_retries=10, multiplier=2)
    def call_api(self, path: str, method: str = "GET", **kwargs) -> Dict[str, Any]:
        logger = self._logger.parent.getChild(f"{__class__.__name__}")

        if method.upper() not in ("GET", "POST", "PUT", "DELETE"):
            logger.error(f"Invalid HTTP method: {method!r}")
            raise ValueError(f"Invalid HTTP method: {method!r}")

        try:
            response = self._http_client.request(method.upper(), f"{path}", **kwargs)
            logger.info(f"API call: {method.upper()} {path} -> {response.status_code}")
            response.raise_for_status()
            return response.json()
        except HTTPStatusError as e:
            raise PianoESPException(e)

    def __repr__(self):
        return f"<{self.__class__.__name__}({' '.join(f'{k}={v!r}' for k, v in self.__dict__.items() if not k.startswith("_"))})>"


class ClientESP(ESPAPIClient):

    def __init__(self, site_id: int, api_key: str, *, http_client=None, logger: logging.Logger = None):
        super().__init__(site_id, api_key, http_client=http_client, logger=logger)

    def get_all_campaigns(self, only_active: bool = True, /) -> list[Campaign]:
        res = self.call_api(f"/publisher/list/{self.site_id}").get("lists", [])
        return [
            Campaign.from_raw_response(raw, api_key=self._api_key)
            for raw in res
            if raw.get("Active") or not only_active
        ]

    def get_all_mailing_lists(self, only_active: bool = True, /) -> list[MailingList]:
        res = self.call_api(f"/publisher/pub/{self.site_id}/sq")
        return [
            MailingList.from_raw_response(raw, api_key=self._api_key)
            for raw in res
            if raw.get("Active") or not only_active
        ]

    def get_all_subscribers(self, ml: MailingList | List[MailingList]) -> Dict[str, Any]:
        sq_ids = [ml.id] if isinstance(ml, MailingList) else [_.id for _ in ml]
        return self.call_api(f"/publisher/pub/{self.site_id}/sq/subscribers", method="POST", json={"sqIds": sq_ids})


    def __str__(self):
            return f"<{self.__class__.__name__}(ID={self.site_id!r})>"


class Campaign(Singleton, ESPAPIClient):

    def __init__(self,
                 id: int,
                 name: str = None,
                 *,
                 site_id: int,
                 active: bool = None,
                 friendly_name: str = None,
                 schedule_type: str = None,
                 api_key: str,
                 type: int = None,
                 stage: int = None,
                 **kwargs):
        self.id = id
        self.name = name.strip() if name else None
        self.active = bool(active)
        self.friendly_name = friendly_name.strip() if friendly_name else None
        self.schedule_type = schedule_type.strip() if schedule_type else None
        self.type = type
        self.stage = stage

        ESPAPIClient.__init__(self, site_id, api_key)

    @classmethod
    def from_raw_response(cls, response: dict, api_key: str):
        norm = {camel_to_snake(k): v for k, v in response.items()}
        try:
           return Campaign.get_instance(norm.get("id"))
        except ValueError:
            return cls(
                norm.pop("id"),
                norm.pop("name"),
                active=norm.pop("active"),
                friendly_name=norm.pop("friendly_name"),
                schedule_type=norm.pop("schedule_type"),
                site_id=norm.pop("publisher_id"),
                api_key=api_key,
                type=norm.pop("type"),
                stage=norm.pop("stage")
            )

    def get_mailing_list(self):
        res = self.call_api(f"/publisher/pub/{self.site_id}/ml/{self.id}/sq")

        return [
            MailingList.from_raw_response(m, api_key=self._api_key)
            for m in res
        ]

    def get_stats(self, date_start: datetime.date, date_end: datetime.date = None):
        if not date_end:
            date_end = datetime.date.today()
            self._logger.info(f"No date_end provided, using today's date({date_end}) as fallback")

        return self.call_api(f"/stats/campaigns/full/{self.id}", params={"date_start": date_start, "date_end": date_end})

    def __str__(self):
        return f"<{self.__class__.__name__}(ID={self.id!r})>"


class MailingList(Singleton, ESPAPIClient):

    def __init__(self,
                 id: int,
                 name:str = None,
                 *,
                 active: bool = None,
                 internal_name: str = None,
                 hide_on_sub_page: bool = None,
                 mailing_lists: list[int] = None,
                 site_id: int,
                 api_key: str,
                 **kwargs):
        self.id = id
        self.name = name
        self.mailing_lists = mailing_lists
        self.active = bool(active)
        self.internal_name = internal_name.strip() if internal_name else None
        self.hide_on_sub_page = bool(hide_on_sub_page)

        ESPAPIClient.__init__(self, site_id, api_key)

    @property
    def linked_campaigns(self):
        campaigns = []
        if self.mailing_lists:
            for id in self.mailing_lists:
                try:
                    campaigns.append(Campaign.get_instance(id))
                except ValueError:
                    pass
        return campaigns

    @classmethod
    def from_raw_response(cls, response: dict, api_key: str):
        norm = {camel_to_snake(k): v for k, v in response.items()}
        try:
           return MailingList.get_instance(norm.get("id"))
        except ValueError:
            return cls(
                norm.pop("id"),
                norm.pop("name"),
                active=norm.pop("active"),
                internal_name=norm.pop("internal_name"),
                hide_on_sub_page=norm.pop("hide_on_sub_page"),
                mailing_lists=norm.pop("mailing_lists"),
                site_id=norm.pop("publisher_id"),
                api_key=api_key,
            )

    def get_stats(self, date_start: datetime.date, date_end: datetime.date = None):
        date_end = date_end or datetime.date.today()
        if not date_start:
            raise ValueError("date_start is required use ClientESP(...).get_all_subscribers() to get all subscribers for lists")
        return self.call_api(f"/stats/squads/full/{self.id}", params={"date_start": date_start, "date_end": date_end})

    def __repr__(self):
        return f"<{self.__class__.__name__}({' '.join(f'{k}={v!r}' for k, v in self.__dict__.items() if not k.startswith("_"))})>"

    def __str__(self):
        return f"<{self.__class__.__name__}(ID={self.id!r})>"


__all__ = ["ClientESP", "Campaign", "MailingList"]