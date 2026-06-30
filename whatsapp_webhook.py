# whatsapp_webhook.py
# Tahfeel WhatsApp bot — Phase 1
# ─────────────────────────────────────────────────────────────
# Receives WhatsApp messages (Meta Cloud API), logs them to the CRM
# against the matching lead/customer, and sends a smart menu auto-reply.
# Also exposes notify_new_lead() so a new CRM lead is greeted on WhatsApp
# (Flow A) using an approved template.
#
# Re-uses the same proven pattern as meta_webhook.py:
#   - signature-verified webhook (X-Hub-Signature-256, same app secret)
#   - Graph API calls with a permanent/temporary access token
#   - all state in the DB, so it survives restarts and works across workers
# ─────────────────────────────────────────────────────────────

import os
import re
import hmac
import hashlib
import requests
from datetime import datetime, timedelta, timezone
from flask import Blueprint, request

wa_bp = Blueprint('whatsapp', __name__)

DUBAI_TZ = timezone(timedelta(hours=4))
def now_dubai():
    return datetime.now(DUBAI_TZ).replace(tzinfo=None)

GRAPH = 'https://graph.facebook.com/v19.0'

# ── Config (Railway env vars) ────────────────────────────────────────────────
def _cfg(key, default=''):
    return os.environ.get(key, default)

def _flag(key, default='false'):
    """Truthy env flag. SAFE-OFF by default — nothing is sent unless explicitly enabled."""
    return _cfg(key, default).strip().lower() in ('1', 'true', 'yes', 'on')

# ── Phone helpers ─────────────────────────────────────────────────────────────
def normalize_phone(p):
    """Reduce any phone to comparable digits (drop +, spaces, dashes, leading 0)."""
    if not p:
        return ''
    d = re.sub(r'\D', '', str(p))
    return d

def _match_key(p):
    """Last 9 digits — robust match across +971 / 0 / 00971 prefixes."""
    d = normalize_phone(p)
    return d[-9:] if len(d) >= 9 else d


# ── Graph API: send ───────────────────────────────────────────────────────────
def _send(payload):
    token   = _cfg('WA_ACCESS_TOKEN')
    phone_id = _cfg('WA_PHONE_NUMBER_ID')
    if not token or not phone_id:
        print('[WA] Not configured (WA_ACCESS_TOKEN / WA_PHONE_NUMBER_ID missing) — skip send')
        return None
    url = f'{GRAPH}/{phone_id}/messages'
    headers = {'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'}
    try:
        r = requests.post(url, headers=headers, json=payload, timeout=15)
        if r.status_code >= 300:
            print(f'[WA] Send failed {r.status_code}: {r.text[:300]}')
            return None
        data = r.json()
        wam = (data.get('messages') or [{}])[0].get('id')
        return wam
    except Exception as e:
        print(f'[WA] Send error: {e}')
        return None

def send_text(to, body):
    """Free-form text — ONLY allowed inside the 24h customer-service window."""
    return _send({
        'messaging_product': 'whatsapp',
        'to': normalize_phone(to),
        'type': 'text',
        'text': {'body': body},
    })

def send_template(to, template_name, params=None, lang='en'):
    """Business-initiated message — required for first contact (Flow A)."""
    components = []
    if params:
        components = [{
            'type': 'body',
            'parameters': [{'type': 'text', 'text': str(p)} for p in params],
        }]
    payload = {
        'messaging_product': 'whatsapp',
        'to': normalize_phone(to),
        'type': 'template',
        'template': {
            'name': template_name,
            'language': {'code': lang},
        },
    }
    if components:
        payload['template']['components'] = components
    return _send(payload)


# ── DB logging ────────────────────────────────────────────────────────────────
def find_contact(wa_number):
    """Match an incoming WhatsApp number to an existing Lead or Customer.
    Returns (lead_id, customer_id) — either may be None."""
    from app import Lead, Customer
    key = _match_key(wa_number)
    if not key:
        return None, None
    lead_id = customer_id = None
    # Leads: phone or phone2
    for lead in Lead.query.filter(Lead.phone.isnot(None)).all():
        if _match_key(lead.phone) == key or (lead.phone2 and _match_key(lead.phone2) == key):
            lead_id = lead.id
            break
    # Customers: phone / phone2 / mobile / whatsapp
    for c in Customer.query.all():
        for f in (c.phone, c.phone2, c.mobile, c.whatsapp):
            if f and _match_key(f) == key:
                customer_id = c.id
                break
        if customer_id:
            break
    return lead_id, customer_id

