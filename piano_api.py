import datetime
import logging
import os
from json import JSONDecodeError
from urllib.parse import urlparse, parse_qs, urlencode
import requests

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


class ESP:
    """
    Piano API client for making authenticated requests to the Piano API endpoint.

    The API endpoint is configured via the API_ENDPOINT environment variable.
    """

    # Base API endpoint loaded from environment
    ENDPOINT = os.getenv("API_ENDPOINT").strip('/')

    def __init__(self, api_key: str, site_id: int, logger=None):
        """
        Initialize Piano API client with authentication key.

        Args:
            api_key: The API key used for authenticating requests

        Raises:
            PianoClientError: If the API key is empty or contains only whitespace
        """
        if not api_key or not api_key.strip():
            raise PianoClientError("API key cannot be empty")

        if not site_id or int(site_id) <= 0:
            raise PianoClientError("Site ID cannot be empty")

        self.logger = logger if logger else logging.getLogger(__name__)

        self.site_id = site_id

        self.session = requests.Session()
        self.session.params = {"api_key": api_key}

    def get_url(self, path: str):
        """
        Composes a fully qualified URL with base endpoint, path, and API key authentication.

        Args:
            path: Relative API path with optional query parameters (e.g., 'users/list?limit=10')

        Returns:
            Complete URL string with base endpoint, path, and api_key parameter

        Raises:
            ValueError: If path is empty, starts with slash after stripping, or contains a domain/protocol
        """

        path = path.strip('/')
        if not path:
            raise ValueError(f"Path cannot be empty, or start with a slash: {path}")

        # Parse the path to validate it's relative (no scheme like 'http://' or netloc like 'example.com')
        parsed = urlparse(path)
        if parsed.scheme or parsed.netloc:
            raise ValueError("Path must not contain a domain or protocol")

        # Combine base endpoint with the complete path (including query string)
        return f"{self.ENDPOINT}/{parsed.geturl()}"

    def request(self, url: str, method: str = "GET", **kwargs):
        """
        Execute an HTTP request to the Piano API.

        Args:
            url: Relative API path (will be composed into full URL with authentication)
            method: HTTP method to use, either 'GET' or 'POST' (case-insensitive, defaults to 'GET')

        Returns:
            requests.Response object containing the API response

        Raises:
            ValueError: If method is not GET or POST, or if url is empty
        """
        # Normalize method to uppercase for consistent validation
        method = method.upper()
        if not method in ["GET", "POST"]:
            raise ValueError("Invalid method")
        if not url:
            raise ValueError("Invalid url")
        # Compose the full authenticated URL
        url = self.get_url(url)
        
        if "api_key" in kwargs.get('params', {}):
            del kwargs['params']["api_key"]

        try:
            response = self.session.request(method, url, **kwargs)
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            raise PianoResponseError(f"{e}")
        except JSONDecodeError as e:
            raise PianoResponseError(f"{e}")


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

        return self.request(f"//stats/campaigns/full/{c_id}", params=params)


