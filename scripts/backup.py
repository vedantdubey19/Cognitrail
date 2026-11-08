"""Consistent SQLite backup for the single-owner deployment."""
import argparse
import os
from pathlib import Path
import sqlite3
from urllib.parse import quote
from sqlalchemy.engine import make_url
from app.config import Settings


def backup_database(source: Path, target: Path):
    source = source.resolve()
    if not source.is_file():
        raise ValueError('Source database is unavailable')
    target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    descriptor = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    os.close(descriptor)
    try:
        with sqlite3.connect(f'file:{quote(str(source))}?mode=ro', uri=True) as original:
            with sqlite3.connect(target) as destination:
                original.backup(destination)
                if destination.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
                    raise ValueError('Backup integrity check failed')
    except Exception:
        target.unlink(missing_ok=True)
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    url = make_url(Settings().database_url)
    if url.get_backend_name() != 'sqlite' or not url.database or url.database == ':memory:':
        parser.error('This tool requires a file-based SQLite database; use pg_dump for PostgreSQL')
    try:
        backup_database(Path(url.database), args.output)
    except (OSError, ValueError, sqlite3.Error):
        parser.exit(1, 'Backup failed. Verify the source, output permissions, and that the output does not already exist.\n')
    print('Backup created and integrity verified. Copy it to approved encrypted off-host storage.')


if __name__ == '__main__':
    main()
