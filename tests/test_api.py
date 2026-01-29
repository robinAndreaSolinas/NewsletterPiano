import datetime
import os
import unittest
from json import JSONDecodeError
from typing import Iterable
from unittest.mock import patch, Mock
import requests
import piano_api as pa
from urllib.parse import urlparse


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
        return pa.ESP(os.getenv('API_KEY'), 557)

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
        self.assertRaises(pa.PianoClientError, pa.ESP, '', 123)
        self.assertRaises(pa.PianoClientError, pa.ESP, '', 's')

        obj = self.esp_object
        self.assertIsInstance(obj, pa.ESP)
        self.assertIsNotNone(obj.session)
        self.assertEqual(obj.session.params.get('api_key'), os.getenv('API_KEY'))

    def test_get_url(self):
        n_letter = self.esp_object
        url = urlparse(n_letter.get_url('/foo?bar=baz&1=1'))

        self.assertIn('/foo', url.path)
        self.assertIn(url.netloc, os.getenv('API_ENDPOINT'))

    @patch('requests.Session.request')
    def test_request(self, mock_get):
        n_letter = self.esp_object

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {'success': True}
        mock_get.return_value = mock_response

        n_letter.request('/foo', 'get', params={'bar': 'baz', 'api_key': 'dp'})

        resp_url = mock_get.call_args[0][1]

        self.assertIsNotNone(resp_url)
        self.assertIn(os.getenv("API_ENDPOINT"), resp_url)

        # test deleted api_key from params
        params = mock_get.call_args[1].get('params', {})
        self.assertNotIn('api_key', params)

    @patch('requests.Session.request')
    def test_request_error(self, mock_get):

        mock_response = Mock()
        mock_response.status_code = 500
        mock_response.json.return_value = {'success': False}
        mock_response.raise_for_status.side_effect = requests.RequestException('RAISE GENERIC EXCEPTION FOR TESTING')
        mock_get.return_value = mock_response

        n_letter = self.esp_object
        self.assertRaises(pa.PianoResponseError, n_letter.request, '/foo')

        mock_response.raise_for_status.side_effect = JSONDecodeError('RAISE GENERIC EXCEPTION FOR TESTING', doc='', pos=0)
        mock_get.return_value = mock_response

        self.assertRaises(pa.PianoResponseError, n_letter.request, '/foo')

    def test_get_all_campaign(self):
        piano = self.esp_object

        campaigns = piano.get_all_campaign()
        self.assertIsNotNone(campaigns)

        self.assertIsInstance(campaigns, Iterable)

    @patch('requests.Session.request')
    def test_get_campaign_stat(self, mock_get):
        piano = self.esp_object
        test_date = datetime.date(2026, 1, 1)
        self.assertRaises(ValueError, piano.get_campaign_stats, '', start_date=test_date, end_date=test_date)
        self.assertRaises(ValueError, piano.get_campaign_stats, 123, start_date='', end_date=test_date)
        self.assertRaises(ValueError, piano.get_campaign_stats, 123, start_date=test_date, end_date='')

        responce_mock = Mock()
        responce_mock.status_code = 200
        responce_mock.json.return_value = {'success': True}
        mock_get.return_value = responce_mock

        piano.get_campaign_stats(123, start_date=test_date, end_date=test_date)
        mock_get.assert_called_once()
        mock_get.assert_called_with('GET', f"{piano.ENDPOINT}/stats/campaigns/full/123", params={'date_start': '2026-01-01', 'date_end': '2026-01-01'})


    def test_other(self):
        pass