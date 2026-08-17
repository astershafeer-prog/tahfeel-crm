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


class MetaTransientError(Exception):
    """A lead fetch that failed for a reason a retry could clear.

    Raised rather than returned so no caller can mistake it for "there was no lead
    here" — the entire point is that the webhook must NOT acknowledge these."""


# Meta error codes a retry can actually clear. 190 is the important one: an expired
# page token comes back as a plain 400, and answering 200 to that would silently bin
# every lead arriving between the expiry and someone noticing.
_RETRYABLE_META_CODES = {
    1,    # unknown transient API error
    2,    # temporary Graph API problem
    4,    # app-level rate limit
    17,   # user-level rate limit
    32,   # page-level rate limit
    190,  # access token expired/invalid — fixable, so keep the lead alive
    341,  # application limit reached
    613,  # calls-per-second limit
}

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
# One ad produces many leads, so the same handful of ads gets asked about all day.
# Process-local and never invalidated on purpose: an ad is renamed rarely, and
# a redeploy clears it anyway.
_AD_INFO_CACHE = {}

_EMPTY_AD = {'ad_id': '', 'ad_name': '', 'campaign': ''}


def fetch_ad_info(ad_id):
    """Resolve an ad to its own name and the campaign that owns it, via ads_read.

    The roundabout route is the point. Asking Meta for the LEAD's campaign_name —
    the obvious call, and what this module used to do — needs a token holding
    lead-retrieval rights. The ads token does not have them, and Meta reports that
    as a bare "object does not exist", which reads like an expired lead rather than
    a permission problem. So every lookup failed silently and every lead saved blank.

    Ads are precisely what an ads token may read, and each lead names the ad that
    produced it. Same answer, via a door we actually hold the key to.

    The ad's own name is what tells you WHICH creative a lead answered — a campaign
    runs several at once, so the campaign name alone can't. It rides along on this
    same request; there is no second call and no extra permission.

    Returns a dict of empty strings on any failure — a lost label must never cost
    us a lead."""
    if not ad_id:
        return dict(_EMPTY_AD)
    ad_id = str(ad_id)
    if ad_id in _AD_INFO_CACHE:
        return dict(_AD_INFO_CACHE[ad_id])
    try:
        from app import get_setting
        token = get_setting('ads_token', '')
    except Exception:
        token = ''
    if not token:
        return dict(_EMPTY_AD)
    try:
        r = requests.get(f'https://graph.facebook.com/v19.0/{ad_id}',
                         params={'access_token': token, 'fields': 'name,campaign{name}'}, timeout=10)
        if r.status_code != 200:
            print(f'[Meta] ad lookup failed for ad {ad_id}: {r.text[:140]}')
            return dict(_EMPTY_AD)
        body = r.json()
        info = {
            'ad_id':    ad_id,
            'ad_name':  (body.get('name') or '').strip(),
            'campaign': ((body.get('campaign') or {}).get('name') or '').strip(),
        }
    except Exception as e:
        print(f'[Meta] ad lookup failed for ad {ad_id}: {e}')
        return dict(_EMPTY_AD)
    if info['ad_name'] or info['campaign']:
        _AD_INFO_CACHE[ad_id] = dict(info)
    return info


def fetch_lead_ad_id(leadgen_id):
    """Ask Meta which ad a lead came from, using the Page token.

    Only needed when we're starting from a lead already saved without an ad_id — the
    live webhook is handed one in the notification and skips this hop."""
    token = os.environ.get('META_PAGE_ACCESS_TOKEN', '')
    if not token:
        return ''
    try:
        r = requests.get(f'https://graph.facebook.com/v19.0/{leadgen_id}',
                         params={'access_token': token, 'fields': 'ad_id'}, timeout=10)
        if r.status_code != 200:
            return ''
        return str(r.json().get('ad_id') or '')
    except Exception as e:
        print(f'[Meta] ad_id lookup failed for lead {leadgen_id}: {e}')
        return ''


def resolve_ad_info(leadgen_id=None, ad_id=None):
    """Ad id, ad name and campaign name for a lead, from whichever identifier we have.

    Two callers: the webhook, which already knows the ad, and the report's backfill
    button, which starts from a saved lead and has to ask Meta for the ad first.
    Returns empty strings if neither route arrives — the lead still saves,
    just unlabelled."""
    info = fetch_ad_info(ad_id)
    if not (info['ad_name'] or info['campaign']) and leadgen_id:
        info = fetch_ad_info(fetch_lead_ad_id(leadgen_id))
    return info


