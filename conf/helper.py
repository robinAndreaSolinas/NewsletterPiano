import logging
import os
import re
from pathlib import Path
from typing import Iterable

BASE_DIR = Path(__file__).parent.parent

def register_app(apps_dir: str | Path = None, *,
                 include: Iterable[str] = None,
                 exclude: Iterable[str] = None,
                 use_app_name: bool = False) -> set[str]:
    """
    Scan a directory and return the set of Django app modules or names to register in INSTALLED_APPS.

    :param apps_dir: Root directory to scan for Django apps. Defaults to BASE_DIR.
    :param include: Explicit apps to include, merged with the discovered ones.
    :param exclude: Apps to remove from the final result.
    :param use_app_name: If ``True``, yields folder names (e.g. ``"myapp"``).
                         If ``False``, yields the dotted path of the AppConfig class
                         (e.g. ``"myapp.apps.MyAppConfig"``).
    :return: Set of strings ready to be used in INSTALLED_APPS, with exclusions already applied.
    """
    apps_dir = Path(apps_dir) if apps_dir else BASE_DIR
    include = set(include or [])
    exclude = set(exclude or [])

    if use_app_name:
        include |= set(_get_apps_name(apps_dir))
    else:
        include |= set(_get_apps_module(apps_dir))
    logging.info(f"Registering apps: {include}")
    return include - exclude

def _get_apps_name(apps_dir):
    """
    Yield the name of every subdirectory that contains an ``apps.py`` file.

    :param apps_dir: Root directory to scan.
    :return: Directory name (e.g. ``"myapp"``).
    """
    for path in apps_dir.glob("*"):
        if path.is_dir() and (path / "apps.py").exists():
            yield path.name

def _get_apps_module(apps_dir):
    """
    Yield the full dotted path of every AppConfig class found inside ``apps.py`` files.

    Uses a regex to detect classes that extend ``AppConfig``, then builds the dotted
    module path relative to ``apps_dir``.

    :param apps_dir: Root directory to scan.
    :return: Dotted path of the AppConfig subclass (e.g. ``"myapp.apps.MyAppConfig"``).
    """
    module_pattern = re.compile(r"class\s+(\w+)\(.*\bAppConfig\):")  # match class name if extends AppConfig

    for path in apps_dir.glob("*/apps.py"):
        pattern_match = module_pattern.search(path.read_text())
        relative_path = path.relative_to(apps_dir)
        modules = relative_path.with_suffix('').as_posix().replace('/', '.')

        if pattern_match:
            cls_name = pattern_match.group(1)
            yield f"{modules}.{cls_name}"

    return [True]


def allowed_hosts_env(is_debug: bool = False,/) -> set[str]:
    """
    Return the set of allowed hosts to use in ``ALLOWED_HOSTS``.

    In debug mode returns ``{"*"}`` to allow any host.
    In production reads the ``ALLOWED_HOSTS`` and ``HOST`` environment variables,
    discarding empty values and the wildcard ``"*"`` (with a warning log).

    :param is_debug: If ``True``, skip all checks and return ``{"*"}``. Positional-only.
    :return: Set of allowed host strings.
    :raises None:
    .. warning::
        Logs a warning if the wildcard ``"*"`` is found among the configured hosts in production.
    """
    if is_debug: # allow all hosts if in debug mode
        return set('*')

    h = set(os.getenv("ALLOWED_HOSTS", "").replace(" ", "").split(","))
    h.add(os.getenv("HOST", "0.0.0.0"))
    h = {v.strip() for v in h}

    if "*" in h:
        logging.warning(f"wilcard '*' not allowed in prod, discarding")

    h -= {"", None, "*"}

    return h

__all__ = {"register_app", "allowed_hosts_env"}
