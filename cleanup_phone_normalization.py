"""TASK 1.4 cleanup — normalize existing phone numbers to E.164 (+971...) format.

Audit finding: mixed formats in the DB — "0554342277", "+971 502721366",
"+971 0523950403" (invalid stray zero). WhatsApp sends can fail silently on
malformed numbers. New saves are now normalized automatically (see
normalize_phone_e164() in app.py); this script fixes EXISTING rows.

Only the unambiguous patterns are auto-fixed (same three the audit named, plus
a couple of clearly-safe variants — see normalize_phone_e164() docstring in
app.py for the exact list). Anything ambiguous (landlines, numbers too short,
numbers that don't start with 0/971/+, garbage values) is left untouched and
listed separately for manual review — this script never guesses a country code.

SAFE BY DEFAULT: dry-run only. Nothing is written unless you pass --write.
The as-typed value is preserved in phone_original before any change.

Covers: Customer.phone, Customer.phone2, Customer.mobile, Customer.whatsapp,
Customer.alert_whatsapp, Lead.phone, Lead.phone2.

Usage:
    python cleanup_phone_normalization.py            # dry run
    python cleanup_phone_normalization.py --write     # applies the fixes

Run against whichever DATABASE_URL is in the environment.
"""
import sys

from app import app, db, Customer, Lead, normalize_phone_e164

WRITE = '--write' in sys.argv

# (model, column name, whether to also stamp *_original — only the primary
# "phone" column has a phone_original counterpart)
TARGETS = [
    (Customer, 'phone', 'phone_original'),
    (Customer, 'phone2', None),
    (Customer, 'mobile', None),
    (Customer, 'whatsapp', None),
    (Customer, 'alert_whatsapp', None),
    (Lead, 'phone', 'phone_original'),
    (Lead, 'phone2', None),
]

with app.app_context():
    fixable = []    # (model_name, id, label, column, old, new)
    unfixable = []  # (model_name, id, label, column, value)

    for model, col, orig_col in TARGETS:
        rows = model.query.filter(getattr(model, col).isnot(None)).all()
        for row in rows:
            val = getattr(row, col)
            if not val or not str(val).strip():
                continue
            new_val = normalize_phone_e164(val)
            label = getattr(row, 'name', '') or ''
            if new_val != val:
                fixable.append((model.__name__, row.id, label, col, val, new_val, orig_col))
            else:
                # Flag anything that still doesn't look like a clean +<digits> value
                s = str(val).strip()
                looks_clean = s.startswith('+') and s[1:].replace(' ', '').isdigit()
                if not looks_clean:
                    unfixable.append((model.__name__, row.id, label, col, val))

    print('=' * 100)
    print(f'{len(fixable)} phone value(s) can be auto-fixed (unambiguous patterns only)')
    print('=' * 100)
    print(f"{'Model':<10}{'ID':<7}{'Name':<26}{'Column':<16}{'Before':<22}{'After'}")
    print('-' * 100)
    for model_name, rid, label, col, old, new, orig_col in fixable:
        print(f"{model_name:<10}{rid:<7}{label[:24]:<26}{col:<16}{old[:20]:<22}{new}")

    print()
    print('=' * 100)
    print(f'{len(unfixable)} phone value(s) could NOT be confidently classified — left untouched, needs manual review')
    print('=' * 100)
    print(f"{'Model':<10}{'ID':<7}{'Name':<26}{'Column':<16}{'Value'}")
    print('-' * 100)
    for model_name, rid, label, col, val in unfixable:
        print(f"{model_name:<10}{rid:<7}{label[:24]:<26}{col:<16}{val}")

    if not WRITE:
        print(f'\nDRY RUN — no changes made. {len(fixable)} value(s) would be normalized.')
        print('Re-run with --write to apply.')
        sys.exit(0)

    for model_name, rid, label, col, old, new, orig_col in fixable:
        model = Customer if model_name == 'Customer' else Lead
        row = model.query.get(rid)
        if not row:
            continue
        if orig_col and not getattr(row, orig_col):
            setattr(row, orig_col, old)
        setattr(row, col, new)
    db.session.commit()

    print(f'\nWROTE: {len(fixable)} value(s) normalized. As-typed values preserved in phone_original where applicable.')
