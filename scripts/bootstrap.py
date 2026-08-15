from __future__ import annotations

from urllib.parse import urlsplit, urlunsplit

import psycopg
from psycopg import sql

from llm_central_gateway.settings import (
    DEFAULT_CONFIG_PATH,
    CaseSensitiveConfigParser,
    initialize_missing_config,
)

BUSINESS_DATABASE_NAME = "llm_gateway_business"
LITELLM_DATABASE_NAME = "llm_gateway_litellm"


def main() -> None:
    changed = initialize_missing_config()
    parser = CaseSensitiveConfigParser(interpolation=None)
    parser.read(DEFAULT_CONFIG_PATH, encoding="utf-8")
    current_uri = parser["postgres"]["POSTGRES_URI"]
    parsed = urlsplit(current_uri)
    maintenance_uri = urlunsplit((parsed.scheme, parsed.netloc, "/postgres", parsed.query, ""))
    with psycopg.connect(maintenance_uri, autocommit=True) as connection:
        for database_name in (BUSINESS_DATABASE_NAME, LITELLM_DATABASE_NAME):
            exists = connection.execute(
                "SELECT 1 FROM pg_database WHERE datname = %s", (database_name,)
            ).fetchone()
            if not exists:
                connection.execute(
                    sql.SQL("CREATE DATABASE {}").format(sql.Identifier(database_name))
                )
    parser["postgres"]["POSTGRES_URI"] = urlunsplit(
        (parsed.scheme, parsed.netloc, f"/{BUSINESS_DATABASE_NAME}", parsed.query, "")
    )
    parser["litellm"]["LITELLM_DATABASE_NAME"] = LITELLM_DATABASE_NAME
    with DEFAULT_CONFIG_PATH.open("w", encoding="utf-8") as handle:
        parser.write(handle, space_around_delimiters=False)
    DEFAULT_CONFIG_PATH.chmod(0o600)
    print(f"Configuration initialized ({len(changed)} fields added); database is ready.")


if __name__ == "__main__":
    main()
