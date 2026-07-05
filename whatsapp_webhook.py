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

def send_media(to, media_type, url, caption=None):
    """Send an image/document/audio/video by public link — ONLY inside the 24h window."""
    payload = {
        'messaging_product': 'whatsapp',
        'to': normalize_phone(to),
        'type': media_type,
        media_type: {'link': url},
    }
    if caption and media_type in ('image', 'document', 'video'):
        payload[media_type]['caption'] = caption
    return _send(payload)

def send_template(to, template_name, params=None, lang='en', param_names=None):
    """Business-initiated message — required for first contact (Flow A).
    param_names: optional list parallel to params. If given, each body variable
    is sent as a NAMED parameter (e.g. {{customer_name}}); otherwise positional
    ({{1}}, {{2}}…). Meta requires the payload to match how the template was built."""
    components = []
    if params:
        parameters = []
        for i, p in enumerate(params):
            item = {'type': 'text', 'text': str(p)}
            if param_names and i < len(param_names) and param_names[i]:
                item['parameter_name'] = param_names[i]
            parameters.append(item)
        components = [{'type': 'body', 'parameters': parameters}]
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
                lead_id=None, customer_id=None, media_url=None, mime_type=None):
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
        media_url    = media_url,
        mime_type    = mime_type,
        created_at   = now_dubai(),
    )
    db.session.add(row)
    db.session.commit()
    return row

def fetch_and_store_media(media_id):
    """Download a media's temp URL from Meta and re-upload it to Cloudinary for permanent
    storage (Meta's own URL expires in ~5 minutes). Returns (secure_url, mime_type) or (None, None)."""
    token = _cfg('WA_ACCESS_TOKEN')
    if not token or not media_id:
        return None, None
    try:
        r = requests.get(f'{GRAPH}/{media_id}', headers={'Authorization': f'Bearer {token}'}, timeout=10)
        if r.status_code >= 300:
            print(f'[WA] media metadata fetch failed {r.status_code}: {r.text[:200]}')
            return None, None
        meta = r.json()
        temp_url = meta.get('url')
        mime_type = meta.get('mime_type')
        if not temp_url:
            return None, None
        # Meta's media download also requires the bearer token
        dl = requests.get(temp_url, headers={'Authorization': f'Bearer {token}'}, timeout=20)
        if dl.status_code >= 300:
            print(f'[WA] media download failed {dl.status_code}')
            return None, None
        import cloudinary.uploader
        import io
        result = cloudinary.uploader.upload(
            io.BytesIO(dl.content), folder='tahfeel-whatsapp',
            resource_type='auto', use_filename=True, unique_filename=True,
        )
        return result.get('secure_url'), mime_type
    except Exception as e:
        print(f'[WA] fetch_and_store_media failed: {e}')
        return None, None


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

def _menu_reply(wa_id, text, is_first):
    """Phase-1 scripted fallback used when the AI is off or unavailable."""
    t = (text or '').strip()
    if t in MENU_REPLIES:
        return MENU_REPLIES[t]
    if is_first or _is_greeting(t):
        return WELCOME
    return (
        "Thanks for your message — a Tahfeel team member will get back to you shortly. 🙏\n\n"
        "Meanwhile, reply *1* (new license), *2* (visa) or *3* (agent)."
    )

