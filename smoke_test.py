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

    # A destructive route is POST-only. A GET now gets a friendly redirect
    # (see the 405 handler) instead of a raw Werkzeug error page, so the check
    # is on the safety property — no 200, nothing deleted — not the exact code.
    r = c2.get('/customers/1/delete')
    checks.append(('destructive route refuses GET (no 200)', r.status_code != 200))

    # Webhooks reject unsigned requests (fail closed)
    r = c2.post('/webhook/meta', json={'x': 1})
    checks.append(('meta webhook fails closed without secret', r.status_code == 503))

    # find_contact executes (WhatsApp matching path)
    import whatsapp_webhook as W
    with A.app.app_context():
        W.find_contact('971500000000')
    checks.append(('whatsapp find_contact executes', True))

    # ── Bundle Management ────────────────────────────────────────────────────
    from datetime import date, timedelta as _td

    r = c2.post('/admin/vendor/add', data={'name': 'Smoke Vendor', 'category': 'Branding', 'csrf_token': t2})
    with A.app.app_context():
        vendor = A.Vendor.query.filter_by(name='Smoke Vendor').first()
    checks.append(('vendor add creates a Vendor row', vendor is not None))

    r = c2.post('/admin/bundle-template/add', data={'name': 'Smoke Bundle', 'price_aed': '2999', 'csrf_token': t2})
    with A.app.app_context():
        template = A.BundleTemplate.query.filter_by(name='Smoke Bundle').first()
    checks.append(('bundle template add creates a BundleTemplate row', template is not None))

    if template:
        c2.post(f'/admin/bundle-template/{template.id}/item/add', data={
            'service_name': 'Mandatory Item', 'category': 'Branding', 'default_due_days': '15',
            'mandatory': 'on', 'default_provider_type': 'inhouse', 'csrf_token': t2,
        })
        c2.post(f'/admin/bundle-template/{template.id}/item/add', data={
            'service_name': 'Optional Item', 'category': 'Marketing', 'default_due_days': '20',
            'default_provider_type': 'vendor', 'default_vendor_id': str(vendor.id) if vendor else '',
            'csrf_token': t2,
        })
        with A.app.app_context():
            items = A.BundleTemplateItem.query.filter_by(template_id=template.id, active=True) \
                        .order_by(A.BundleTemplateItem.sort_order).all()
        checks.append(('two template items created with ascending sort_order',
                       len(items) == 2 and items[0].sort_order < items[1].sort_order))
        checks.append(('mandatory flag round-trips correctly per item',
                       len(items) == 2 and items[0].mandatory and not items[1].mandatory))
    else:
        items = []
        checks.append(('two template items created with ascending sort_order', False))
        checks.append(('mandatory flag round-trips correctly per item', False))

    with A.app.app_context():
        cust = A.Customer(name='Smoke Test Co', customer_type='Company')
        A.db.session.add(cust)
        A.db.session.commit()
        cust_id = cust.id

    purchase_date = date.today()
    if template:
        # Assignment now happens from the standalone /bundles page, not the
        # customer's own profile — customer_id travels in the form, not the URL.
        c2.post('/bundles/assign', data={
            'customer_id': str(cust_id), 'template_id': str(template.id),
            'purchase_date': purchase_date.isoformat(), 'csrf_token': t2,
        })
    with A.app.app_context():
        cb = A.CustomerBundle.query.filter_by(customer_id=cust_id).first()
        delivs = A.BundleDeliverable.query.filter_by(customer_bundle_id=cb.id).order_by(A.BundleDeliverable.sort_order).all() if cb else []
    checks.append(('bundle assignment creates exactly 2 deliverables', len(delivs) == 2))
    checks.append(('deliverable due_date = purchase_date + default_due_days',
                   len(delivs) == 2 and delivs[0].due_date == purchase_date + _td(days=15)
                   and delivs[1].due_date == purchase_date + _td(days=20)))
    checks.append(('deliverable provider_type inherited from template item defaults',
                   len(delivs) == 2 and delivs[0].provider_type == 'inhouse' and delivs[1].provider_type == 'vendor'))

    if delivs:
        c2.post(f'/bundle-deliverables/{delivs[0].id}/update', data={
            'status': 'Completed', 'provider_type': 'inhouse', 'csrf_token': t2,
        })
        with A.app.app_context():
            d0 = A.BundleDeliverable.query.get(delivs[0].id)
            progress = A._bundle_progress(A.CustomerBundle.query.get(cb.id))
        checks.append(('completed_date auto-stamped when status set to Completed', d0.completed_date == date.today()))
        # 1 of 1 MANDATORY item done (the optional item never counts) = 100%
        checks.append(('_bundle_progress ignores non-mandatory items (100% expected)', progress == 100))
    else:
        checks.append(('completed_date auto-stamped when status set to Completed', False))
        checks.append(('_bundle_progress ignores non-mandatory items (100% expected)', False))

    if vendor:
        c2.post(f'/admin/vendor/{vendor.id}/delete', data={'csrf_token': t2})
        with A.app.app_context():
            v_after = A.Vendor.query.get(vendor.id)
        checks.append(('vendor soft-delete preserves the row', v_after is not None and v_after.active is False))
    else:
        checks.append(('vendor soft-delete preserves the row', False))

    r = c2.get('/bundles')
    list_html = r.get_data(as_text=True)
    checks.append(('bundle list page renders and shows the seeded customer',
                   r.status_code == 200 and 'Smoke Test Co' in list_html))

    if cb:
        r = c2.get(f'/bundles/{cb.id}')
        detail_html = r.get_data(as_text=True)
        checks.append(('bundle detail page renders and shows its deliverables',
                       r.status_code == 200 and 'Mandatory Item' in detail_html and 'Optional Item' in detail_html))
    else:
        checks.append(('bundle detail page renders and shows its deliverables', False))

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
