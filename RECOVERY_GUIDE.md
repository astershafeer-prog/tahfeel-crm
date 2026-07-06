# 🆘 Tahfeel CRM — "Something Went Wrong" Recovery Sheet

Plain-English steps for when something breaks. **Stay calm — almost everything here is reversible.**
Keep this handy. You do NOT need to be a coder to follow it.

Your setup at a glance:
- **Website:** https://tahfeelcrm.online
- **Hosting + database:** Railway (railway.app) — this runs the app and holds all your data
- **Code:** GitHub (github.com/astershafeer-prog/tahfeel-crm) — deploys to Railway automatically when changed
- **Domain/DNS:** Cloudflare · **Uploaded files:** Cloudinary · **Email sending:** Resend

---

## 1. The website won't load / is down

1. First check if it's really down: open **https://tahfeelcrm.online/healthz**
   - If it shows `{"status": "ok"}` → the app is fine; your internet or browser is the problem. Try another device/network.
   - If it shows an error or won't load → go on.
2. Go to **Railway → your project → the web service → "Deployments"** tab.
   - Look at the latest deployment. Is it **green/Active** or **red/Crashed**?
   - If red/crashed → this was almost certainly caused by the last code change. **Do a rollback (see Section 3).**
3. Check **Railway → the service → "Logs"** — the newest red lines usually say what failed. If it mentions a missing variable (e.g. `SECRET_KEY`), see Section 6.
4. If Railway itself shows an outage, wait — it usually recovers on its own. Check https://status.railway.app.

---

## 2. Nobody can log in (or you're locked out)

- **"Too many failed attempts"** → this is the anti-hacker throttle. Just **wait 5 minutes** and try again. It clears itself.
- **"Invalid email or password"** → double-check the email/password. The main admin is `admin@tahfeel.ae`.
- **Everyone got logged out at once** → usually harmless; just log in again. (Happens if the app restarted.)
- **Truly locked out of the admin account** → tell your developer/support; the admin password can be reset directly in the database via Railway. Don't panic — the data is safe.

---

## 3. A change was made and now something is broken → ROLL BACK

**This is your undo button. It's safe.** Railway keeps every previous version.

1. Go to **Railway → your project → the web service → "Deployments"**.
2. Find the **last deployment that was working** (before the problem started).
3. Click the **⋮ (three dots)** next to it → **"Redeploy"**.
4. Wait 1–2 minutes. The site goes back to how it was before the bad change.

> After rollback, the site is safe. Then figure out what the bad change was — don't re-deploy it until it's fixed and `python smoke_test.py` passes.

---

## 4. Something looks wrong / data seems missing or was deleted by mistake

1. **Don't make more changes** — that can make recovery harder.
2. Small mistake (one record) → often quicker to just re-enter it.
3. Bigger problem (lots of data wrong/missing) → you need a **database restore** (Section 5). This brings back the data as of the last backup.
4. Note the **date and time** things looked correct — you'll pick a backup from before the problem.

---

## 5. WORST CASE — the database is lost or badly corrupted → RESTORE

Your data is backed up. You will not lose everything.

**Best option — Railway's own backups (if enabled):**
1. Go to **Railway → the Postgres (database) service → "Backups"**.
2. Pick a backup from **before** the problem.
3. Click **Restore**. Confirm. Done.

**Backup option — GitHub backup file:**
1. Go to **GitHub → the repo → "Actions" → "Daily Database Backup"**.
2. Open the most recent successful run → download the **backup artifact** (a `.sql.gz` file).
3. Send it to your developer/support to load into the database (needs a technical restore step).

> ⚠️ If Railway backups are NOT turned on yet, turn them on TODAY: Railway → Postgres service → Backups → enable scheduled snapshots. This is your #1 safety net.

---

## 6. Leads or WhatsApp messages stopped coming in

- **Meta leads not arriving** → the app now rejects unsigned webhook calls for security. Make sure `META_APP_SECRET` is still set in **Railway → Variables**. Also check Meta Business isn't in review/disabled.
- **WhatsApp bot silent** → check `WA_APP_SECRET`, `WA_ACCESS_TOKEN`, `WA_PHONE_NUMBER_ID` are still set in Railway Variables. WhatsApp access tokens can expire — that's the usual cause.
- **Emails/reports not sending** → check `RESEND_API_KEY` in Railway Variables.

> These four important variables must always exist in Railway: `SECRET_KEY`, `META_APP_SECRET`, `WA_APP_SECRET`, `DATABASE_URL`. If `SECRET_KEY` or the database URL is missing, the app won't start on purpose (a safety measure).

---

## 7. Golden rules (prevent 90% of disasters)

1. **Never delete data when unsure** — ask first. Deletes of customers/leads now require a confirm click, but be careful.
2. **Before trusting any code change**, the green checkmark on GitHub (the CI smoke test) should pass. A red ✗ means don't rely on it.
3. **Keep the four Railway variables** (above) safe — write them down somewhere private and offline.
4. **Turn on Railway database backups** and **test a restore once** so you know it works before you ever need it.
5. **Rollback (Section 3) is always safe** — when in doubt, roll back first, investigate second.

---

## 8. Emergency contacts / key info

- Developer / technical support: __________________________
- Railway account login: __________________________
- GitHub account: astershafeer-prog
- Cloudflare (domain) login: __________________________
- Main admin email in CRM: `admin@tahfeel.ae`

*Fill in the blanks and keep a printed copy somewhere safe.*
