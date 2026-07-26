"""TASK 1.5 cleanup — reformat existing Emirates ID numbers to dashed format.

Audit finding: the same doc type stored dashed and undashed
(784-1975-25261309 vs 784196632341309). Emirates ID numbers currently only
live on Owner.eid_no (Document rows have no number field).

Only reformats entries that are UNAMBIGUOUSLY a valid Emirates ID: exactly 15
digits once separators are stripped, starting with "784". Those get rewritten
to 784-XXXX-XXXXXXX-X. Anything else (wrong length, doesn't start with 784,
blank) is left completely untouched and listed for manual review — this
script never guesses or truncates a number.

SAFE BY DEFAULT: dry-run only. Nothing is written unless you pass --write.

Usage:
    python cleanup_eid_formatting.py            # dry run
    python cleanup_eid_formatting.py --write     # applies the reformatting
"""
import re
import sys

from app import app, db, Owner

WRITE = '--write' in sys.argv


def reformat(digits):
    return f'{digits[0:3]}-{digits[3:7]}-{digits[7:14]}-{digits[14:15]}'


with app.app_context():
    owners = Owner.query.filter(Owner.eid_no.isnot(None)).all()
    fixable = []    # (id, name, old, new)
    review = []     # (id, name, value, reason)

    for o in owners:
        val = (o.eid_no or '').strip()
        if not val:
            continue
        digits = re.sub(r'\D', '', val)
        target = reformat(digits) if len(digits) == 15 and digits.startswith('784') else None
        if target and target != val:
            fixable.append((o.id, o.name, val, target))
        elif not target:
            reason = ('does not start with 784' if len(digits) == 15
                      else f'{len(digits)} digit(s), expected 15')
            review.append((o.id, o.name, val, reason))

    print('=' * 90)
    print(f'{len(fixable)} Emirates ID(s) can be reformatted to 784-XXXX-XXXXXXX-X')
    print('=' * 90)
    print(f"{'Owner ID':<10}{'Name':<28}{'Before':<24}{'After'}")
    print('-' * 90)
    for oid, name, old, new in fixable:
        print(f"{oid:<10}{(name or '')[:26]:<28}{old:<24}{new}")

    print()
    print('=' * 90)
    print(f'{len(review)} Emirates ID(s) need manual review (not a valid 15-digit 784-prefixed number)')
    print('=' * 90)
    print(f"{'Owner ID':<10}{'Name':<28}{'Value':<24}{'Reason'}")
    print('-' * 90)
    for oid, name, val, reason in review:
        print(f"{oid:<10}{(name or '')[:26]:<28}{val:<24}{reason}")

    if not WRITE:
        print(f'\nDRY RUN — no changes made. {len(fixable)} value(s) would be reformatted.')
        print('Re-run with --write to apply.')
        sys.exit(0)

    for oid, name, old, new in fixable:
        o = Owner.query.get(oid)
        if o:
            o.eid_no = new
    db.session.commit()

    print(f'\nWROTE: {len(fixable)} Emirates ID(s) reformatted.')
