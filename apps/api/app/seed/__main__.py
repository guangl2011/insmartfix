"""`python -m app.seed`: load the TEST_PLAN §5 fixtures (FR-10.2). Used by `make seed`.

Refuses `ENV=production`. Test-account passwords come from `SEED_PASSWORD` (local: your shell or
`infra/.env`; CI: generated per run; staging: the GitHub `staging` environment secret). They are
never committed.
"""

import os
import sys

from app import clock
from app.auth.passwords import hash_password
from app.db.session import get_sessionmaker
from app.seed.load import load
from app.settings import get_settings

MIN_PASSWORD_LENGTH = 12


def main() -> int:
    settings = get_settings()
    if settings.env == "production":
        print("seed: refusing to load test fixtures into ENV=production", file=sys.stderr)
        return 2
    password = os.environ.get("SEED_PASSWORD", "")
    if len(password) < MIN_PASSWORD_LENGTH:
        print(
            f"seed: set SEED_PASSWORD (>= {MIN_PASSWORD_LENGTH} chars) for the test accounts",
            file=sys.stderr,
        )
        return 2
    with get_sessionmaker(settings.database_url)() as session, session.begin():
        load(session, now=clock.now(), password=password, hash_password=hash_password)
    print(f"seed: TEST_PLAN §5 fixtures loaded (ENV={settings.env})", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
