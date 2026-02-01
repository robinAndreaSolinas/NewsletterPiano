import os
from typing import Optional, Dict
from urllib.parse import urlunparse, urlencode, quote_plus
from sqlalchemy import create_engine, Executable, util, text
from sqlalchemy.orm import Session as BaseSession


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

class SessionSingleton(BaseSession):
    _instance = None

    def __new__(cls, *args, **kwargs):
        if SessionSingleton._instance is None:
            return super().__new__(cls)
        return cls._instance

    def __init__(self, connection_url:str,
                 autoflush: bool = True,
                 expire_on_commit: bool = True,
                 autobegin: bool = True,
                 twophase: bool = False,
                 binds: Optional[Dict] = None,
                 enable_baked_queries: bool = True,
                 info: Optional = None,
                 query_cls: Optional = None,
                 join_transaction_mode = "conditional_savepoint",
                 close_resets_only=0
                 ):

        if not connection_url:
            raise TypeError("connection_url is required")

        if SessionSingleton._instance is not None:
            return

        super().__init__(bind=create_engine(connection_url),
                         autoflush = autoflush,
                         expire_on_commit = expire_on_commit,
                         autobegin = autobegin,
                         twophase = twophase,
                         binds = binds,
                         enable_baked_queries = enable_baked_queries,
                         info = info,
                         query_cls = query_cls,
                         join_transaction_mode = join_transaction_mode,
                         close_resets_only = close_resets_only,
                         )
        self.engine = self.bind
        SessionSingleton._instance = self

    def execute(self, statement: str | Executable,
                params: Optional = None,
                *,
                execution_options = util.EMPTY_DICT,
                bind_arguments: Optional = None,
                _parent_execute_state: Optional = None,
                _add_event: Optional = None):

        if isinstance(statement, str):
            statement = text(statement)

        return super().execute(statement, params, execution_options=execution_options, bind_arguments=bind_arguments,
                               _parent_execute_state=_parent_execute_state, _add_event=_add_event)

    def close(self) -> None:
        super().close()
        SessionSingleton._instance = None

    @staticmethod
    def get_instance():
        if SessionSingleton._instance is None:
            raise RuntimeError("There is no session instance, please create one first")
        return SessionSingleton._instance

    def __del__(self):
        SessionSingleton._instance = None


def build_from_env():
    builder = PyDBCBuilder()
    if os.environ.get("DATABASE_URL"):
        return os.getenv('DATABESE_URL')
    try:
        builder.set_driver(os.environ.get("DB_DRIVER", "sqlite"))
        builder.set_username(os.environ.get("DB_USERNAME"))
        builder.set_password(os.environ.get("DB_PASSWORD"))
        builder.set_host(os.environ.get("DB_HOST"))
        builder.set_port(int(os.environ.get("DB_PORT")))
        builder.set_database_name(os.environ.get("DB_NAME"))
        return builder.build()
    except (ValueError, KeyError, TypeError):
        return 'sqlite:///:memory:'

session = SessionSingleton(build_from_env())

__all__ = ["SessionSingleton", "PyDBCBuilder"]