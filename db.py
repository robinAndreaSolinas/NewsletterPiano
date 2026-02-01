from typing import Dict
from urllib.parse import urlunparse, urlencode, quote_plus

class PyDBCBuilder:
    _driver:str
    _username:str = ""
    _password:str = ""
    _host:str = ""
    _port:int = 0
    _database_name:str
    _params:Dict = {}

    def set_driver(self, driver:str):
        if not isinstance(driver, str):
            raise TypeError("Driver must be a string")
        if not driver:
            raise ValueError("There is no driver, please set first")

        self._driver = driver
        return self

    def set_username(self, username:str):
        if not isinstance(username, str):
            raise TypeError("Username must be a string")
        if not username:
            raise ValueError("There is no username, please set first")

        self._username = username
        return self

    def set_password(self, password:str):
        if not isinstance(password, str):
            raise TypeError("Password must be a string")
        if not password:
            raise ValueError("There is no password, please set first")

        self._password = password
        return self

    def set_host(self, host:str):
        if not isinstance(host, str):
            raise TypeError("Host must be a string")
        if not host:
            raise ValueError("There is no host, please set first")

        self._host = host
        return self

    def set_port(self, port:int):
        if not isinstance(port, int):
            raise TypeError("Port must be an integer")
        if not 1024 <= int(port) <= 65535:
            raise ValueError("Port is invalid")
        self._port = port
        return self

    def set_database_name(self, database_name:str):
        if not isinstance(database_name, str):
            raise TypeError("Database Name must be a string")
        if not database_name:
            raise ValueError("There is no database_name, please set first")

        self._database_name = database_name
        return self

    def set_params(self, params:Dict):
        if not isinstance(params, dict):
            raise TypeError("Params must be a dict")
        params =  {k: v for k, v in params.items() if v is not None}
        if not params:
            raise ValueError("There is no params, please set first")

        self._params = params
        return self

    def _build_netloc(self):
        username = f"{quote_plus(self._username)}" if self._username else ''
        password = f":{quote_plus(self._password, safe='*')}" if self._password and username else ''
        host = f"@{self._host}" if username else self._host
        port = f":{self._port}" if self._port else ''

        if not self._host:
            return ''

        return f"{username}{password}{host}{port}"

    def _build_params(self):
        return urlencode(self._params, doseq=True) if self._params else ''

    def build(self):
        if not getattr(self, '_driver', None):
            raise ValueError("There is no driver, please set first")
        if not getattr(self, '_database_name', None):
            raise ValueError("There is no database_name, please set first")

        driver = self._driver
        netloc = self._build_netloc()
        path = self._database_name

        if not netloc:
            netloc = path
            path = ''


        return urlunparse((self._driver, netloc, path, '', self._build_params(), ''))

    def __str__(self):
        original_password = self._password
        self._password = '***'
        build = self.build()
        self._password = original_password if original_password else ''
        return build

    def __repr__(self):
        return (
            f"PyDBCBuilder(driver={self._driver!r}, "
            f"username={self._username!r}, "
            f"password={'***' if self._password else None!r}, "
            f"host={self._host!r}, "
            f"port={self._port}, "
            f"database={self._database_name!r})"
        )

