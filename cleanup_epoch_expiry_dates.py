"""TASK 1.1 cleanup — null out placeholder/epoch expiry dates on Document rows.

Audit finding: /customers/282 showed an Emirates ID "expiring 08 Sep 1970 EXPIRED".
That's not a real expiry — it's a NULL-ish placeholder that got saved as a real
date (blank date input defaulting to epoch, or a bad import). The app code now
treats any Document.expiry_date before year 2000 as "not set" everywhere (see
`has_valid_expiry()` / `MIN_VALID_EXPIRY_YEAR` in app.py), but existing bad rows
in the database still hold the bogus date until cleaned up.

This script finds Document rows with expiry_date < 2000-01-01 and sets them to
NULL — the same state a normal "not set" document is already in.

SAFE BY DEFAULT: dry-run only. Nothing is written unless you pass --write.

Usage:
    python cleanup_epoch_expiry_dates.py            # dry run — lists affected rows, writes nothing
    python cleanup_epoch_expiry_dates.py --write     # applies the fix (sets expiry_date = NULL)

Run against whichever DATABASE_URL is in the environment. For production
(Railway Postgres), set DATABASE_URL before running — do NOT run --write
against production without having reviewed the dry-run list first.
"""
import sys
from datetime import datetime

from app import app, db, Document, MIN_VALID_EXPIRY_YEAR

WRITE = '--write' in sys.argv

with app.app_context():
    cutoff = datetime(MIN_VALID_EXPIRY_YEAR, 1, 1)
    bad = (Document.query
           .filter(Document.expiry_date.isnot(None), Document.expiry_date < cutoff)
           .order_by(Document.expiry_date).all())

    if not bad:
        print('No Document rows with expiry_date before {} — nothing to clean up.'.format(
            MIN_VALID_EXPIRY_YEAR))
        sys.exit(0)

    print('=' * 96)
    print(f'{len(bad)} document(s) with a pre-{MIN_VALID_EXPIRY_YEAR} expiry_date (placeholder, not a real date)')
    print('=' * 96)
    print(f"{'Doc ID':<8}{'Customer':<30}{'Doc Type':<24}{'Owner Name':<24}{'Expiry (current)'}")
    print('-' * 96)
    for d in bad:
        cust = (d.customer.name if d.customer else '') or ''
        print(f"{d.id:<8}{cust[:28]:<30}{(d.doc_type or '')[:22]:<24}{(d.owner_name or '')[:22]:<24}{d.expiry_date}")
    print('-' * 96)

    if not WRITE:
        print(f'\nDRY RUN — no changes made. {len(bad)} row(s) would be set to expiry_date = NULL.')
        print('Re-run with --write to apply.')
        sys.exit(0)

    for d in bad:
        d.expiry_date = None
    db.session.commit()

    print(f'\nWROTE: {len(bad)} row(s) updated — expiry_date set to NULL.')
    print('These documents will now show as "Not set" instead of a computed date,')
    print('and are excluded from health-score / expired-count / alert logic.')
