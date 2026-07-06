# meta_webhook.py
# Receives Meta Lead Ads in real-time and saves to Tahfeel CRM
# ─────────────────────────────────────────────────────────────

import os
import hmac
import hashlib
import requests
from datetime import datetime, timedelta, timezone
from flask import Blueprint, request, jsonify

meta_bp = Blueprint('meta', __name__)

DUBAI_TZ = timezone(timedelta(hours=4))

def now_dubai():
    return datetime.now(DUBAI_TZ).replace(tzinfo=None)


# ── Round-robin assignment ────────────────────────────────────────────────────
def get_next_sales_staff(db, User, Lead):
    """Assign the new lead to the active sales staff member who was assigned a lead
    LEAST recently. This is true round-robin that survives restarts/redeploys and
    works across all gunicorn workers (state lives in the DB, not in memory)."""
    staff = User.query.filter(
        User.active == True,
        User.on_leave == False,
        User.role == 'sales'
    ).order_by(User.id).all()

    if not staff:
        # Fallback: any active sales staff regardless of leave
        staff = User.query.filter(
            User.active == True,
            User.role == 'sales'
        ).order_by(User.id).all()

    if not staff:
        return None

    def last_lead_id(s):
        last = Lead.query.filter_by(assigned_to=s.id).order_by(Lead.id.desc()).first()
        return last.id if last else 0

    # The staff member whose most-recent lead is oldest (or who has none) is next up.
    # Ties resolve to lowest User.id (staff list is already id-ordered, min is stable).
    return min(staff, key=last_lead_id)


# ── Fetch lead details from Meta API ─────────────────────────────────────────
def fetch_meta_lead(leadgen_id):
    """Call Meta API to get the actual lead field data."""
    token = os.environ.get('META_PAGE_ACCESS_TOKEN', '')
    url = f'https://graph.facebook.com/v19.0/{leadgen_id}'
    params = {
        'access_token': token,
        'fields': 'field_data,created_time,ad_name,campaign_name,platform'
    }
    try:
        r = requests.get(url, params=params, timeout=10)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        print(f'[Meta] Failed to fetch lead {leadgen_id}: {e}')
        return None


def parse_lead_fields(field_data):
    """Convert Meta field_data list into a clean dict."""
    mapping = {}
    for item in field_data:
        name = item.get('name', '').lower().strip()
        values = item.get('values', [])
        value = values[0] if values else ''
        mapping[name] = value
    return mapping


def save_lead_to_crm(lead_data, raw_meta):
    """Create Lead record in CRM from parsed Meta data."""
    from app import db, Lead, User, LeadUpdate

    fields = parse_lead_fields(raw_meta.get('field_data', []))

    # Map Meta fields to CRM fields
    name         = fields.get('full_name', fields.get('name', 'Unknown'))
    phone        = fields.get('whatsapp_number', fields.get('phone_number', ''))
    email        = fields.get('email', '')
    service      = fields.get('what_service_are_you_looking_for?',
                   fields.get('service', ''))
    city         = fields.get('city', '')
    pref_time    = fields.get('preferred_time_for_call:', '')
    platform     = raw_meta.get('platform', 'Facebook')
    campaign     = raw_meta.get('campaign_name', '')
    meta_lead_id = str(lead_data.get('leadgen_id', ''))

    # Avoid duplicate leads
    existing = Lead.query.filter_by(meta_lead_id=meta_lead_id).first()
    if existing:
        print(f'[Meta] Duplicate lead ignored: {meta_lead_id}')
        return None

    # Round-robin assignment (least-recently-assigned active sales staff)
    assigned_user = get_next_sales_staff(db, User, Lead)

    remarks = f'Preferred call time: {pref_time}' if pref_time else ''

    lead = Lead(
        name         = name.title(),
        phone        = phone,
        email        = email,
        service      = service,
        address      = city,
        source       = 'Meta-Lead',     # managed CRM source
        sub_source   = platform,        # Facebook / Instagram
        campaign     = campaign,
        lead_type    = 'New',
        status       = 'New',
        remarks      = remarks,
        assigned_to  = assigned_user.id if assigned_user else None,
        meta_lead_id = meta_lead_id,
        created_at   = now_dubai(),
        due_date     = now_dubai() + timedelta(days=1),
    )
    db.session.add(lead)
    db.session.flush()  # get lead.id

    # CRM notification — shows in lead activity history
    notif = LeadUpdate(
        lead_id    = lead.id,
        stage      = 'New — Meta Lead',
        remark     = (
            f'Auto-received from Meta Ads ({platform}). '
            f'Service: {service or "Not specified"}. '
            f'{remarks}'
        ).strip(),
        staff_name = 'System (Meta Ads)',
        created_at = now_dubai(),
    )
    db.session.add(notif)
    db.session.commit()

    assigned_name = assigned_user.name if assigned_user else 'Nobody (no sales staff available)'
    print(f'[Meta] ✓ Lead saved: {name} → assigned to {assigned_name}')

    # Flow A — auto-greet the new lead on WhatsApp (approved template).
    # No-ops safely if WhatsApp isn't configured or the lead has no phone.
    try:
        from whatsapp_webhook import notify_new_lead
        notify_new_lead(lead)
    except Exception as e:
        print(f'[Meta] WhatsApp greet skipped: {e}')

    return lead


# ── Webhook verification ──────────────────────────────────────────────────────
@meta_bp.route('/webhook/meta', methods=['GET'])
def meta_verify():
    """Meta calls this once to verify your webhook URL."""
    mode      = request.args.get('hub.mode')
    token     = request.args.get('hub.verify_token')
    challenge = request.args.get('hub.challenge')
    expected  = os.environ.get('META_VERIFY_TOKEN', '')

    if mode == 'subscribe' and token == expected:
        print('[Meta] Webhook verified ✓')
        return challenge, 200
    return 'Forbidden', 403


# ── Webhook receiver ──────────────────────────────────────────────────────────
@meta_bp.route('/webhook/meta', methods=['POST'])
def meta_receive():
    """Receives lead notification from Meta instantly."""
    # Verify the request is genuinely from Meta. Fail CLOSED: if no secret is
    # configured we reject everything rather than accept unsigned/spoofable posts.
    app_secret = os.environ.get('META_APP_SECRET', '')
    if not app_secret:
        print('[Meta] META_APP_SECRET not configured — rejecting webhook (fail closed)')
        return 'Server not configured', 503
    sig_header   = request.headers.get('X-Hub-Signature-256', '')
    expected_sig = 'sha256=' + hmac.new(
        app_secret.encode(), request.data, hashlib.sha256
    ).hexdigest()
    if not hmac.compare_digest(sig_header, expected_sig):
        print('[Meta] Invalid signature — rejected')
        return 'Unauthorized', 401

    payload = request.get_json(silent=True)
    if not payload:
        return 'OK', 200

    for entry in payload.get('entry', []):
        for change in entry.get('changes', []):
            if change.get('field') != 'leadgen':
                continue
            lead_data  = change.get('value', {})
            leadgen_id = lead_data.get('leadgen_id')
            if not leadgen_id:
                continue

            raw_meta = fetch_meta_lead(leadgen_id)
            if raw_meta:
                save_lead_to_crm(lead_data, raw_meta)

    return 'OK', 200