def fetch_meta_lead(leadgen_id, ad_id=''):
    """Call Meta API to get the actual lead field data.

    `ad_id` comes from the webhook notification and is only a head start — if it is
    absent the lead object usually carries one too.

    Returns the lead dict, or None when Meta says the lead is genuinely gone and
    asking again will not change that. Raises MetaTransientError for anything a
    retry might fix, which the caller turns into a non-200 so Meta re-delivers."""
    token = os.environ.get('META_PAGE_ACCESS_TOKEN', '')
    if not token:
        # Not a lost cause: someone can set the token and Meta's retry still lands.
        raise MetaTransientError('META_PAGE_ACCESS_TOKEN is not configured')

    url = f'https://graph.facebook.com/v19.0/{leadgen_id}'
    params = {
        'access_token': token,
        'fields': 'field_data,created_time,ad_id,ad_name,campaign_name,platform'
    }
    try:
        r = requests.get(url, params=params, timeout=10)
    except requests.RequestException as e:
        raise MetaTransientError(f'network error: {e}') from e

    if r.status_code != 200:
        err = {}
        try:
            err = (r.json() or {}).get('error') or {}
        except ValueError:
            pass
        code   = err.get('code')
        detail = err.get('message') or r.text[:200]
        if r.status_code >= 500 or code in _RETRYABLE_META_CODES:
            raise MetaTransientError(f'HTTP {r.status_code} (code {code}): {detail}')
        print(f'[Meta] Lead {leadgen_id} unavailable, not retrying — '
              f'HTTP {r.status_code} (code {code}): {detail}')
        return None

    try:
        data = r.json()
    except ValueError as e:
        raise MetaTransientError(f'unreadable response: {e}') from e

    # Whatever the page token withheld, go round through the ad for. One lookup
    # covers both labels, so a lead missing only its ad name costs nothing extra.
    # Still non-fatal: a lost label must never cost us a lead.
    data['ad_id'] = str(data.get('ad_id') or ad_id or '')
    if not ((data.get('campaign_name') or '').strip() and (data.get('ad_name') or '').strip()):
        info = resolve_ad_info(leadgen_id=leadgen_id, ad_id=data['ad_id'])
        data['ad_id']         = data['ad_id'] or info['ad_id']
        data['ad_name']       = (data.get('ad_name') or '').strip() or info['ad_name']
        data['campaign_name'] = (data.get('campaign_name') or '').strip() or info['campaign']
    return data


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
    from app import db, Lead, User, LeadUpdate, normalize_phone_e164

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
    # The ad is the creative the customer actually answered. Stored alongside the
    # campaign, never instead of it — Campaign ROI matches Meta's ad spend to leads
    # on the exact campaign name, so dropping it would orphan every spend row.
    ad_id        = str(raw_meta.get('ad_id') or lead_data.get('ad_id') or '')
    ad_name      = (raw_meta.get('ad_name') or '').strip()
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
        phone        = normalize_phone_e164(phone),
        phone_original = phone or None,
        email        = email,
        service      = service,
        address      = city,
        source       = 'Meta-Lead',     # managed CRM source
        sub_source   = platform,        # Facebook / Instagram
        campaign     = campaign,
        meta_ad_id   = ad_id[:50] or None,
        meta_ad_name = ad_name[:200] or None,
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

    # A lead we could not save for a reason that may clear on its own means the whole
    # delivery has to go unacknowledged — a 200 here is Meta's cue to forget the lead
    # forever, which is how paid leads were being lost to a single timeout. Meta
    # re-sends the entire payload, and the meta_lead_id check in save_lead_to_crm
    # stops the ones that did save from doubling up.
    retry_delivery = False

    for entry in payload.get('entry', []):
        for change in entry.get('changes', []):
            if change.get('field') != 'leadgen':
                continue
            lead_data  = change.get('value', {})
            leadgen_id = lead_data.get('leadgen_id')
            if not leadgen_id:
                continue

            # Meta names the ad in the notification itself — pass it through so the
            # campaign can be resolved without a second round trip to find it.
            try:
                raw_meta = fetch_meta_lead(leadgen_id, lead_data.get('ad_id', ''))
            except MetaTransientError as e:
                print(f'[Meta] Lead {leadgen_id} fetch failed, asking Meta to resend: {e}')
                retry_delivery = True
                continue
            if raw_meta is None:
                continue  # permanently gone — already logged, nothing to retry

            try:
                save_lead_to_crm(lead_data, raw_meta)
            except Exception as e:
                try:
                    from app import db
                    db.session.rollback()
                except Exception:
                    pass
                print(f'[Meta] Lead {leadgen_id} save failed, asking Meta to resend: {e}')
                retry_delivery = True

    if retry_delivery:
        # 503 rather than 500 — this is "come back later", and Meta backs off and
        # re-delivers for hours. Permanently-dead leads returned 200 above, so one
        # of those can never pin the endpoint in an endless retry loop and get the
        # whole subscription disabled.
        return 'Retry later', 503

    return 'OK', 200
