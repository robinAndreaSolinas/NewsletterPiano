import datetime
import logging
import os
from json import JSONDecodeError
from mimetypes import knownfiles
from urllib.parse import urlparse
from httpx import Client, AsyncClient, HTTPError
import asyncio

http_client_params = {
    "http2": True,
    "follow_redirects": True,
    "headers": {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
    }
}
logger = logging.getLogger(__name__)

class PianoAPIError(Exception):
    """Base exception class for Piano API errors."""
    pass


class PianoClientError(PianoAPIError):
    """Exception class for Piano Client errors."""
    pass


class PianoRequestException(PianoClientError):
    """Exception class for Piano Client errors."""
    pass


class PianoResponseError(PianoClientError):
    """Exception raised for authentication-related errors."""
    pass


class PianoAuthenticationError(PianoClientError):
    """Exception raised for authentication-related errors."""
    pass


def validate_path(path: str):
    path = path.strip().strip('/')
    if not path:
        raise ValueError(f"Path cannot be empty, or start with a slash: {path}")

    # Parse the path to validate it's relative (no scheme like 'http://' or netloc like 'example.com')
    parsed = urlparse(path)
    if parsed.scheme or parsed.netloc:
        raise ValueError("Path must be relative (no scheme like 'http(s)://' or netloc like 'example.com')")
    return path.strip('/')

def validate_url(url: str):
    parsed = urlparse(url.strip().strip('/'))

    if not parsed.scheme or not parsed.netloc:
        raise ValueError(f"Invalid URL format: {url}")

    return parsed.geturl()

async def _fetch_url_with_semaphore(url, *, client, semaphore, method='GET', **kwargs):
    async with semaphore:
        try:
            return await client.request(method=method, url=url)
        except HTTPError as e:
            logger.error(f"{url} => Response Exception {e}")
            return None

async def _fetch_urls(urls:list[str], **kwargs):
    semaphore = asyncio.Semaphore(75)

    method = kwargs.pop("method") if "method" in kwargs else "GET"

    async with AsyncClient(**kwargs) as client:

        tasks = [_fetch_url_with_semaphore(url, client=client, semaphore=semaphore, method=method) for url in urls]

        responses = []

        for response in  await asyncio.gather(*tasks, return_exceptions=True):
            if response is not None:
                try:
                    response.raise_for_status()
                    if response is not None:
                        responses.append(response)
                except HTTPError as exc:
                    logger.error(f"{exc.request.url} => [Response Exception] {exc}")

        return responses


class BaseClient(object):

    ENDPOINT = os.getenv("API_ENDPOINT").strip('/')

    def __init__(self, api_key: str,*, client=None, logger=None, **kwargs):

        if not api_key or not api_key.strip():
            raise PianoClientError("API key cannot be empty")

        self.logger = logger if logger else logging.getLogger(__name__)

        kwargs.update(http_client_params)
        self.client = client if client else Client(**kwargs)

        self.client.params = {"api_key": api_key}

    @staticmethod
    def get_url(path: str, path_validator=None):
        path_validator = path_validator or validate_path
        # Combine base endpoint with the complete path (including query string)
        return f"{BaseClient.ENDPOINT}/{path_validator(path)}"

    def _prepare_request(self,path:str|list[str], method:str = None, **kwargs):
        # Normalize method to uppercase for consistent validation
        method = method.upper() if method else "GET"
        if not method in ["GET", "POST"]:
            raise ValueError("Invalid method")

        if isinstance(path, list):
            pathilst = path
            path = []
            for p in pathilst:
                path.append(self.get_url(p))
        elif isinstance(path, str):
            path = str(path).strip('/') if path else None
            path = self.get_url(path)
        else:
            raise ValueError("Invalid url")

        if "api_key" in kwargs.get('params', {}):
            del kwargs['params']["api_key"]

        return method, path, kwargs

    def _plain_request(self, path: str, method: str = "GET", **kwargs):
        method,path,kwargs = self._prepare_request(path, method, **kwargs)

        try:
            response = self.client.request(method,path,**kwargs)
            response.raise_for_status()
            return response.json()
        except HTTPError as e:
            raise PianoResponseError(f"{e}")
        except JSONDecodeError as e:
            raise PianoResponseError(f"{e}")

    def _batch_request(self,paths:list[str], method="GET", **kwargs):
        method,paths,kwargs = self._prepare_request(paths, method, **kwargs)

        params = {'api_key': self.client.params.get('api_key'), **kwargs.pop('params', {})}

        ## CHANGE CLIENT TO ASYNC
        # Update api_key for all requests
        resposces = asyncio.run(_fetch_urls(paths, method=method, params=params, **kwargs))
        try:
            return list(resposce.json() for resposce in resposces)
        except JSONDecodeError as e:
            raise PianoResponseError(f"{e}")

    def request(self, path: str|list[str], method:str="GET", **kwargs):
        if isinstance(path, list):
            return self._batch_request(path, method, **kwargs)
        return self._plain_request(path, method, **kwargs)


class PianoESP(BaseClient):

    def __init__(self, api_key: str, site_id: int, **kwargs):
        super().__init__(api_key, **kwargs)

        if not site_id or int(site_id) <= 0:
            raise PianoClientError("Site ID cannot be empty")

        self.site_id = site_id

    def get_all_campaign(self, /, filter_active: bool = True):
        try:
            campaign = self.request(f"/publisher/list/{self.site_id}")
        except PianoResponseError as e:
            self.logger.exception(f"Error to get campaings: {e}")
            return []

        return [ active for active in campaign.get('lists', []) if active.get('Active') ] if filter_active else campaign.get('lists', [])

    def get_campaign_stats(self,c_id: int|list[int], *, start_date: datetime.date, end_date: datetime.date):
        BASE_PATH = "/stats/campaigns/full"
        c_id = c_id if isinstance(c_id, list) else [c_id]
        urls = []

        for cid in c_id:
            if not cid or not isinstance(cid, int) or cid <= 0:
                raise ValueError("Invalid list id")
            urls.append(f"{BASE_PATH}/{cid}")

        urls = urls[0] if len(urls) == 1 else urls

        if not start_date or not isinstance(start_date, datetime.date):
            raise ValueError("Invalid start date")
        if not end_date or not isinstance(end_date, datetime.date):
            raise ValueError("Invalid end date")

        params = {"date_start": start_date.strftime("%Y-%m-%d"), "date_end": end_date.strftime("%Y-%m-%d")}

        return self.request(urls, params=params)

if __name__ == "__main__":
    client = PianoESP(os.getenv("API_KEY"), int(os.getenv("SITE_ID")))
    ids = [item.get("Id") for item in client.get_all_campaign()]
    stats = client.get_campaign_stats(ids, start_date=datetime.date(2026, 1, 1), end_date=datetime.date(2026, 1, 31))
    print(stats)