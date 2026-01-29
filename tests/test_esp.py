import datetime
import os
import unittest
from typing import Iterable
from unittest.mock import patch, Mock
import piano_api as pa

class TestPianoESP(unittest.TestCase):

    @property
    def esp(self):
        return pa.PianoESP(os.getenv('API_KEY'), 557)

    def test_site_id(self):
        id = os.getenv('SITE_ID')
        self.assertIsNotNone(id)
        try:
            id = int(id)
            self.assertIsInstance(id, int)
            self.assertGreater(id, 0)
        except ValueError as e:
            self.fail(f'SITE_ID must be an integer {type(id)} passed')

    def test_ESP(self):
        self.assertRaises(pa.PianoClientError, pa.PianoESP, '', 123)
        self.assertRaises(pa.PianoClientError, pa.PianoESP, '', 's')

        obj = self.esp
        self.assertIsInstance(obj, pa.PianoESP)
        self.assertIsNotNone(obj.client)
        self.assertEqual(obj.client.params.get('api_key'), os.getenv('API_KEY'))

    @patch('piano_api.BaseClient.request')
    def test_get_all_campaign(self, mock_get):
        piano = self.esp

        campaigns = piano.get_all_campaign()
        self.assertIsNotNone(campaigns)

        self.assertIsInstance(campaigns, Iterable)

    @patch('httpx.Client.request')
    def test_get_campaign_stat(self, mock_get):
        piano = self.esp
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

        # Assert start_date and end_date are in params
        params = mock_get.call_args[1].get('params', {})
        self.assertIn('date_start', params)
        self.assertIn('date_end', params)
