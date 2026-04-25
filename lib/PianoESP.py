from __future__ import annotations
import datetime
from typing import Dict, Any

from httpx import Client, HTTPStatusError
import logging
from lib.utils import camel_to_snake, Singleton, AbstractAPIClient


class APIException(Exception):
    pass


class APIClientException(APIException):
    pass


class PianoESPException(APIException):
    pass


class ESPAPIClient(AbstractAPIClient):

    ENDPOINT = "https://api-esp.piano.io"

    def __init__(self, site_id: int, api_key: str, *, http_client=None, logger: logging.Logger = None):
        self.site_id = site_id
        self._api_key = api_key
        self._http_client = http_client or Client(base_url=self.ENDPOINT, params={"api_key": self._api_key})
        self._logger = logger or logging.getLogger(__class__.__name__)

    def call_api(self, path: str, method: str = "GET", **kwargs) -> Dict[str, Any]:
        if method.upper() not in ("GET", "POST", "PUT", "DELETE"):
            raise ValueError(f"Invalid HTTP method: '{method}'. Allowed methods are: GET, POST, PUT, DELETE")

        try:
            response = self._http_client.request(method.upper(), f"{path}", **kwargs)
            response.raise_for_status()
            return response.json()
        except HTTPStatusError as e:
            raise APIClientException(e)

    def __repr__(self):
        return f"<{self.__class__.__name__}({' '.join(f'{k}={v!r}' for k, v in self.__dict__.items() if not k.startswith("_"))})>"


class ClientESP(Singleton, ESPAPIClient):

    def get_all_campaigns(self, only_active: bool = True, /):
        res = self.call_api(f"/publisher/list/{self.site_id}").get("lists", [])
        return [
            Campaign.from_raw_response(raw, api_key=self._api_key)
            for raw in res
            if raw.get("Active") or not only_active
        ]

    def get_all_mailing_lists(self, only_active: bool = True, /):
        res = self.call_api(f"/publisher/pub/{self.site_id}/sq")

        return [
            MailingList.from_raw_response(raw, api_key=self._api_key)
            for raw in res
            if raw.get("Active") or not only_active
        ]

    def get_all_subscribers(self, ml: MailingList | list[MailingList]):
        sq_ids = [ml.list_id] if isinstance(ml, MailingList) else [_.list_id for _ in ml]
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
        self.types = type
        self.stage = stage

        super().__init__(site_id, api_key)

    @classmethod
    def from_raw_response(cls, response: dict, api_key: str):
        norm = {camel_to_snake(k): v for k, v in response.items()}
        try:
           return Campaign.get_instance(int(norm.get("id")))
        except ValueError:
            return cls(
                norm.pop("id"),
                norm.pop("name"),
                active=norm.pop("active"),
                friendly_name=norm.pop("friendly_name"),
                schedule_type=norm.pop("schedule_type"),
                site_id=norm.pop("publisher_id"),
                api_key=api_key,
                types=norm.pop("type"),
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

        super().__init__(site_id, api_key)

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
           return Campaign.get_instance(int(norm.get("id")))
        except ValueError:
            return cls(
                id=norm.pop("id"),
                name=norm.pop("name"),
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