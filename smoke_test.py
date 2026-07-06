#!/usr/bin/env python3
"""
Tahfeel CRM — pre-deploy smoke test (safety net).

Boots the app against a throwaway SQLite database and checks the critical paths
that must never break: the app imports, the login page renders, CSRF protection
is active, login works with a token, destructive routes are POST-only, the health
probe responds, and the webhooks reject unsigned requests.

It changes NOTHING in your real database — it uses a temporary file that is
deleted at the end.

Run it before pushing:      python smoke_test.py
Exit code 0 = all good.     Exit code 1 = something is broken, do NOT deploy.
"""
import os, re, sys, json, tempfile

def main():
    tmpdb = os.path.join(tempfile.gettempdir(), 'tahfeel_smoke.db')
    if os.path.exists(tmpdb):
        os.remove(tmpdb)
    os.environ['SECRET_KEY'] = 'smoke-test-key'
    os.environ['DATABASE_URL'] = 'sqlite:///' + tmpdb.replace('\\', '/')
    os.environ.pop('META_APP_SECRET', None)
    os.environ.pop('WA_APP_SECRET', None)
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

    import app as A
    with A.app.app_context():
        A.db.create_all()
    client = A.app.test_client()

    def token(cl):
        html = cl.get('/login').get_data(as_text=True)
        m = re.search(r'var t=("(?:[^"\\]|\\.)*");', html)
        return json.loads(m.group(1)) if m else None

    def logged_in(cl):
        with cl.session_transaction() as s:
            return 'user_id' in s

    checks = []

    # Health probe
    r = client.get('/healthz')
    checks.append(('health probe returns 200', r.status_code == 200))

    # Login page renders + CSRF shim injected
    c = A.app.test_client()
    html = c.get('/login').get_data(as_text=True)
    tok = token(c)
    checks.append(('login page renders + CSRF token present', bool(tok) and 'X-CSRFToken' in html))

    # No-token login is blocked
    c1 = A.app.test_client()
    c1.post('/login', data={'email': 'admin@tahfeel.ae', 'password': 'tahfeel2026'})
    checks.append(('login without CSRF token is blocked', not logged_in(c1)))

    # Token login works (seeded default admin)
    c2 = A.app.test_client()
    t2 = token(c2)
    c2.post('/login', data={'email': 'admin@tahfeel.ae', 'password': 'tahfeel2026', 'csrf_token': t2})
    checks.append(('login with token succeeds', logged_in(c2)))

    # A destructive route is POST-only
    r = c2.get('/customers/1/delete')
    checks.append(('destructive route is POST-only (GET->405)', r.status_code == 405))

    # Webhooks reject unsigned requests (fail closed)
    r = c2.post('/webhook/meta', json={'x': 1})
    checks.append(('meta webhook fails closed without secret', r.status_code == 503))

    # find_contact executes (WhatsApp matching path)
    import whatsapp_webhook as W
    with A.app.app_context():
        W.find_contact('971500000000')
    checks.append(('whatsapp find_contact executes', True))

    if os.path.exists(tmpdb):
        try: os.remove(tmpdb)
        except OSError: pass

    print()
    ok = True
    for name, res in checks:
        print(f'[{"PASS" if res else "FAIL"}] {name}')
        ok = ok and res
    print('\n' + ('ALL CHECKS PASSED — safe to deploy.' if ok
                  else 'SOME CHECKS FAILED — do NOT deploy until fixed.'))
    return 0 if ok else 1

if __name__ == '__main__':
    sys.exit(main())
