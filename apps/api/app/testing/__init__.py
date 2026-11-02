"""Test-only routes. Mounted only when FAKE_CLOCK=1 and ENV in {local, test, ci} (D10 H-7).

The production Docker stage deletes this package, so `import app.testing` fails there (T-AUTH-18).
"""
