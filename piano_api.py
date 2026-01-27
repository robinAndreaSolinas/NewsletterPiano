import os
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


class PianoAuthenticationError(PianoClientError):
    """Exception raised for authentication-related errors."""
    pass


class Piano:
    """
    Piano API client for making authenticated requests to the Piano API endpoint.

    The API endpoint is configured via the API_ENDPOINT environment variable.
    """

    # Base API endpoint loaded from environment
    ENDPOINT = os.getenv("API_ENDPOINT").strip('/')

    def __init__(self, api_key: str):
        """
        Initialize Piano API client with authentication key.

        Args:
            api_key: The API key used for authenticating requests

        Raises:
            PianoClientError: If the API key is empty or contains only whitespace
        """
        if not api_key or not api_key.strip():
            raise PianoClientError("API key cannot be empty")

        self._api_key = api_key

    def _inject_api_key(self, path: str):
        """
        Injects the API key into the query string of the given path.

        Args:
            path: URL path with optional query parameters

        Returns:
            URL string with api_key parameter added to the query string
        """
        path = path.strip('/')
        if not path:
            raise ValueError(f"Path cannot be empty, or start with a slash: {path}")

        parsed = urlparse(path)

        qs = parse_qs(parsed.query)
        qs["api_key"] = [self._api_key]

        return parsed._replace(query=urlencode(qs)).geturl()

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

        # Inject API key into the query string
        path = self._inject_api_key(path)

        # Parse the path to validate it's relative (no scheme like 'http://' or netloc like 'example.com')
        parsed = urlparse(path)
        if parsed.scheme or parsed.netloc:
            raise ValueError("Path must not contain a domain or protocol")

        # Combine base endpoint with the complete path (including query string)
        return f"{self.ENDPOINT}/{parsed.geturl()}"

    def request(self, url: str, method: str = "GET"):
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
        # Execute the HTTP request using the requests library
        try:
            response = requests.request(method, url)
            response.raise_for_status()
            return response
        except Exception as e:
            raise PianoAPIError(f"Error executing request to {url}: {e}")
