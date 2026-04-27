from flask import Flask
from flask_login import LoginManager

from .routers import register_routers

_ = Flask(__name__)
register_routers(_)

login_manager = LoginManager(_)
login_manager.login_view = "auth.login"    # redirect se non loggato


def start(host: str = None, port: int = None, debug: bool = False,):
    _.run(host=host, port=port, debug=bool(debug))


__all__ = ["start"]

if __name__ == "__main__":
    start(debug=True)
