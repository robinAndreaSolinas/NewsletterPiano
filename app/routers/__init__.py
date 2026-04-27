import logging
from pathlib import Path
import importlib
from flask import Blueprint

ROUTERS_DIR = Path(__file__).resolve().parent
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

def register_routers(app):

    for file in sorted(ROUTERS_DIR.glob("*.py")):

        if file.stem.startswith("_"):
            logger.debug(f"{file.stem} file ignored: Start with '_'")
            continue

        module_name = f"{__package__ or ROUTERS_DIR.stem}.{file.stem}"
        try:
            logger.debug(f"try to importing {module_name} ...")
            module = importlib.import_module(module_name)
        except ImportError as e:
            logger.error(f"{module_name!r} ignored: Error {e}")
            raise

        if not hasattr(module, "router") or (
                hasattr(module, "router") and not isinstance(module.router, Blueprint)
        ):
            logger.info(f"{module_name!r} ignored: No valid router found")
            continue

        prefix = getattr(module.router, "url_prefix", None) or (
            f"/{module.router.name}" if module.router.name else f"/{file.stem}")

        # print(module.router.name, module.router.url_prefix)
        try:
            app.register_blueprint(module.router, url_prefix=prefix)
            logger.info(f" ### {module_name!r} register routes => {prefix}")
        except ValueError as e:
                logger.error(f"{module_name!r} ignored: {e}\n{prefix} NOT IMPORTED")

__all__ = [
    "register_routers",
]