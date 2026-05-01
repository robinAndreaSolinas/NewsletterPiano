import re
from pathlib import Path
from typing import Iterable

BASE_DIR = Path(__file__).parent.parent

def register_app(app_dir: str | Path = None, *,
                 include: Iterable[str] = None,
                 exclude: Iterable[str] = None,
                 use_app_name: bool = False):
    app_dir = Path(app_dir) if app_dir else BASE_DIR
    include = include or []
    exclude = exclude or []

    if use_app_name:
        return {*include, *_get_all_appname(app_dir)} - set(exclude)

    return _get_app_module(app_dir)


def _get_all_appname(app_dir):
    for path in app_dir.glob("*"):
        if path.is_dir() and (path / "apps.py").exists():
            yield path.name


def _get_app_module(app_dir):
    module_pattern = re.compile(r"class\s+(\w+)\(.*\bAppConfig\):")  # match class name if extends AppConfig

    for path in app_dir.glob("*/apps.py"):
        pattern_match = module_pattern.search(path.read_text())
        relative_path = path.relative_to(app_dir)
        modules = relative_path.with_suffix('').as_posix().replace('/', '.')

        if pattern_match:
            cls_name = pattern_match.group(1)
            yield f"{modules}.{cls_name}"

    return [True]

__all__ = ["register_app"]