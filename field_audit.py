"""Field coverage audit — catches the "Free Zone Name" class of bug.

That bug: a field existed in the database and on the EDIT form, but was never
added to the ADD form. So every new record left it blank, and a chart built on
it silently showed nothing. Nothing crashed, so nothing flagged it.

This script compares, for each entity:
    DB columns   vs   the Add form   vs   the Edit form
and reports fields that are saved but can't be entered, or can only be entered
in one place.

Run it anytime (safe — reads files only, never touches the database):
    python field_audit.py
"""
import os
import re
import sys

BASE = os.path.dirname(os.path.abspath(__file__))
TPL = os.path.join(BASE, 'templates')

# entity -> (model class name, add-form templates, edit-form templates)
ENTITIES = {
    'Customer (Company)': ('Customer', ['add_customer_company.html'], ['edit_customer.html']),
    'Customer (Individual)': ('Customer', ['add_customer_individual.html'], ['edit_customer.html']),
    'Lead': ('Lead', ['add_lead.html'], ['edit_lead.html']),
    'Job / Task': ('Job', ['add_job.html'], ['job_detail.html']),
    'Document': ('Document', ['add_document.html'], ['edit_document.html']),
}

# Columns that are set by code, not typed by a human — not expected on any form.
INTERNAL = {
    'id', 'created_at', 'updated_at', 'created_by', 'resolved_at', 'completed_at',
    'lead_id', 'customer_id', 'employee_id', 'company_id', 'job_id', 'staff_id',
    'converted_lead_id', 'meta_lead_id', 'first_contacted_at', 'attempts',
    'finance_approved_by', 'finance_approved_at', 'cloudinary_public_id',
    'file_url', 'file_name', 'uploaded_by', 'added_by', 'is_read', 'wam_id',
    'revenue_date', 'partner_received_date', 'is_super', 'report_from',
    'password', 'active', 'on_leave',
}


def model_fields(src, cls):
    """Column names declared on a model class."""
    m = re.search(r'^class %s\(db\.Model\):(.*?)(?=^class |\Z)' % cls, src, re.S | re.M)
    if not m:
        return None
    return [f for f in re.findall(r'^\s{4}(\w+)\s*=\s*db\.Column', m.group(1), re.M)]


def form_fields(names):
    """name="..." attributes present across the given templates."""
    found = set()
    for n in names:
        p = os.path.join(TPL, n)
        if not os.path.exists(p):
            continue
        with open(p, encoding='utf-8') as fh:
            found |= set(re.findall(r'name=["\']([\w_]+)["\']', fh.read()))
    return found


def main():
    with open(os.path.join(BASE, 'app.py'), encoding='utf-8') as fh:
        src = fh.read()

    issues = 0
    print('=' * 68)
    print('FIELD COVERAGE AUDIT'.center(68))
    print('=' * 68)

    for label, (cls, add_t, edit_t) in ENTITIES.items():
        cols = model_fields(src, cls)
        if cols is None:
            print(f'\n{label}: model {cls} not found — skipped')
            continue
        cols = [c for c in cols if c not in INTERNAL]
        add, edit = form_fields(add_t), form_fields(edit_t)

        only_edit = [c for c in cols if c in edit and c not in add]
        only_add = [c for c in cols if c in add and c not in edit]
        neither = [c for c in cols if c not in add and c not in edit]

        print(f'\n{label}')
        print(f'  model: {len(cols)} user-facing columns | add form: {len(add & set(cols))} | edit form: {len(edit & set(cols))}')

        if only_edit:
            issues += len(only_edit)
            print('  [!] EDIT ONLY — blank on every new record (the Free Zone bug):')
            for c in only_edit:
                print(f'        - {c}')
        if only_add:
            issues += len(only_add)
            print('  [!] ADD ONLY — cannot be corrected later:')
            for c in only_add:
                print(f'        - {c}')
        if neither:
            print('  [ ] on no form (fine if set by code / retired):')
            print('        ' + ', '.join(neither))
        if not only_edit and not only_add:
            print('  OK — add and edit forms agree')

    print('\n' + '=' * 68)
    print(f'{issues} mismatch(es) worth a look')
    print('=' * 68)
    return 0


if __name__ == '__main__':
    sys.exit(main())
