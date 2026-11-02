"""Seed fixtures (TEST_PLAN §5): `python -m app.seed`.

Stub at M0. The backend engineer fills this in M1 with the Midtown Properties tenant, Marco Rossi,
Ana Lee, Zed (other tenant), RTU-04 / AHU-NEW-01 and the SLA-offset offers. Test-account passwords
come from the environment (GitHub `staging` environment secrets), never from the repo.
"""

import sys


def main() -> int:
    print("seed: no fixtures yet — implemented in M1 (TEST_PLAN §5)", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