def log_message(wa_id, direction, body, msg_type='text', wam_id=None,
                contact_name=None, handled_by='bot', status=None,
                lead_id=None, customer_id=None):
    """Persist one message row. Auto-links to lead/customer if not supplied."""
    from app import db, WhatsAppMessage
    if lead_id is None and customer_id is None:
        lead_id, customer_id = find_contact(wa_id)
    row = WhatsAppMessage(
        wa_id        = normalize_phone(wa_id),
        contact_name = contact_name,
        direction    = direction,
        body         = body,
        msg_type     = msg_type,
        wam_id       = wam_id,
        status       = status,
        handled_by   = handled_by,
        lead_id      = lead_id,
        customer_id  = customer_id,
        created_at   = now_dubai(),
    )
    db.session.add(row)
    db.session.commit()
    return row


# ── Auto-reply brain (Phase 1: menu). Phase 2 swaps this for Claude. ──────────
WELCOME = (
    "Hello and welcome to *Tahfeel* 🇦🇪 — your partner for business setup in Dubai.\n\n"
    "How can we help you today? Reply with a number:\n"
    "1️⃣  New business license\n"
    "2️⃣  Visa services\n"
    "3️⃣  Speak to an agent\n\n"
    "Or just type your question and our team will assist you."
)
MENU_REPLIES = {
    '1': ("Great choice! 🏢 Tahfeel handles *new business licenses* — mainland, "
          "free zone and offshore. Tell us your planned activity and we'll guide you "
          "on the best setup, cost and timeline. A specialist will follow up shortly."),
    '2': ("✈️ We arrange *visas* — investor, partner, employment and family. "
          "Let us know who the visa is for and we'll share the requirements. "
          "A specialist will follow up shortly."),
    '3': ("👍 Connecting you with one of our agents now. "
          "Please share your name and what you need, and the assigned team member "
          "will reply here shortly."),
}

def _is_greeting(text):
    t = (text or '').strip().lower()
    return t in ('hi', 'hello', 'hey', 'start', 'salam', 'assalam',
                 'assalamualaikum', 'hai', 'menu', 'help') or t == ''

def decide_reply(wa_id, text, is_first):
    """Return the bot's reply string (or None to stay silent)."""
    t = (text or '').strip()
    if t in MENU_REPLIES:
        return MENU_REPLIES[t]
    if is_first or _is_greeting(t):
        return WELCOME
    # Unknown free text → acknowledge + re-show menu once
    return (
        "Thanks for your message — a Tahfeel team member will get back to you shortly. 🙏\n\n"
        "Meanwhile, reply *1* (new license), *2* (visa) or *3* (agent)."
    )


# ── Incoming message handling ─────────────────────────────────────────────────
def _already_seen(wam_id):
    from app import WhatsAppMessage
    if not wam_id:
        return False
    return WhatsAppMessage.query.filter_by(wam_id=wam_id).first() is not None

def handle_incoming(msg, contacts):
    from app import db, WhatsAppMessage
    wam_id = msg.get('id')
    if _already_seen(wam_id):
        return  # Meta retries — never double-process
    wa_id = msg.get('from')
    mtype = msg.get('type', 'text')
    if mtype == 'text':
        body = (msg.get('text') or {}).get('body', '')
    elif mtype in ('button', 'interactive'):
        body = (msg.get('button') or {}).get('text') or \
               (((msg.get('interactive') or {}).get('button_reply') or {}).get('title')) or ''
    else:
        body = f'[{mtype} message]'

    # profile name (if WhatsApp shared it)
    cname = None
    for c in (contacts or []):
        if normalize_phone(c.get('wa_id')) == normalize_phone(wa_id):
            cname = (c.get('profile') or {}).get('name')
            break

    # Is this the very first inbound from this number?
    is_first = WhatsAppMessage.query.filter_by(
        wa_id=normalize_phone(wa_id), direction='in').first() is None

    # 1) log the inbound (always — so it shows in the CRM inbox even when the bot is muted)
    log_message(wa_id, 'in', body, msg_type=mtype, wam_id=wam_id, contact_name=cname)

    # 2) auto-reply — ONLY if the bot is explicitly switched on (safe-off by default)
    if not _flag('WA_BOT_ENABLED'):
        print('[WA] Bot muted (WA_BOT_ENABLED off) — logged inbound, no reply sent')
        return
    reply = decide_reply(wa_id, body, is_first)
    if reply:
        out_wam = send_text(wa_id, reply)
        log_message(wa_id, 'out', reply, wam_id=out_wam, handled_by='bot', status='sent')

