import datetime
import logging
import os
from json import JSONDecodeError
from urllib.parse import urlparse
from httpx import Client, AsyncClient, HTTPError
import asyncio

http_client_params = {
    "http2": True,
    "follow_redirects": True,
    "headers": {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36 (SeoAgent)",
        "X-Agent": "SeoAgent-images/1.0"
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
    if "method" in kwargs:
        method = kwargs.pop("method")
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

def request_batch(urls, **kwargs):

    kwargs.update(http_client_params)
    return asyncio.run(_fetch_urls(urls, **kwargs))


class BaseClient(object):

    ENDPOINT = os.getenv("API_ENDPOINT").strip('/')

    def __init__(self, api_key: str,*, client=None, logger=None, **kwargs):

        if not api_key or not api_key.strip():
            raise PianoClientError("API key cannot be empty")

        self.logger = logger if logger else logging.getLogger(__name__)

        self.client = client if client else Client(**http_client_params, **kwargs)

        self.client.params = {"api_key": api_key}

    @staticmethod
    def get_url(path: str, path_validator=None):
        path_validator = path_validator or validate_path
        # Combine base endpoint with the complete path (including query string)
        return f"{BaseClient.ENDPOINT}/{path_validator(path)}"

    def _plain_request(self, path: str, method: str = "GET", **kwargs):

        # Normalize method to uppercase for consistent validation
        method = method.upper()
        if not method in ["GET", "POST"]:
            raise ValueError("Invalid method")
        if not path:
            raise ValueError("Invalid url")

        # Compose the full authenticated URL
        url = self.get_url(path)
        if "api_key" in kwargs.get('params', {}):
            del kwargs['params']["api_key"]

        try:
            response = self.client.request(method, url, **kwargs)
            response.raise_for_status()
            return response.json()
        except HTTPError as e:
            raise PianoResponseError(f"{e}")
        except JSONDecodeError as e:
            raise PianoResponseError(f"{e}")

    def _batch_request(self,paths:list[str], method="GET", **kwargs):

        # Normalize method to uppercase for consistent validation
        method = method.upper()
        if not method in ["GET", "POST"]:
            raise ValueError("Invalid method")

        valid_url = []
        for path in paths:
            try:
                valid_url.append(self.get_url(path))
            except ValueError as e:
                self.logger.error(f"Invalid URL: {e}")

        ## CHANGE CLIENT TO ASYNC
        # Update api_key for all requests
        return request_batch(valid_url, method=method, params={'api_key': self.client.params.get('api_key'), **kwargs.get('params', {})})

    def request(self, path: str|list[str], **kwargs):
        if isinstance(path, list):
            return self._batch_request(path, **kwargs)
        return self._plain_request(path, **kwargs)


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

    def get_campaign_stats(self,c_id: int, *, start_date: datetime.date, end_date: datetime.date):
        if not c_id or not isinstance(c_id, int) or c_id <= 0:
            raise ValueError("Invalid list id")
        if not start_date or not isinstance(start_date, datetime.date):
            raise ValueError("Invalid start date")
        if not end_date or not isinstance(end_date, datetime.date):
            raise ValueError("Invalid end date")

        params = {"date_start": start_date.strftime("%Y-%m-%d"), "date_end": end_date.strftime("%Y-%m-%d")}

        return self.request(f"/stats/campaigns/full/{c_id}", params=params)
