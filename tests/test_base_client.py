from json import JSONDecodeError
from unittest.mock import patch, Mock
from urllib.parse import urlparse
import os
import unittest
import httpx

import piano_api as pa

class TestBaseClient(unittest.TestCase):

    def test_path_validator(self):
        self.assertRaises(ValueError, pa.validate_path, 'https://example.com/foo/bar')
        self.assertRaises(ValueError, pa.validate_path, '/')
        self.assertRaises(ValueError, pa.validate_path, ' ')

    def test_url_validator(self):
        self.assertRaises(ValueError, pa.validate_url, '/')
        self.assertRaises(ValueError, pa.validate_url, ' ')
        raw = 'https://example.com/foo?bar=baz'
        url = pa.validate_url(raw)
        self.assertEqual(url, raw)

    def test_endpoint(self):
        path = urlparse(os.getenv('API_ENDPOINT'))

        self.assertIn(path.scheme, ['http', 'https'])
        main_domain = path.netloc[path.netloc.find('.') + 1:]
        sub_domain = path.netloc.replace(main_domain, '').strip().strip('.')

        self.assertEqual('piano.io', main_domain)

        self.assertIn(sub_domain, ("api-esp" , "api-esp-us", "api-esp-ap", "sandbox-api-esp"))

    @property
    def client(self):
        return pa.BaseClient('pippo')

    def test_api_key(self):
        self.assertRaises(pa.PianoClientError, pa.BaseClient, ' ')

    def test_get_url(self):
        url = urlparse(pa.BaseClient.get_url('/foo?bar=baz&1=1'))

        self.assertIn('/foo', url.path)
        self.assertIn(url.netloc, os.getenv('API_ENDPOINT'))

    def test_prepare_request(self):
        self.assertRaises(ValueError, self.client._prepare_request, '/', 'get')
        self.assertRaises(ValueError, self.client._prepare_request, '/foo', 'PUT')

        preparation =self.client._prepare_request('/foo', params={'api_key': 'dp'})
        self.assertEqual(len(preparation), 3)
        method, url, kwargs = preparation
        self.assertEqual(method, 'GET')
        self.assertIn('/foo', url)
        self.assertIsNotNone(kwargs)

        self.assertNotIn('api_key', preparation[2].get('params', {}))

    @patch('httpx.AsyncClient.request')
    def test_batch(self, mock):
        response = Mock()
        response.status_code = 200
        response.json.return_value = {'success': True}
        mock.return_value = response

        self.client._batch_request(['/foo', '/bar'], params={'jonny':True})
        self.assertGreater(mock.call_count, 1)
        for call in mock.call_args_list:
            self.assertEqual(call[1].get('method'), 'GET')
            self.assertIn(os.getenv("API_ENDPOINT"), call[1].get('url'))


    @patch('httpx.Client.request')
    def test_plain_request(self, mock_get):
        n_letter = self.client

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {'success': True}
        mock_get.return_value = mock_response

        n_letter._plain_request('/foo', 'get', params={'bar': 'baz', 'api_key': 'dp'})

        resp_url = mock_get.call_args[0][1]

        self.assertIsNotNone(resp_url)
        self.assertIn(os.getenv("API_ENDPOINT"), resp_url)

        #test deleted api_key from params
        params = mock_get.call_args[1].get('params', {})
        self.assertNotIn('api_key', params)

    @patch('httpx.Client.request')
    def test_plain_request_error(self, mock_get):

        mock_response = Mock()
        mock_response.status_code = 500
        mock_response.json.return_value = {'success': False}
        mock_response.raise_for_status.side_effect = httpx.HTTPError('RAISE GENERIC EXCEPTION FOR TESTING')
        mock_get.return_value = mock_response

        n_letter = self.client
        self.assertRaises(pa.PianoResponseError, n_letter._plain_request, '/foo')

        mock_response.raise_for_status.side_effect = JSONDecodeError('RAISE GENERIC EXCEPTION FOR TESTING', doc='', pos=0)
        mock_get.return_value = mock_response

        self.assertRaises(pa.PianoResponseError, n_letter._plain_request, '/foo')