def handle_status(st):
    """Delivery receipts for our outbound messages (sent/delivered/read/failed)."""
    from app import db, WhatsAppMessage
    wam_id = st.get('id')
    status = st.get('status')
    if not wam_id or not status:
        return
    row = WhatsAppMessage.query.filter_by(wam_id=wam_id).first()
    if row:
        row.status = status
        db.session.commit()


# ── Flow A: greet a brand-new CRM lead on WhatsApp (template) ─────────────────
def notify_new_lead(lead):
    """Send the approved welcome template to a freshly-created lead.
    Safe to call always — silently no-ops if WhatsApp isn't configured or no phone."""
    try:
        if not _flag('WA_AUTO_WELCOME'):
            return  # Flow A off by default — no auto-greeting until explicitly enabled
        if not _cfg('WA_ACCESS_TOKEN') or not _cfg('WA_PHONE_NUMBER_ID'):
            return
        if not lead or not lead.phone:
            return
        first = (lead.name or 'there').split()[0]
        tmpl = _cfg('WA_WELCOME_TEMPLATE', 'tahfeel_lead_welcome')
        wam = send_template(lead.phone, tmpl, params=[first], lang=_cfg('WA_TEMPLATE_LANG', 'en'))
        body = f'[template: {tmpl}] Hi {first}, thanks for your interest in Tahfeel…'
        log_message(lead.phone, 'out', body, msg_type='template',
                    wam_id=wam, handled_by='bot', status='sent', lead_id=lead.id)
        print(f'[WA] ✓ Welcome template sent to lead {lead.id} ({lead.phone})')
    except Exception as e:
        # Never let WhatsApp break lead creation
        print(f'[WA] notify_new_lead failed: {e}')


# ── Webhook: verification (GET) ───────────────────────────────────────────────
@wa_bp.route('/webhook/whatsapp', methods=['GET'])
def wa_verify():
    mode      = request.args.get('hub.mode')
    token     = request.args.get('hub.verify_token')
    challenge = request.args.get('hub.challenge')
    expected  = _cfg('WA_VERIFY_TOKEN')
    if mode == 'subscribe' and token == expected:
        print('[WA] Webhook verified ✓')
        return challenge, 200
    print('[WA] Webhook verify failed')
    return 'Forbidden', 403


# ── Webhook: receiver (POST) ──────────────────────────────────────────────────
@wa_bp.route('/webhook/whatsapp', methods=['POST'])
def wa_receive():
    # Verify the request genuinely came from Meta (same app secret as leads)
    app_secret = _cfg('META_APP_SECRET')
    if app_secret:
        sig = request.headers.get('X-Hub-Signature-256', '')
        expected = 'sha256=' + hmac.new(
            app_secret.encode(), request.data, hashlib.sha256
        ).hexdigest()
        if not hmac.compare_digest(sig, expected):
            print('[WA] Invalid signature — rejected')
            return 'Unauthorized', 401

    payload = request.get_json(silent=True) or {}
    for entry in payload.get('entry', []):
        for change in entry.get('changes', []):
            if change.get('field') != 'messages':
                continue
            value = change.get('value', {})
            contacts = value.get('contacts', [])
            for msg in value.get('messages', []):
                try:
                    handle_incoming(msg, contacts)
                except Exception as e:
                    print(f'[WA] handle_incoming error: {e}')
            for st in value.get('statuses', []):
                try:
                    handle_status(st)
                except Exception as e:
                    print(f'[WA] handle_status error: {e}')
    return 'OK', 200
