from __future__ import annotations
import abc
import datetime
from typing import Any

from httpx import Client, HTTPStatusError
from lib.utility import camel_to_snake


class APIException(Exception):
    pass

class APIClientException(APIException):
    pass

class PianoESPException(APIException):
    pass


class AbstractAPIClient(abc.ABC):

    ENDPOINT = "https://api-esp.piano.io"

    def __init__(self, site_id: int, api_key: str, *, http_client=None):
        self.site_id = site_id
        self._api_key = api_key
        self._http_client = http_client or Client(base_url=AbstractAPIClient.ENDPOINT, params={"api_key": self._api_key})

    def call_api(self,path, method="GET", **kwargs):

        if method.upper() not in ("GET", "POST", "PUT", "DELETE"):
            raise ValueError("Invalid method")
        try:
            response = self._http_client.request(method.upper(), f"{path}", **kwargs)
            response.raise_for_status()
            return response.json()
        except HTTPStatusError as e:
            raise APIClientException(e)

    def __repr__(self):
        return f"<{self.__class__.__name__}({' '.join(f'{k}={v!r}' for k, v in self.__dict__.items() if not k.startswith("_"))})>"


class ClientESP(AbstractAPIClient):

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

# to prevent multiple creation for the same instance
class RegistryMeta(abc.ABCMeta):
    """
    Metaclasse che mantiene un registro interno di tutte le istanze create.
    Supporta ricerca per ID e la sintassi `if Classe in [lista_id]`.
    """

    def __init__(cls, name: str, bases: tuple, attrs: dict) -> None:
        super().__init__(name, bases, attrs)
        cls._instances: dict[int, Any] = {}  # registro privato per classe
        cls._last_id: int | None = None  # supporto a `if C in [...]`

    def __call__(cls, *args: Any, **kwargs: Any) -> Any:
        instance = super().__call__(*args, **kwargs)
        if hasattr(instance, "id"):
            cls._instances[instance.id] = instance
            cls._last_id = instance.id
        return instance

    def find(cls, target_id: int) -> Any:
        """Cerca un'istanza per ID. Solleva ValueError se non trovata."""
        if target_id not in cls._instances:
            raise ValueError(
                f"Errore: {cls.__name__} con ID {target_id} non trovato nel registro."
            )
        return cls._instances[target_id]

    def all(cls) -> list[Any]:
        """Restituisce tutte le istanze registrate."""
        return list(cls._instances.values())

    def __eq__(cls, other: Any) -> bool:
        """
        Permette `if C in [1, 2, 3]`: Python itera la lista e valuta
        `elemento == C`; int.__eq__(C) ritorna NotImplemented, quindi Python
        prova il riflesso `C.__eq__(elemento)` che arriva qui.
        """
        if isinstance(other, int):
            return cls._last_id == other
        return super().__eq__(other)

    def __hash__(cls) -> int:
        return super().__hash__()

    def __repr__(cls) -> str:
        ids = list(cls._instances.keys())
        return (
            f"<class '{cls.__name__}' | "
            f"istanze={ids} | ultimo_id={cls._last_id}>"
        )


class Campaign(AbstractAPIClient, metaclass=RegistryMeta):

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
           return Campaign.find(int(norm.get("id")))
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


class MailingList(AbstractAPIClient, metaclass=RegistryMeta):

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
                    campaigns.append(Campaign.find(id))
                except ValueError:
                    pass
        return campaigns

    @classmethod
    def from_raw_response(cls, response: dict, api_key: str):
        norm = {camel_to_snake(k): v for k, v in response.items()}
        try:
           return Campaign.find(int(norm.get("id")))
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

    def get_subscribers(self, date_start: datetime.date = None, date_end: datetime.date = None):
        date_end = date_end or datetime.date.today()
        if not date_start:
            raise ValueError("date_start is required use ClientESP(...).get_all_subscribers() to get all subscribers for lists")
        return self.call_api(f"/stats/squads/full/{self.id}", params={"date_start": date_start, "date_end": date_end})

    def __repr__(self):
        return f"<{self.__class__.__name__}({' '.join(f'{k}={v!r}' for k, v in self.__dict__.items() if not k.startswith("_"))} mailing_lists={[str(m) if isinstance(m, Campaign) else m for m in self.mailing_lists]})>"

    def __str__(self):
        return f"<{self.__class__.__name__}(ID={self.id!r})>"
