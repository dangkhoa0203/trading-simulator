"""Apply data/schema.sql to the PostgreSQL database at DATABASE_URL.

Run once against a freshly provisioned database (Supabase, Neon, RDS, whatever):
    DATABASE_URL=postgresql://user:pass@host:5432/dbname python migrate.py
"""

import os
import sys
from pathlib import Path

import psycopg2


def main():
    database_url = os.environ.get("DATABASE_URL")
    if not database_url or database_url.startswith("sqlite"):
        print("DATABASE_URL must point at a PostgreSQL database, e.g.:")
        print("  postgresql://user:pass@host:5432/dbname")
        sys.exit(1)

    schema_path = Path(__file__).resolve().parent.parent / "data" / "schema.sql"
    sql = schema_path.read_text()

    conn = psycopg2.connect(database_url)
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute(sql)
        print(f"Applied {schema_path.name} to {database_url.rsplit('@', 1)[-1]}")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
