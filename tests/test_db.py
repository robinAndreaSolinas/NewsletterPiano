from urllib.parse import urlunparse, urlencode

import db
import unittest

class TestPyDBCBuilder(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(db.PyDBCBuilder())
        self.assertRaises(TypeError, db.PyDBCBuilder, 5, '')
        self.builder = db.PyDBCBuilder()

    def test_set_driver(self):
        self.assertIsInstance(self.builder.set_driver('foo'), db.PyDBCBuilder)
        self.assertRaises(ValueError, self.builder.set_driver, '')
        self.assertEqual('foo', self.builder._driver)

    def test_set_username(self):
        self.assertIsInstance(self.builder.set_username('foo'), db.PyDBCBuilder)
        self.assertRaises(ValueError, self.builder.set_username, '')
        self.assertEqual('foo', self.builder._username)

    def test_set_password(self):
        self.assertIsInstance(self.builder.set_password('bar'), db.PyDBCBuilder)
        self.assertRaises(ValueError, self.builder.set_password, '')
        self.assertEqual('bar', self.builder._password)

    def test_set_host(self):
        self.assertIsInstance(self.builder.set_host('foo'), db.PyDBCBuilder)
        self.assertRaises(ValueError, self.builder.set_host, '')
        self.assertEqual('foo', self.builder._host)

    def test_set_port(self):
        self.assertIsInstance(self.builder.set_port(3502), db.PyDBCBuilder)
        self.assertRaises(TypeError, self.builder.set_port, '')
        self.assertEqual(3502, self.builder._port)
        self.assertRaises(ValueError, self.builder.set_port, -1)
        self.assertRaises(TypeError, self.builder.set_port, 'baz')
        self.assertGreaterEqual(self.builder._port, 1024) # Reserved Port
        self.assertLessEqual(self.builder._port, 65535) # Max port number

    def test_set_database_name(self):
        self.assertIsInstance(self.builder.set_database_name('foo'), db.PyDBCBuilder)
        self.assertRaises(ValueError, self.builder.set_database_name, '')
        self.assertEqual('foo', self.builder._database_name)

    def test_set_params(self):
        self.assertIsInstance(self.builder.set_params({'foo': 'bar','boo': False, 'baz':None}), db.PyDBCBuilder)
        self.assertRaises(TypeError, self.builder.set_params, '')
        self.assertRaises(ValueError, self.builder.set_params, {})
        self.assertIn('foo', self.builder._params)
        self.assertIn('boo', self.builder._params)
        self.assertNotIn('baz', self.builder._params)

    def test_build_netloc(self):
        builder = db.PyDBCBuilder()
        builder.set_username('foo')
        builder.set_password('cwsdvw')
        builder.set_host('foo')
        builder.set_port(3502)

        netloc = builder._build_netloc()
        self.assertIsInstance(netloc, str)
        self.assertEqual('foo:cwsdvw@foo:3502', netloc)

        builder._username = ''

        self.assertEqual('foo:3502', builder._build_netloc())
        builder._port = None
        self.assertEqual(builder._host, builder._build_netloc())
        builder._host = None
        self.assertEqual(str(), builder._build_netloc())

    def test_build_params(self):
        # No test for this
        pass

    def test_build(self):
        driver = 'sqlite'
        dbname = 'name'
        dbuser = 'user'
        dbpass = 'psw'
        dbhost = 'host'
        dbport = 1500
        params = {'foo': ['bar', None, 5], 'boo': 1}

        self.builder.set_driver(driver)
        self.builder.set_database_name(dbname)
        self.builder.set_username(dbuser)
        self.builder.set_password(dbpass)
        self.builder.set_port(dbport)
        self.builder.set_host(dbhost)
        self.builder.set_params(params)

        qs = urlencode(params, doseq=True)

        self.assertEqual(f'{driver}://{dbuser}:{dbpass}@{dbhost}:{dbport}/{dbname}?{qs}', self.builder.build())

        self.builder._host = None

        self.assertEqual(f'{driver}://{dbname}?{qs}', self.builder.build())
