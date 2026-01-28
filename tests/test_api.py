import os
import unittest
from unittest.mock import patch, Mock
import piano_api as pa
from urllib.parse import urlparse, parse_qs


class TestAPI(unittest.TestCase):

    def test_endpoint(self):
        path = urlparse(os.getenv('API_ENDPOINT'))

        self.assertIn(path.scheme, ['http', 'https'])
        main_domain = path.netloc[path.netloc.find('.') + 1:]
        sub_domain = path.netloc.replace(main_domain, '').strip().strip('.')

        self.assertEqual('piano.io', main_domain)

        self.assertIn(sub_domain, ("api-esp" , "api-esp-us", "api-esp-ap", "sandbox-api-esp"))

    @property
    def esp_object(self):
        return pa.ESP(os.getenv('API_KEY'))

    def test_site_id(self):
        id = os.getenv('SITE_ID')
        self.assertIsNotNone(id)
        try:
            id = int(id)
            self.assertIsInstance(id, int)
            self.assertGreater(id, 0)
        except ValueError as e:
            self.fail(f'SITE_ID must be an integer {type(id)} passed')

    def test_api_key(self):
        key = os.getenv('API_KEY')
        self.assertIsNotNone(key)

    def test_Piano(self):
        self.assertRaises(pa.PianoClientError, pa.ESP, '')

    def test_injection_key(self):
        esp = self.esp_object
        self.assertIsNotNone(esp._api_key)
        self.assertRaises(ValueError, esp._inject_api_key, '')
        self.assertIn('api_key', esp._inject_api_key('foo'))

    def test_get_url(self):
        n_letter = pa.ESP(os.getenv('API_KEY'))
        url = urlparse(n_letter.get_url('/foo?bar=baz&1=1'))

        self.assertIn('/foo', url.path)
        self.assertIn(url.netloc, os.getenv('API_ENDPOINT'))
        self.assertIn('api_key', url.query)

    @patch('requests.request')
    def test_request(self, mock_get):
        n_letter = self.esp_object

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {'success': True}
        mock_get.return_value = mock_response

        resp = n_letter.request('/foo', 'get')

        mock_response.url = mock_get.call_args[0][1]
        resp.url = mock_response.url

        self.assertIsNotNone(resp.url)
        self.assertIn(os.getenv("API_ENDPOINT"), resp.url)
        self.assertIn('api_key', resp.url)
    
    @patch('requests.request')
    def test_request_error(self, mock_get):
        mock_get.side_effect = pa.PianoResponseError("Network error")
        n_letter = self.esp_object
        self.assertRaises(pa.PianoResponseError, n_letter.request, '/foo')

    def test_other(self):
        pass