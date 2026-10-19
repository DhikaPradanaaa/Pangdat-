from __future__ import annotations

import os
import subprocess
from pathlib import Path
from urllib.parse import quote_plus

import mysql.connector
from sqlalchemy import create_engine

from config import MYSQL_CLIENT, MYSQL_HOST, MYSQL_PASSWORD, MYSQL_PORT, MYSQL_USER


def connect(database: str | None = None):
    return mysql.connector.connect(
        host=MYSQL_HOST,
        port=MYSQL_PORT,
        user=MYSQL_USER,
        password=MYSQL_PASSWORD,
        database=database,
        charset="utf8mb4",
        autocommit=False,
        allow_local_infile=True,
    )


def engine(database: str):
    password = quote_plus(MYSQL_PASSWORD)
    user = quote_plus(MYSQL_USER)
    return create_engine(
        f"mysql+mysqlconnector://{user}:{password}@{MYSQL_HOST}:{MYSQL_PORT}/{database}?charset=utf8mb4",
        pool_pre_ping=True,
    )


def run_sql_file(path: Path) -> None:
    command = [
        str(MYSQL_CLIENT),
        f"--host={MYSQL_HOST}",
        f"--port={MYSQL_PORT}",
        f"--user={MYSQL_USER}",
        "--default-character-set=utf8mb4",
        f"--execute=source {path.resolve().as_posix()}",
    ]
    environment = os.environ.copy()
    if MYSQL_PASSWORD:
        environment["MYSQL_PWD"] = MYSQL_PASSWORD
    subprocess.run(command, check=True, env=environment)


def scalar(query: str, database: str | None = None, params: tuple = ()):
    connection = connect(database)
    try:
        cursor = connection.cursor()
        cursor.execute(query, params)
        return cursor.fetchone()[0]
    finally:
        connection.close()