# ── Phase 2: Claude-powered replies ───────────────────────────────────────────
AI_SYSTEM_PROMPT = (
    "You are the WhatsApp assistant for Tahfeel Business Setup Services LLC, a business-setup "
    "and PRO-services consultancy in Dubai, UAE. You help prospective and existing clients over "
    "WhatsApp with: new business licenses (mainland, free zone, offshore), visa services "
    "(investor, partner, employment, family), company amendments, bank-account opening, and "
    "general PRO/government paperwork.\n\n"
    "VERIFIED FACTS — state these exactly when asked; never alter or guess them:\n"
    "- Company: Tahfeel Business Setup Services LLC, Dubai, UAE. Operating since 2011. "
    "Licensed under DET (formerly DED).\n"
    "- Office: Al Wasl Ivory Building, next to Central Post Office, Karama, Dubai (nearest metro: "
    "ADCB & BurJuman). Walk-ins welcome; single branch in Dubai.\n"
    "- Working hours: Monday–Friday 9:00 AM–7:00 PM; Saturday 9:00 AM–4:00 PM; "
    "Sunday & UAE public holidays closed. WhatsApp and phone stay available outside office hours.\n"
    "- Contact: Landline +971 4 585 5033; Mobile/WhatsApp +971 55 434 6950; "
    "email info@tahfeel.ae; website www.tahfeel.ae.\n"
    "If a customer asks something not covered in these facts, do NOT invent details — give general "
    "guidance and offer to have a specialist confirm.\n\n"
    "Style: warm, professional, concise. This is WhatsApp — keep replies short (2–5 sentences), "
    "use simple language, and at most one relevant emoji. If the customer writes in Arabic, reply "
    "in Arabic; otherwise reply in English.\n\n"
    "Goals, in order: (1) understand what the customer needs, (2) ask one focused qualifying "
    "question at a time (e.g. planned business activity, mainland vs free zone, how many visas, "
    "nationality) to move things forward, (3) give helpful high-level guidance, (4) reassure them "
    "a Tahfeel specialist will follow up to confirm exact cost and timeline.\n\n"
    "Rules: Never invent specific prices, fees, or processing times — say a specialist will share "
    "exact figures. Do not promise guaranteed approvals. If the customer asks for a human, is "
    "upset, or the matter is complex/sensitive, tell them you're connecting them with a Tahfeel "
    "team member who will reply here shortly. Contact: info@tahfeel.ae, +971 4 585 5033.\n\n"
    "HAND-OVER SIGNAL: Whenever you tell the customer that a Tahfeel specialist or team member will "
    "take over or follow up — i.e. they ask for a human, they are upset, the matter is complex or "
    "sensitive, or they are ready to proceed / want to get started — append the exact text "
    "[[HANDOVER]] as the very last line of your reply. The system removes this marker before the "
    "customer ever sees it. Never mention it, and never add it in any other situation.\n\n"
    "Output only the message to send to the customer — no preamble, no quotation marks, no notes "
    "about your reasoning."
)

def ai_reply(wa_id, text, is_first):
    """Generate a reply with Claude from the recent conversation. Raises on failure
    so the caller can fall back to the scripted menu."""
    import anthropic
    from app import WhatsAppMessage
    model = _cfg('WA_AI_MODEL', 'claude-opus-4-8')

    # Build conversation history from the thread (inbound already logged by caller).
    rows = (WhatsAppMessage.query
            .filter_by(wa_id=normalize_phone(wa_id))
            .order_by(WhatsAppMessage.created_at).all())
    history = []
    for r in rows[-16:]:
        content = (r.body or '').strip()
        if not content or content.startswith('['):  # skip media placeholders
            continue
        role = 'user' if r.direction == 'in' else 'assistant'
        history.append({'role': role, 'content': content})
    # The Messages API requires the first turn to be from the user.
    while history and history[0]['role'] != 'user':
        history.pop(0)
    if not history:
        history = [{'role': 'user', 'content': (text or '').strip() or 'Hello'}]

    client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY from env
    resp = client.messages.create(
        model=model,
        max_tokens=1024,
        system=AI_SYSTEM_PROMPT,
        messages=history,
    )
    out = ''.join(b.text for b in resp.content if b.type == 'text').strip()
    handover = '[[HANDOVER]]' in out
    out = out.replace('[[HANDOVER]]', '').strip()
    return (out or None), handover

def decide_reply(wa_id, text, is_first):
    """Return (reply, handover). Uses Claude when an API key is present and
    WA_AI_ENABLED is on; otherwise (or on any AI error) falls back to the menu.
    handover=True means the AI decided a human should take over."""
    if os.environ.get('ANTHROPIC_API_KEY') and _flag('WA_AI_ENABLED', 'true'):
        try:
            r, handover = ai_reply(wa_id, text, is_first)
            if r:
                return r, handover
        except Exception as e:
            print(f'[WA] AI reply failed ({e}); falling back to scripted menu')
    return _menu_reply(wa_id, text, is_first), False

