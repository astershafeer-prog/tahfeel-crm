# Tahfeel CRM - Backup & Recovery Guide

## 📦 Automated Database Backup

### Quick Start

**Manual backup (run anytime):**
```bash
python backup_database.py
```

**List all backups:**
```bash
python backup_database.py list
```

---

## 🤖 Automated Daily Backups

### Option 1: Railway Cron (Recommended)

Add to Railway environment:

1. Install Railway CLI or use Railway dashboard
2. Add cron job service:
   ```bash
   # In Railway dashboard, add new service
   # Type: Cron
   # Schedule: 0 2 * * * (daily at 2 AM Dubai time)
   # Command: python backup_database.py
   ```

**Cost:** Free (runs once daily, minimal compute)

---

### Option 2: GitHub Actions (Free)

Create `.github/workflows/backup.yml`:

```yaml
name: Daily Database Backup
on:
  schedule:
    - cron: '0 22 * * *'  # 2 AM Dubai = 10 PM UTC
  workflow_dispatch:  # Manual trigger

jobs:
  backup:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - uses: actions/setup-python@v4
        with:
          python-version: '3.10'
      - name: Install dependencies
        run: |
          pip install psycopg2-binary
          sudo apt-get update
          sudo apt-get install -y postgresql-client
      - name: Run backup
        env:
          DATABASE_URL: ${{ secrets.DATABASE_URL }}
        run: python backup_database.py
      - name: Upload backup artifact
        uses: actions/upload-artifact@v3
        with:
          name: database-backup
          path: backups/*.sql.gz
          retention-days: 7
```

**Cost:** Free (2,000 minutes/month on GitHub Free)

---

### Option 3: Hostinger VPS Cron (Best Long-term)

SSH into your VPS and add:

```bash
crontab -e
```

Add line:
```
0 2 * * * cd /var/www/tahfeel-crm && python3 backup_database.py >> /var/log/tahfeel-backup.log 2>&1
```

**Cost:** Free (already paying for VPS)

---

## 💾 Current Backup Strategy

### What's Backed Up:
- ✅ **Code:** GitHub (auto on every push)
- ✅ **Database:** Manual backups via script
- ✅ **Files (Cloudinary):** Provider has redundancy

### What's NOT Backed Up:
- ⚠️ **Railway ephemeral storage** (resets on deploy)
- ⚠️ **Local environment variables** (store separately)

---

## 🔄 Restore from Backup

### For PostgreSQL (Production):

```bash
# Decompress backup
gunzip backups/tahfeel_backup_20260503_120000.sql.gz

# Restore to database
psql -h <host> -U <user> -d <database> -f backups/tahfeel_backup_20260503_120000.sql
```

**WARNING:** This will overwrite current data!

### For SQLite (Development):

```bash
# Simply copy the backup file
cp backups/tahfeel_backup_20260503_120000.db tahfeel.db
```

---

## 💰 Cost Comparison

| Solution | Setup | Monthly Cost | Auto | Retention |
|----------|-------|--------------|------|-----------|
| **Manual Script** | ✅ Done | $0 | ❌ | Forever (until disk full) |
| **GitHub Actions** | 15 min | $0 | ✅ | 7 days |
| **Railway Cron** | 10 min | $0 | ✅ | Until disk full |
| **VPS Cron** | 5 min | $0 | ✅ | Forever |
| **AWS S3** | 30 min | ~$1-3 | ✅ | Forever |
| **Google Drive API** | 45 min | $0 | ✅ | 15 GB free |

---

## 🎯 Recommended Setup

**For Today (5 minutes):**
1. Test manual backup: `python backup_database.py`
2. Commit backup script to GitHub

**This Week (15 minutes):**
- Set up GitHub Actions for automated daily backups

**Long-term (when migrating):**
- Use VPS cron on Hostinger (you already own it)

---

## 📊 Current Costs (Railway)

**Tahfeel CRM:**
- Database: ~$5/month (512MB RAM)
- Web service: ~$5/month (512MB RAM)
- **Total: ~$10/month**

**Tahfeel Holidays CRM (once cloned):**
- Database: ~$5/month
- Web service: ~$5/month
- **Total: ~$10/month**

**Both CRMs: ~$20/month**

---

## 💡 Cost Savings Option

**Migrate both to Hostinger VPS:**
- VPS: Already paid (sunk cost = $0/month)
- PostgreSQL: Self-hosted ($0)
- Backups: Cron to local disk ($0)
- **Savings: $20/month = $240/year**

**Trade-off:**
- More manual setup (1-2 days initially)
- You manage updates/security
- No auto-scaling (probably fine for your scale)

---

## 🚨 Emergency Recovery

**If Railway database fails:**

1. **Check GitHub Actions** - Download latest artifact
2. **Check local backups** - If you ran manual backup recently
3. **Cloudinary files** - Still intact (separate service)
4. **Worst case** - Rebuild from code, re-enter critical data

**Prevention:**
- Set up automated backups TODAY
- Test restore process ONCE (on dev environment)

---

## 📞 Support

**Backup script issues:**
- Check Railway logs for cron job
- Verify DATABASE_URL environment variable
- Ensure PostgreSQL client installed (pg_dump)

**Questions:**
- Email: shafeer@tahfeel.ae
- Check script output: `python backup_database.py`
