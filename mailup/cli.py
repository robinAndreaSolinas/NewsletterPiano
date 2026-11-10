"""Shared behaviour for the MailUp management commands."""
from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

from django.conf import settings
from django.core.management.base import CommandError

from mailup.tasks import parse_day


def parse_iso_date(value: str, label: str):
    if value is None:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError as e:
        raise CommandError(f"{label} non valida: '{value}'. Formato atteso: YYYY-MM-DD") from e


def parse_compact_date(value: str, label: str):
    if value is None:
        return None
    try:
        return parse_day(value)
    except ValueError as e:
        raise CommandError(f"{label} non valida: '{value}'. Formato atteso: YYYYMMDD") from e


def ensure_not_future(day, today):
    if day > today:
        raise CommandError(f"{day.isoformat()} è nel futuro")


def confirm(command, summary: str) -> bool:
    command.stdout.write(summary)
    if command.dry_run:
        return False
    if getattr(command, "yes", False):
        return True
    if not sys.stdin.isatty():
        raise CommandError("Terminale non interattivo: aggiungi --yes per eseguire, oppure --dry-run.")
    command.stdout.write("Scrivi si per procedere.")
    answer = input().strip().lower()
    if answer not in {"si", "sì", "yes"}:
        command.stdout.write(command.style.WARNING("Nessuna modifica."))
        return False
    return True


def write_backup(payload: dict) -> Path:
    directory = Path(settings.DATA_DIR) / "mailup-backups"
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"mailup-{datetime.now().strftime('%Y%m%d%H%M%S')}.json"
    path.write_text(json.dumps(payload, default=str, indent=2))
    return path