def do_handover(wa_id):
    """The AI decided a human should take over: assign the chat to a rep and pause
    the bot. For a brand-new prospect, create a round-robin Lead (same as Meta) so
    the rep gets the new-lead bell alert; known contacts route to their own rep."""
    from app import db, WhatsAppMessage, WhatsAppThread, Lead, Customer, LeadUpdate, User
    key = normalize_phone(wa_id)
    lead_id, customer_id = find_contact(wa_id)
    rep_id = None
    if customer_id:
        c = Customer.query.get(customer_id)
        rep_id = c.assigned_to if c else None
    elif lead_id:
        l = Lead.query.get(lead_id)
        rep_id = l.assigned_to if l else None
    else:
        # unknown number → create a round-robin lead so the assigned rep is alerted
        try:
            from meta_webhook import get_next_sales_staff
            assigned = get_next_sales_staff(db, User, Lead)
        except Exception:
            assigned = None
        cname = next((m.contact_name for m in WhatsAppMessage.query.filter_by(wa_id=key).all()
                      if m.contact_name), None) or f'WhatsApp {key}'
        lead = Lead(name=cname.title(), phone=key, source='WhatsApp - AI Bot', sub_source='WhatsApp Bot',
                    lead_type='New', status='New', assigned_to=(assigned.id if assigned else None),
                    created_at=now_dubai(), due_date=now_dubai() + timedelta(days=1),
                    remarks='Bot handed the conversation over to a human.')
        db.session.add(lead)
        db.session.flush()
        WhatsAppMessage.query.filter_by(wa_id=key).update({'lead_id': lead.id})
        db.session.add(LeadUpdate(lead_id=lead.id, stage='New — WhatsApp',
            remark='Bot handed the conversation to a human.',
            staff_name='System (WhatsApp Bot)', created_at=now_dubai()))
        rep_id = lead.assigned_to
    thread = WhatsAppThread.query.get(key)
    if not thread:
        thread = WhatsAppThread(wa_id=key)
        db.session.add(thread)
    if rep_id:
        thread.assigned_to = rep_id
        thread.assigned_at = now_dubai()
    thread.bot_paused = True
    thread.bot_paused_by = 'AI hand-over'
    db.session.commit()
    print(f'[WA] Hand-over for {key} → rep {rep_id}; bot paused')


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
    media_url = None
    mime_type = None
    if mtype == 'text':
        body = (msg.get('text') or {}).get('body', '')
    elif mtype in ('button', 'interactive'):
        body = (msg.get('button') or {}).get('text') or \
               (((msg.get('interactive') or {}).get('button_reply') or {}).get('title')) or ''
    elif mtype in ('image', 'document', 'audio', 'video', 'sticker'):
        media_obj = msg.get(mtype) or {}
        media_id = media_obj.get('id')
        body = media_obj.get('caption') or media_obj.get('filename') or f'[{mtype} received]'
        if media_id:
            media_url, mime_type = fetch_and_store_media(media_id)
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
    log_message(wa_id, 'in', body, msg_type=mtype, wam_id=wam_id, contact_name=cname,
                media_url=media_url, mime_type=mime_type)

    # 2) auto-reply — ONLY if the bot is explicitly switched on (safe-off by default)
    if not _flag('WA_BOT_ENABLED'):
        print('[WA] Bot muted (WA_BOT_ENABLED off) — logged inbound, no reply sent')
        return
    from app import WhatsAppThread
    thread = WhatsAppThread.query.get(normalize_phone(wa_id))
    if thread and thread.bot_paused:
        print(f'[WA] Bot paused for {wa_id} (human takeover) — logged inbound, no reply sent')
        return
    reply, handover = decide_reply(wa_id, body, is_first)
    if reply:
        out_wam = send_text(wa_id, reply)
        log_message(wa_id, 'out', reply, wam_id=out_wam, handled_by='bot', status='sent')
    if handover:
        try:
            do_handover(wa_id)
        except Exception as e:
            print(f'[WA] hand-over failed: {e}')

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
        # In-CRM admin toggle wins; if never set, fall back to the WA_AUTO_WELCOME env flag.
        enabled = None
        try:
            from app import get_setting
            v = get_setting('wa_auto_welcome')
            if v is not None:
                enabled = (v == 'on')
        except Exception:
            pass
        if enabled is None:
            enabled = _flag('WA_AUTO_WELCOME')
        if not enabled:
            return  # off by default — no auto-greeting until explicitly enabled
        if not _cfg('WA_ACCESS_TOKEN') or not _cfg('WA_PHONE_NUMBER_ID'):
            return
        if not lead or not lead.phone:
            return
        first = (lead.name or 'there').split()[0]
        tmpl = _cfg('WA_WELCOME_TEMPLATE', 'general')
        lang = _cfg('WA_WELCOME_LANG', 'en_GB')  # 'general' is English (UK) in Meta
        # 'general' uses a NAMED variable {{customer_name}}. Set WA_WELCOME_PARAM_NAME=''
        # to fall back to a positional {{1}} template.
        pname = _cfg('WA_WELCOME_PARAM_NAME', 'customer_name')
        param_names = [pname] if pname else None
        wam = send_template(lead.phone, tmpl, params=[first], lang=lang, param_names=param_names)
        body = f'[template: {tmpl}] Hi {first}, thanks for your interest in Tahfeel…'
        log_message(lead.phone, 'out', body, msg_type='template',
                    wam_id=wam, handled_by='bot', status='sent' if wam else 'failed',
                    lead_id=lead.id)
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
    # Verify the request genuinely came from Meta. The WhatsApp number lives under
    # a SEPARATE Meta app ("Tahfeel watsup") from the lead webhook, so it is signed
    # with that app's secret — use WA_APP_SECRET, falling back to META_APP_SECRET.
    app_secret = _cfg('WA_APP_SECRET') or _cfg('META_APP_SECRET')
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
