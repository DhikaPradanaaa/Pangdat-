from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parents[1]
WORKSPACE_ROOT = PROJECT_ROOT.parent
load_dotenv(PROJECT_ROOT / ".env")


def env(name: str, default: str = "") -> str:
    return os.getenv(name, default)


MYSQL_HOST = env("MYSQL_HOST", "127.0.0.1")
MYSQL_PORT = int(env("MYSQL_PORT", "3306"))
MYSQL_USER = env("MYSQL_USER", "root")
MYSQL_PASSWORD = env("MYSQL_PASSWORD", "")
OLTP_DB = env("MYSQL_OLTP_DATABASE", "olist_oltp")
STAGING_DB = env("MYSQL_STAGING_DATABASE", "olist_staging")
DWH_DB = env("MYSQL_DWH_DATABASE", "olist_dwh")

RAW_SOURCE_DIR = Path(env("RAW_SOURCE_DIR", str(WORKSPACE_ROOT / "output" / "olist_data_quality_final" / "raw")))
QUALITY_SCRIPT = WORKSPACE_ROOT / "scripts" / "clean_olist.py"
SQLITE_DWH_SCRIPT = WORKSPACE_ROOT / "scripts" / "build_olist_dwh.py"
MYSQL_EXPORT_SCRIPT = WORKSPACE_ROOT / "scripts" / "export_mysql_dump.py"
SQLITE_SCHEMA = WORKSPACE_ROOT / "dwh" / "schema.sql"
MYSQL_SCHEMA = WORKSPACE_ROOT / "mysql" / "schema_mysql.sql"
MYSQL_CLIENT = Path(env("MYSQL_CLIENT", r"C:\laragon\bin\mysql\mysql-8.0.30-winx64\bin\mysql.exe"))
RUNTIME_DIR = PROJECT_ROOT / "runtime"
LOG_DIR = PROJECT_ROOT / "logs"
