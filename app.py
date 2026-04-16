# v16
from flask import Flask, render_template, request, redirect, url_for, session, flash
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timedelta
from functools import wraps
import os

app = Flask(__name__)
app.secret_key = 'tahfeel2026secretkey'
basedir = os.path.abspath(os.path.dirname(__file__))
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'sqlite:///' + os.path.join(basedir, 'tahfeel.db')).replace('postgres://', 'postgresql://')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

@app.errorhandler(500)
def internal_error(error):
    db.session.rollback()
    if 'user_id' in session:
        return redirect(url_for('dashboard'))
    return redirect(url_for('login'))

@app.errorhandler(404)
def not_found(error):
    if 'user_id' in session:
        return redirect(url_for('dashboard'))
    return redirect(url_for('login'))

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(100), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)
    role = db.Column(db.String(20), default='staff')
    active = db.Column(db.Boolean, default=True)

class Lead(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    company = db.Column(db.String(100))
    phone = db.Column(db.String(20))
    email = db.Column(db.String(100))
    address = db.Column(db.String(200))
    source = db.Column(db.String(50))
    service = db.Column(db.String(100))
    representative = db.Column(db.String(100))
    lead_type = db.Column(db.String(20), default='New')
    assigned_to = db.Column(db.Integer, db.ForeignKey('user.id'))
    due_date = db.Column(db.DateTime, default=lambda: datetime.now() + timedelta(days=1))
    remarks = db.Column(db.Text)
    status = db.Column(db.String(50), default='New')
    created_at = db.Column(db.DateTime, default=datetime.now)
    customer_story = db.Column(db.Text)
    potential_value = db.Column(db.Float, default=0)
    phone2 = db.Column(db.String(20))
    assignee = db.relationship('User', foreign_keys=[assigned_to])
    updates = db.relationship('LeadUpdate', backref='lead', lazy=True, order_by='LeadUpdate.created_at.desc()')

class LeadUpdate(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    lead_id = db.Column(db.Integer, db.ForeignKey('lead.id'), nullable=False)
    stage = db.Column(db.String(50))
    remark = db.Column(db.Text, nullable=False)
    staff_name = db.Column(db.String(100))
    created_at = db.Column(db.DateTime, default=datetime.now)
    followup_date = db.Column(db.DateTime)
    lost_reason = db.Column(db.String(100))
    future_potential = db.Column(db.String(20))

class Task(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text)
    assigned_to = db.Column(db.Integer, db.ForeignKey('user.id'))
    created_by = db.Column(db.Integer, db.ForeignKey('user.id'))
    due_date = db.Column(db.DateTime)
    priority = db.Column(db.String(20), default='Medium')  # Low, Medium, High
    status = db.Column(db.String(20), default='Pending')   # Pending, In Progress, Done
    created_at = db.Column(db.DateTime, default=datetime.now)
    lead_id = db.Column(db.Integer, db.ForeignKey('lead.id'), nullable=True)
    assignee = db.relationship('User', foreign_keys=[assigned_to])
    creator = db.relationship('User', foreign_keys=[created_by])
    lead = db.relationship('Lead', foreign_keys=[lead_id])

class Service(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False, unique=True)

class Source(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False, unique=True)

class JobType(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False, unique=True)

class Customer(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    company = db.Column(db.String(100))
    phone = db.Column(db.String(20))
    email = db.Column(db.String(100))
    address = db.Column(db.String(200))
    source = db.Column(db.String(50))
    notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.now)
    lead_id = db.Column(db.Integer, db.ForeignKey('lead.id'), nullable=True)
    lead = db.relationship('Lead', foreign_keys=[lead_id])
    jobs = db.relationship('Job', backref='customer', lazy=True, order_by='Job.created_at.desc()')

class Job(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    customer_id = db.Column(db.Integer, db.ForeignKey('customer.id'), nullable=False)
    job_type = db.Column(db.String(100), nullable=False)
    assigned_to = db.Column(db.Integer, db.ForeignKey('user.id'))
    due_date = db.Column(db.DateTime)
    priority = db.Column(db.String(20), default='Medium')
    status = db.Column(db.String(50), default='Pending Finance Approval')
    internal_notes = db.Column(db.Text)
    amount_invoiced = db.Column(db.Float, default=0)
    amount_received = db.Column(db.Float, default=0)
    finance_approved_by = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    finance_approved_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.now)
    created_by = db.Column(db.Integer, db.ForeignKey('user.id'))
    assignee = db.relationship('User', foreign_keys=[assigned_to])
    creator = db.relationship('User', foreign_keys=[created_by])
    finance_approver = db.relationship('User', foreign_keys=[finance_approved_by])
    updates = db.relationship('JobUpdate', backref='job', lazy=True, order_by='JobUpdate.created_at.desc()')
    subtasks = db.relationship('SubTask', backref='job', lazy=True, order_by='SubTask.created_at')

class SubTask(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    job_id = db.Column(db.Integer, db.ForeignKey('job.id'), nullable=False)
    title = db.Column(db.String(200), nullable=False)
    assigned_to = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    status = db.Column(db.String(20), default='Pending')
    remarks = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.now)
    completed_at = db.Column(db.DateTime, nullable=True)
    assignee = db.relationship('User', foreign_keys=[assigned_to])

class JobUpdate(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    job_id = db.Column(db.Integer, db.ForeignKey('job.id'), nullable=False)
    status = db.Column(db.String(50))
    remark = db.Column(db.Text, nullable=False)
    staff_name = db.Column(db.String(100))
    created_at = db.Column(db.DateTime, default=datetime.now)

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated

def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if session.get('role') != 'admin':
            flash('Admin access required')
            return redirect(url_for('dashboard'))
        return f(*args, **kwargs)
    return decorated

def finance_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if session.get('role') not in ['admin', 'finance']:
            flash('Finance access required')
            return redirect(url_for('dashboard'))
        return f(*args, **kwargs)
    return decorated

def apply_lead_filters(leads, args, now):
    date_filter = args.get('date')
    status_filter = args.get('status')
    staff_filter = args.get('staff')
    if date_filter == 'today':
        leads = [l for l in leads if l.created_at and l.created_at.date() == now.date()]
    elif date_filter == 'week':
        week_start = now.date() - timedelta(days=now.weekday())
        week_end = week_start + timedelta(days=6)
        leads = [l for l in leads if l.created_at and week_start <= l.created_at.date() <= week_end]
    elif date_filter == 'month':
        leads = [l for l in leads if l.created_at and l.created_at.year == now.year and l.created_at.month == now.month]
    elif date_filter == 'custom':
        from_date = args.get('from')
        to_date = args.get('to')
        if from_date:
            from_dt = datetime.strptime(from_date, '%Y-%m-%d').date()
            leads = [l for l in leads if l.created_at and l.created_at.date() >= from_dt]
        if to_date:
            to_dt = datetime.strptime(to_date, '%Y-%m-%d').date()
            leads = [l for l in leads if l.created_at and l.created_at.date() <= to_dt]
            leads = [l for l in leads if l.due_date.date() <= to_dt]
    if status_filter:
        if status_filter == 'Overdue':
            leads = [l for l in leads if l.due_date < now and l.status not in ['Converted', 'Lost']]
        else:
            leads = [l for l in leads if l.status == status_filter]
    if staff_filter:
        leads = [l for l in leads if l.assigned_to == int(staff_filter)]
    return leads

@app.route('/')
def index():
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        user = User.query.filter_by(email=email, active=True).first()
        if user and check_password_hash(user.password, password):
            session['user_id'] = user.id
            session['user_name'] = user.name
            session['role'] = user.role
            return redirect(url_for('dashboard'))
        flash('Invalid email or password')
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

@app.route('/dashboard')
@login_required
def dashboard():
    now = datetime.now()
    role = session['role']

    # ── Finance dashboard ────────────────────────────────────────────────────
    if role == 'finance':
        all_jobs = Job.query.order_by(Job.created_at.desc()).all()
        active_jobs = [j for j in all_jobs if j.status != 'Done']
        pending_approval = [j for j in all_jobs if j.status == 'Pending Finance Approval']
        total_invoiced = sum(j.amount_invoiced or 0 for j in active_jobs)
        total_received = sum(j.amount_received or 0 for j in active_jobs)
        total_pending = total_invoiced - total_received
        completed_value = sum(j.amount_received or 0 for j in all_jobs if j.status == 'Done')
        return render_template('dashboard_finance.html',
                               all_jobs=active_jobs,
                               pending_approval=pending_approval,
                               total_invoiced=total_invoiced,
                               total_received=total_received,
                               total_pending=total_pending,
                               completed_value=completed_value,
                               now=now)

    # ── Admin dashboard ──────────────────────────────────────────────────────
    if role == 'admin':
        all_leads = Lead.query.order_by(Lead.due_date).all()
        all_jobs = Job.query.order_by(Job.due_date).all()
        date_filter = request.args.get('date', '')
        from_date = request.args.get('from', '')
        to_date = request.args.get('to', '')

        leads = all_leads
        if date_filter == 'today':
            leads = [l for l in all_leads if l.created_at and l.created_at.date() == now.date()]
            jobs = [j for j in all_jobs if j.created_at and j.created_at.date() == now.date()]
        elif date_filter == 'week':
            week_start = now.date() - timedelta(days=now.weekday())
            leads = [l for l in all_leads if l.created_at and l.created_at.date() >= week_start]
            jobs = [j for j in all_jobs if j.created_at and j.created_at.date() >= week_start]
        elif date_filter == 'month':
            leads = [l for l in all_leads if l.created_at and l.created_at.year == now.year and l.created_at.month == now.month]
            jobs = [j for j in all_jobs if j.created_at and j.created_at.year == now.year and j.created_at.month == now.month]
        elif date_filter == 'custom' and from_date and to_date:
            from_dt = datetime.strptime(from_date, '%Y-%m-%d').date()
            to_dt = datetime.strptime(to_date, '%Y-%m-%d').date()
            leads = [l for l in all_leads if l.created_at and from_dt <= l.created_at.date() <= to_dt]
            jobs = [j for j in all_jobs if j.created_at and from_dt <= j.created_at.date() <= to_dt]
        else:
            jobs = all_jobs

        # Lead stats
        total = len(leads)
        overdue_leads = [l for l in leads if l.due_date and l.due_date < now and l.status not in ['Converted', 'Lost']]
        converted = [l for l in leads if l.status == 'Converted']
        lost = [l for l in leads if l.status == 'Lost']
        pending = [l for l in leads if l.status not in ['Converted', 'Lost', 'New']]

        # Financial cards (active jobs only, Done separate)
        active_jobs = [j for j in jobs if j.status != 'Done']
        done_jobs = [j for j in jobs if j.status == 'Done']
        total_invoiced = sum(j.amount_invoiced or 0 for j in active_jobs)
        total_received = sum(j.amount_received or 0 for j in active_jobs)
        total_pending = total_invoiced - total_received
        completed_value = sum(j.amount_received or 0 for j in done_jobs)

        overdue_jobs = [j for j in jobs if j.due_date and j.due_date < now and j.status not in ['Done', 'Pending Finance Approval']]
        pending_approval = [j for j in jobs if j.status == 'Pending Finance Approval']

        users = User.query.filter_by(active=True, role='staff').all()
        staff_stats = []
        for u in users:
            u_leads = [l for l in leads if l.assigned_to == u.id]
            u_jobs = [j for j in jobs if j.assigned_to == u.id]
            staff_stats.append({
                'name': u.name,
                'leads': len(u_leads),
                'overdue_leads': len([l for l in u_leads if l.due_date and l.due_date < now and l.status not in ['Converted', 'Lost']]),
                'active_jobs': len([j for j in u_jobs if j.status not in ['Done', 'Pending Finance Approval']]),
                'overdue_jobs': len([j for j in u_jobs if j.due_date and j.due_date < now and j.status not in ['Done', 'Pending Finance Approval']]),
            })

        today_leads = [l for l in all_leads if l.created_at and l.created_at.date() == now.date()][:10]
        recent_jobs = [j for j in all_jobs if j.status not in ['Done', 'Pending Finance Approval']][:10]

        return render_template('dashboard_admin.html',
                               leads=leads, today_leads=today_leads,
                               total=total, overdue_leads=overdue_leads,
                               converted=converted, lost=lost, pending=pending,
                               jobs=jobs, active_jobs=active_jobs,
                               overdue_jobs=overdue_jobs, done_jobs=done_jobs,
                               pending_approval=pending_approval,
                               recent_jobs=recent_jobs,
                               total_invoiced=total_invoiced,
                               total_received=total_received,
                               total_pending=total_pending,
                               completed_value=completed_value,
                               staff_stats=staff_stats,
                               now=now, date_filter=date_filter,
                               from_date=from_date, to_date=to_date)

    # ── Staff dashboard ──────────────────────────────────────────────────────
    leads = Lead.query.filter_by(assigned_to=session['user_id']).order_by(Lead.due_date).all()
    my_jobs = Job.query.filter_by(assigned_to=session['user_id']).filter(Job.status != 'Done').order_by(Job.due_date).all()
    overdue = [l for l in leads if l.due_date and l.due_date < now and l.status not in ['Converted', 'Lost']]
    converted = [l for l in leads if l.status == 'Converted']
    lost = [l for l in leads if l.status == 'Lost']
    pending = [l for l in leads if l.status not in ['Converted', 'Lost', 'New']]
    overdue_jobs = [j for j in my_jobs if j.due_date and j.due_date < now and j.status != 'Pending Finance Approval']
    # Financial summary for staff's own tasks
    active_jobs = [j for j in my_jobs if j.status != 'Pending Finance Approval']
    total_invoiced = sum(j.amount_invoiced or 0 for j in active_jobs)
    total_received = sum(j.amount_received or 0 for j in active_jobs)
    total_pending = total_invoiced - total_received
    done_jobs = Job.query.filter_by(assigned_to=session['user_id'], status='Done').all()
    completed_value = sum(j.amount_received or 0 for j in done_jobs)
    followups = LeadUpdate.query.filter(
        LeadUpdate.staff_name == session['user_name'],
        LeadUpdate.followup_date <= now + timedelta(days=1),
        LeadUpdate.followup_date >= now
    ).all()
    return render_template('dashboard_staff.html', leads=leads, overdue=overdue,
                           converted=converted, lost=lost, pending=pending,
                           my_jobs=my_jobs, overdue_jobs=overdue_jobs,
                           total_invoiced=total_invoiced,
                           total_received=total_received,
                           total_pending=total_pending,
                           completed_value=completed_value,
                           followups=followups, now=now)

@app.route('/leads')
@login_required
@admin_required
def all_leads():
    now = datetime.now()
    leads = Lead.query.order_by(Lead.due_date).all()
    users = User.query.filter_by(active=True).filter(User.role.in_(['staff', 'admin'])).all()
    search = request.args.get('search', '').strip().lower()
    is_default = not any(request.args.get(k) for k in ['date', 'status', 'staff', 'search', 'from', 'to'])

    if is_default:
        leads = [l for l in leads if l.created_at and l.created_at.date() == now.date()]
    else:
        if search:
            leads = [l for l in leads if
                     search in (l.name or '').lower() or
                     search in (l.phone or '').lower() or
                     search in (l.company or '').lower()]
        leads = apply_lead_filters(leads, request.args, now)

    # Pagination
    page = int(request.args.get('page', 1))
    per_page = 50
    total = len(leads)
    total_pages = max(1, (total + per_page - 1) // per_page)
    page = max(1, min(page, total_pages))
    paginated = leads[(page - 1) * per_page: page * per_page]

    return render_template('all_leads.html', leads=paginated, now=now, users=users,
                           search=search, is_default=is_default,
                           page=page, total_pages=total_pages, total=total)

@app.route('/leads/export')
@login_required
@admin_required
def export_leads():
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill
    from flask import make_response
    import io
    now = datetime.now()
    leads = Lead.query.order_by(Lead.due_date).all()
    leads = apply_lead_filters(leads, request.args, now)
    wb = Workbook()
    ws = wb.active
    ws.title = "Leads"
    headers = ['Name', 'Company', 'Phone', 'Phone 2', 'Email', 'Address', 'Source',
               'Service', 'Lead Type', 'Assigned To', 'Due Date', 'Status', 'Remarks', 'Created', 'Potential Value']
    ws.append(headers)
    header_font = Font(bold=True, color="FFFFFF")
    header_fill = PatternFill(start_color="133E87", end_color="133E87", fill_type="solid")
    for cell in ws[1]:
        cell.font = header_font
        cell.fill = header_fill
    for lead in leads:
        ws.append([
            lead.name, lead.company or '', lead.phone or '', lead.phone2 or '',
            lead.email or '', lead.address or '', lead.source or '', lead.service or '',
            lead.lead_type or '', lead.assignee.name if lead.assignee else '',
            lead.due_date.strftime('%d %b %Y') if lead.due_date else '',
            lead.status or '', lead.remarks or '',
            lead.created_at.strftime('%d %b %Y') if lead.created_at else '',
            lead.potential_value or 0,
        ])
    for col in ws.columns:
        max_length = max(len(str(cell.value or '')) for cell in col)
        ws.column_dimensions[col[0].column_letter].width = max_length + 4
    output = io.BytesIO()
    wb.save(output)
    output.seek(0)
    response = make_response(output.read())
    response.headers['Content-Type'] = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    response.headers['Content-Disposition'] = f'attachment; filename=tahfeel_leads_{now.strftime("%Y%m%d")}.xlsx'
    return response

@app.route('/leads/add', methods=['GET', 'POST'])
@login_required
def add_lead():
    now = datetime.now()
    users = User.query.filter_by(active=True).filter(User.role.in_(['staff', 'admin'])).all()
    services = Service.query.order_by(Service.name).all()
    sources = Source.query.order_by(Source.name).all()
    if request.method == 'POST':
        due = request.form.get('due_date')
        lead_date = request.form.get('lead_date')
        created_dt = datetime.strptime(lead_date, '%Y-%m-%d') if lead_date else datetime.now()
        due_dt = datetime.strptime(due, '%Y-%m-%d') if due else created_dt + timedelta(days=1)
        lead = Lead(
            name=request.form['name'],
            company=request.form.get('company'),
            phone=request.form.get('phone'),
            phone2=request.form.get('phone2'),
            email=request.form.get('email'),
            address=request.form.get('address'),
            source=request.form.get('source'),
            service=request.form.get('service'),
            representative=session['user_name'],
            lead_type=request.form.get('lead_type', 'New'),
            assigned_to=int(request.form['assigned_to']) if request.form.get('assigned_to') else None,
            due_date=due_dt,
            remarks=request.form.get('remarks'),
            created_at=created_dt
        )
        db.session.add(lead)
        db.session.commit()
        flash('Lead added successfully')
        return redirect(url_for('dashboard'))
    return render_template('add_lead.html', users=users, services=services, sources=sources, now=now)

@app.route('/leads/<int:lead_id>', methods=['GET', 'POST'])
@login_required
def lead_detail(lead_id):
    now = datetime.now()
    lead = Lead.query.get_or_404(lead_id)
    if request.method == 'POST':
        stage = request.form['stage']
        remark = request.form['remark']
        followup = request.form.get('followup_date')
        followup_dt = datetime.strptime(followup, '%Y-%m-%d') if followup else None
        update = LeadUpdate(
            lead_id=lead.id, stage=stage, remark=remark,
            staff_name=session['user_name'], followup_date=followup_dt,
            lost_reason=request.form.get('lost_reason'),
            future_potential=request.form.get('future_potential')
        )
        lead.status = stage
        if request.form.get('customer_story'):
            lead.customer_story = request.form.get('customer_story')
        potential_value = request.form.get('potential_value')
        if potential_value and not lead.potential_value:
            try:
                lead.potential_value = float(potential_value)
            except:
                pass
        db.session.add(update)
        db.session.commit()
        flash('Update saved')
        return redirect(url_for('lead_detail', lead_id=lead_id))
    return render_template('lead_detail.html', lead=lead, now=now)

@app.route('/leads/import', methods=['GET', 'POST'])
@login_required
@admin_required
def import_leads():
    if request.method == 'POST':
        file = request.files.get('file')
        if not file or not file.filename.endswith('.xlsx'):
            flash('Please upload a valid .xlsx file')
            return redirect(url_for('import_leads'))
        try:
            from openpyxl import load_workbook
            wb = load_workbook(file)
            ws = wb.active
            count = 0
            errors = []
            all_staff = User.query.filter_by(active=True).filter(User.role.in_(['staff', 'admin'])).all()
            staff_map = {u.name.strip().lower(): u.id for u in all_staff}
            for i, row in enumerate(ws.iter_rows(min_row=2, values_only=True), start=2):
                name = row[0] if len(row) > 0 else None
                company = row[1] if len(row) > 1 else None
                phone = str(row[2]) if len(row) > 2 and row[2] else None
                email = row[3] if len(row) > 3 else None
                address = row[4] if len(row) > 4 else None
                source = row[5] if len(row) > 5 else None
                service = row[6] if len(row) > 6 else None
                lead_type = row[7] if len(row) > 7 else 'New'
                remarks = row[8] if len(row) > 8 else None
                assigned_name = str(row[9]).strip() if len(row) > 9 and row[9] else None
                lead_date_str = str(row[10]).strip() if len(row) > 10 and row[10] else None
                assigned_id = None
                if assigned_name:
                    assigned_id = staff_map.get(assigned_name.lower())
                    if not assigned_id:
                        errors.append(f'Row {i}: Staff "{assigned_name}" not found — lead imported unassigned')
                if not name:
                    errors.append(f'Row {i}: Name is required — skipped')
                    continue
                if not phone:
                    errors.append(f'Row {i}: Phone is required — skipped')
                    continue
                created_dt = datetime.strptime(lead_date_str, '%Y-%m-%d') if lead_date_str else datetime.now()
                lead = Lead(
                    name=str(name), company=str(company) if company else None,
                    phone=str(phone), email=str(email) if email else None,
                    address=str(address) if address else None,
                    source=str(source) if source else None,
                    service=str(service) if service else None,
                    lead_type=str(lead_type) if lead_type else 'New',
                    remarks=str(remarks) if remarks else None,
                    representative=session['user_name'],
                    assigned_to=assigned_id,
                    created_at=created_dt,
                    due_date=created_dt + timedelta(days=1)
                )
                db.session.add(lead)
                count += 1
            db.session.commit()
            if errors:
                flash(f'Imported {count} leads. Notes: ' + ' | '.join(errors))
            else:
                flash(f'Successfully imported {count} leads!')
            return redirect(url_for('dashboard'))
        except Exception as e:
            flash(f'Error reading file: {str(e)}')
            return redirect(url_for('import_leads'))
    return render_template('import_leads.html')

@app.route('/leads/template')
@login_required
def download_template():
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill
    from openpyxl.worksheet.datavalidation import DataValidation
    from flask import make_response
    import io
    services = Service.query.order_by(Service.name).all()
    sources = Source.query.order_by(Source.name).all()
    staff = User.query.filter_by(active=True).filter(User.role.in_(['staff', 'admin'])).all()
    wb = Workbook()
    ws = wb.active
    ws.title = "Leads"
    headers = ['Name*', 'Company', 'Phone*', 'Email', 'Address',
               'Source', 'Service', 'Lead Type', 'Remarks', 'Assigned To', 'Lead Date']
    ws.append(headers)
    ws.append(['John Smith', 'ABC Trading LLC', '+971501234567',
               'john@abc.ae', 'Dubai',
               sources[0].name if sources else 'WhatsApp',
               services[0].name if services else 'Trade License',
               'New', 'Interested in mainland license',
               staff[0].name if staff else '', '2026-04-16'])
    ws.append(['Sara Ahmed', '', '+971509876543', '', 'Sharjah',
               sources[1].name if len(sources) > 1 else '',
               services[1].name if len(services) > 1 else '',
               'New', '',
               staff[1].name if len(staff) > 1 else '', '2026-04-16'])
    header_font = Font(bold=True, color="FFFFFF")
    header_fill = PatternFill(start_color="133E87", end_color="133E87", fill_type="solid")
    for cell in ws[1]:
        cell.font = header_font
        cell.fill = header_fill
    for col in ws.columns:
        max_length = max(len(str(cell.value or '')) for cell in col)
        ws.column_dimensions[col[0].column_letter].width = max_length + 4
    ref = wb.create_sheet(title="Reference")
    ref['A1'] = 'Services'
    for i, s in enumerate(services, start=2):
        ref.cell(row=i, column=1, value=s.name)
    ref['B1'] = 'Sources'
    for i, s in enumerate(sources, start=2):
        ref.cell(row=i, column=2, value=s.name)
    ref['C1'] = 'Staff'
    for i, u in enumerate(staff, start=2):
        ref.cell(row=i, column=3, value=u.name)
    ref['D1'] = 'Lead Type'
    ref['D2'] = 'New'
    ref['D3'] = 'Old Follow-up'
    ref.sheet_state = 'hidden'
    service_count = len(services) + 1
    source_count = len(sources) + 1
    staff_count = len(staff) + 1
    dv_source = DataValidation(type="list", formula1=f"Reference!$B$2:$B${source_count}", allow_blank=True, showDropDown=False)
    dv_source.sqref = "F2:F1000"
    ws.add_data_validation(dv_source)
    dv_service = DataValidation(type="list", formula1=f"Reference!$A$2:$A${service_count}", allow_blank=True, showDropDown=False)
    dv_service.sqref = "G2:G1000"
    ws.add_data_validation(dv_service)
    dv_type = DataValidation(type="list", formula1="Reference!$D$2:$D$3", allow_blank=True, showDropDown=False)
    dv_type.sqref = "H2:H1000"
    ws.add_data_validation(dv_type)
    dv_staff = DataValidation(type="list", formula1=f"Reference!$C$2:$C${staff_count}", allow_blank=True, showDropDown=False)
    dv_staff.sqref = "J2:J1000"
    ws.add_data_validation(dv_staff)
    output = io.BytesIO()
    wb.save(output)
    output.seek(0)
    response = make_response(output.read())
    response.headers['Content-Type'] = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    response.headers['Content-Disposition'] = 'attachment; filename=tahfeel_leads_template.xlsx'
    return response

@app.route('/leads/<int:lead_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_lead(lead_id):
    now = datetime.now()
    lead = Lead.query.get_or_404(lead_id)
    users = User.query.filter_by(active=True).filter(User.role.in_(['staff', 'admin'])).all()
    services = Service.query.order_by(Service.name).all()
    sources = Source.query.order_by(Source.name).all()
    if request.method == 'POST':
        lead.name = request.form['name']
        lead.company = request.form.get('company')
        lead.phone = request.form.get('phone')
        lead.phone2 = request.form.get('phone2')
        lead.email = request.form.get('email')
        lead.address = request.form.get('address')
        lead.source = request.form.get('source')
        lead.service = request.form.get('service')
        lead.lead_type = request.form.get('lead_type', 'New')
        lead.remarks = request.form.get('remarks')
        assigned = request.form.get('assigned_to')
        lead.assigned_to = int(assigned) if assigned else None
        due = request.form.get('due_date')
        if due:
            lead.due_date = datetime.strptime(due, '%Y-%m-%d')
        db.session.commit()
        flash('Lead updated successfully')
        return redirect(url_for('lead_detail', lead_id=lead_id))
    return render_template('edit_lead.html', lead=lead, users=users, services=services, sources=sources, now=now)

@app.route('/leads/<int:lead_id>/delete')
@login_required
@admin_required
def delete_lead(lead_id):
    lead = Lead.query.get_or_404(lead_id)
    LeadUpdate.query.filter_by(lead_id=lead_id).delete()
    db.session.delete(lead)
    db.session.commit()
    flash('Lead deleted successfully')
    ref = request.referrer
    if ref and '/leads' in ref:
        return redirect(ref)
    return redirect(url_for('all_leads'))

@app.route('/leads/bulk-delete', methods=['POST'])
@login_required
@admin_required
def bulk_delete_leads():
    ids = request.form.getlist('lead_ids')
    if not ids:
        flash('No leads selected')
        return redirect(url_for('all_leads'))
    count = 0
    for lead_id in ids:
        lead = Lead.query.get(int(lead_id))
        if lead:
            LeadUpdate.query.filter_by(lead_id=lead.id).delete()
            db.session.delete(lead)
            count += 1
    db.session.commit()
    flash(f'{count} lead(s) deleted successfully')
    return redirect(url_for('all_leads'))

@app.route('/admin', methods=['GET', 'POST'])
@login_required
@admin_required
def admin_panel():
    users = User.query.order_by(User.name).all()
    services = Service.query.order_by(Service.name).all()
    sources = Source.query.order_by(Source.name).all()
    job_types = JobType.query.order_by(JobType.name).all()
    return render_template('admin_panel.html', users=users, services=services, sources=sources, job_types=job_types)

@app.route('/admin/staff/add', methods=['POST'])
@login_required
@admin_required
def admin_add_staff():
    email = request.form['email']
    existing = User.query.filter_by(email=email).first()
    if existing:
        flash('This email already exists')
        return redirect(url_for('admin_panel'))
    try:
        user = User(
            name=request.form['name'],
            email=email,
            password=generate_password_hash(request.form['password']),
            role=request.form['role']
        )
        db.session.add(user)
        db.session.commit()
        flash('Staff member added successfully')
    except Exception as e:
        db.session.rollback()
        flash('Error — ' + str(e))
    return redirect(url_for('admin_panel'))

@app.route('/admin/staff/<int:user_id>/edit', methods=['POST'])
@login_required
@admin_required
def admin_edit_staff(user_id):
    user = User.query.get_or_404(user_id)
    name = request.form.get('name', '').strip()
    email = request.form.get('email', '').strip()
    new_password = request.form.get('password', '').strip()
    new_role = request.form.get('role', '').strip()
    if name:
        user.name = name
    if email:
        existing = User.query.filter_by(email=email).first()
        if existing and existing.id != user_id:
            flash('That email is already in use')
            return redirect(url_for('admin_panel'))
        user.email = email
    if new_role in ['staff', 'admin', 'finance']:
        user.role = new_role
    if new_password:
        user.password = generate_password_hash(new_password)
    db.session.commit()
    flash('Staff member updated successfully')
    return redirect(url_for('admin_panel'))

@app.route('/admin/service/add', methods=['POST'])
@login_required
@admin_required
def admin_add_service():
    name = request.form.get('name', '').strip()
    if name:
        existing = Service.query.filter_by(name=name).first()
        if existing:
            flash('Service already exists')
        else:
            db.session.add(Service(name=name))
            db.session.commit()
            flash(f'Service "{name}" added')
    return redirect(url_for('admin_panel'))

@app.route('/admin/service/<int:service_id>/delete')
@login_required
@admin_required
def admin_delete_service(service_id):
    service = Service.query.get_or_404(service_id)
    db.session.delete(service)
    db.session.commit()
    flash(f'Service "{service.name}" removed')
    return redirect(url_for('admin_panel'))

@app.route('/admin/source/add', methods=['POST'])
@login_required
@admin_required
def admin_add_source():
    name = request.form.get('name', '').strip()
    if name:
        existing = Source.query.filter_by(name=name).first()
        if existing:
            flash('Source already exists')
        else:
            db.session.add(Source(name=name))
            db.session.commit()
            flash(f'Source "{name}" added')
    return redirect(url_for('admin_panel'))

@app.route('/admin/source/<int:source_id>/delete')
@login_required
@admin_required
def admin_delete_source(source_id):
    source = Source.query.get_or_404(source_id)
    db.session.delete(source)
    db.session.commit()
    flash(f'Source "{source.name}" removed')
    return redirect(url_for('admin_panel'))

@app.route('/users', methods=['GET', 'POST'])
@login_required
@admin_required
def manage_users():
    return redirect(url_for('admin_panel'))

@app.route('/users/<int:user_id>/toggle')
@login_required
@admin_required
def toggle_user(user_id):
    user = User.query.get_or_404(user_id)
    user.active = not user.active
    db.session.commit()
    flash(f'{"Activated" if user.active else "Deactivated"} {user.name}')
    return redirect(url_for('admin_panel'))

@app.route('/admin/staff/<int:user_id>/toggle')
@login_required
@admin_required
def admin_toggle_staff(user_id):
    user = User.query.get_or_404(user_id)
    user.active = not user.active
    db.session.commit()
    flash(f'{"Activated" if user.active else "Deactivated"} {user.name}')
    return redirect(url_for('admin_panel'))

# ── Customers ────────────────────────────────────────────────────────────────

@app.route('/customers')
@login_required
@admin_required
def customers():
    customer_list = Customer.query.order_by(Customer.name).all()
    return render_template('customers.html', customers=customer_list)

@app.route('/customers/add', methods=['GET', 'POST'])
@login_required
@admin_required
def add_customer():
    converted_leads = Lead.query.filter_by(status='Converted').order_by(Lead.name).all()
    sources = Source.query.order_by(Source.name).all()
    if request.method == 'POST':
        lead_id = request.form.get('lead_id') or None
        if lead_id:
            lead = Lead.query.get(int(lead_id))
            customer = Customer(
                name=lead.name, company=lead.company, phone=lead.phone,
                email=lead.email, address=lead.address, source=lead.source,
                notes=request.form.get('notes'), lead_id=int(lead_id)
            )
        else:
            customer = Customer(
                name=request.form['name'],
                company=request.form.get('company'),
                phone=request.form.get('phone'),
                email=request.form.get('email'),
                address=request.form.get('address'),
                source=request.form.get('source'),
                notes=request.form.get('notes')
            )
        db.session.add(customer)
        db.session.commit()
        flash('Customer added successfully')
        return redirect(url_for('customers'))
    return render_template('add_customer.html', converted_leads=converted_leads, sources=sources)

@app.route('/customers/<int:customer_id>')
@login_required
@admin_required
def customer_detail(customer_id):
    customer = Customer.query.get_or_404(customer_id)
    jobs = Job.query.filter_by(customer_id=customer_id).order_by(Job.created_at.desc()).all()
    total_invoiced = sum(j.amount_invoiced or 0 for j in jobs)
    total_received = sum(j.amount_received or 0 for j in jobs)
    return render_template('customer_detail.html', customer=customer, jobs=jobs,
                           total_invoiced=total_invoiced, total_received=total_received)

# ── Jobs ──────────────────────────────────────────────────────────────────────

JOB_STATUSES = ['Assigned', 'Job Started', 'Processing', 'Pending Authority', 'On Hold', 'Delayed', 'Final Stage', 'Done']
JOB_STATUSES_ALL = ['Pending Finance Approval'] + JOB_STATUSES

@app.route('/jobs')
@login_required
def jobs():
    now = datetime.now()
    role = session['role']
    if role in ['admin', 'finance']:
        job_list = Job.query.order_by(Job.created_at.desc()).all()
    else:
        # Staff see their assigned jobs (excluding pending finance approval)
        job_list = Job.query.filter_by(assigned_to=session['user_id']).filter(
            Job.status != 'Pending Finance Approval'
        ).order_by(Job.due_date).all()
    status_filter = request.args.get('status', '')
    priority_filter = request.args.get('priority', '')
    if status_filter:
        job_list = [j for j in job_list if j.status == status_filter]
    if priority_filter:
        job_list = [j for j in job_list if j.priority == priority_filter]
    overdue = [j for j in job_list if j.due_date and j.due_date < now and j.status not in ['Done', 'Pending Finance Approval']]
    users = User.query.filter_by(active=True).filter(User.role.in_(['staff', 'admin'])).all()
    return render_template('jobs.html', jobs=job_list, now=now, overdue=overdue,
                           statuses=JOB_STATUSES, users=users,
                           status_filter=status_filter, priority_filter=priority_filter)

@app.route('/jobs/add', methods=['GET', 'POST'])
@login_required
@admin_required
def add_job():
    customers = Customer.query.order_by(Customer.name).all()
    job_types = JobType.query.order_by(JobType.name).all()
    users = User.query.filter_by(active=True).filter(User.role.in_(['staff', 'admin'])).all()
    if request.method == 'POST':
        due = request.form.get('due_date')
        due_dt = datetime.strptime(due, '%Y-%m-%d') if due else None
        amount_invoiced = request.form.get('amount_invoiced') or 0
        job = Job(
            customer_id=int(request.form['customer_id']),
            job_type=request.form['job_type'],
            assigned_to=int(request.form['assigned_to']) if request.form.get('assigned_to') else None,
            due_date=due_dt,
            priority=request.form.get('priority', 'Medium'),
            internal_notes=request.form.get('internal_notes'),
            amount_invoiced=float(amount_invoiced),
            amount_received=0,
            created_by=session['user_id'],
            status='Pending Finance Approval'
        )
        db.session.add(job)
        db.session.commit()
        update = JobUpdate(job_id=job.id, status='Pending Finance Approval',
                           remark='Task created — awaiting finance approval', staff_name=session['user_name'])
        db.session.add(update)
        db.session.commit()
        flash('Job created successfully')
        return redirect(url_for('jobs'))
    return render_template('add_job.html', customers=customers, job_types=job_types, users=users)

@app.route('/jobs/<int:job_id>', methods=['GET', 'POST'])
@login_required
def job_detail(job_id):
    job = Job.query.get_or_404(job_id)
    now = datetime.now()
    role = session['role']
    # Finance can see all jobs; staff only their own; admin all
    if role == 'staff' and job.assigned_to != session['user_id']:
        flash('Access denied')
        return redirect(url_for('jobs'))
    if request.method == 'POST':
        # Block staff from updating if pending finance approval
        if job.status == 'Pending Finance Approval' and role == 'staff':
            flash('This task is pending finance approval. You cannot update it yet.')
            return redirect(url_for('job_detail', job_id=job_id))
        remark = request.form.get('remark', '').strip()
        if not remark:
            flash('Remark is required')
            return redirect(url_for('job_detail', job_id=job_id))
        new_status = request.form.get('status', job.status)
        # Don't allow staff to set back to Pending Finance Approval
        if role == 'staff' and new_status == 'Pending Finance Approval':
            new_status = job.status
        job.status = new_status
        update = JobUpdate(job_id=job.id, status=new_status,
                           remark=remark, staff_name=session['user_name'])
        db.session.add(update)
        db.session.commit()
        flash('Task updated')
        return redirect(url_for('job_detail', job_id=job_id))
    users = User.query.filter_by(active=True).filter(User.role.in_(['staff', 'admin'])).all()
    return render_template('job_detail.html', job=job, now=now,
                           statuses=JOB_STATUSES, users=users)

@app.route('/jobs/<int:job_id>/edit', methods=['GET', 'POST'])
@login_required
@admin_required
def edit_job(job_id):
    job = Job.query.get_or_404(job_id)
    customers = Customer.query.order_by(Customer.name).all()
    job_types = JobType.query.order_by(JobType.name).all()
    users = User.query.filter_by(active=True).filter(User.role.in_(['staff', 'admin'])).all()
    if request.method == 'POST':
        job.job_type = request.form['job_type']
        job.customer_id = int(request.form['customer_id'])
        assigned = request.form.get('assigned_to')
        job.assigned_to = int(assigned) if assigned else None
        due = request.form.get('due_date')
        job.due_date = datetime.strptime(due, '%Y-%m-%d') if due else None
        job.priority = request.form.get('priority', 'Medium')
        job.internal_notes = request.form.get('internal_notes')
        try:
            ai = request.form.get('amount_invoiced')
            ar = request.form.get('amount_received')
            if ai: job.amount_invoiced = float(ai)
            if ar: job.amount_received = float(ar)
        except:
            pass
        db.session.commit()
        flash('Job updated')
        return redirect(url_for('job_detail', job_id=job_id))
    return render_template('edit_job.html', job=job, customers=customers,
                           job_types=job_types, users=users, statuses=JOB_STATUSES)

@app.route('/jobs/<int:job_id>/delete')
@login_required
@admin_required
def delete_job(job_id):
    job = Job.query.get_or_404(job_id)
    JobUpdate.query.filter_by(job_id=job_id).delete()
    db.session.delete(job)
    db.session.commit()
    flash('Job deleted')
    return redirect(url_for('jobs'))

# ── Finance ───────────────────────────────────────────────────────────────────

@app.route('/jobs/<int:job_id>/approve', methods=['POST'])
@login_required
@finance_required
def approve_job(job_id):
    job = Job.query.get_or_404(job_id)
    amount_invoiced = request.form.get('amount_invoiced', '').strip()
    amount_received = request.form.get('amount_received', '').strip()
    try:
        if amount_invoiced:
            job.amount_invoiced = float(amount_invoiced)
        if amount_received:
            job.amount_received = float(amount_received)
    except:
        pass
    job.status = 'Assigned'
    job.finance_approved_by = session['user_id']
    job.finance_approved_at = datetime.now()
    notes = request.form.get('finance_notes', '').strip()
    remark = f'Approved by Finance. Invoiced: AED {job.amount_invoiced or 0:,.0f} / Received: AED {job.amount_received or 0:,.0f}'
    if notes:
        remark += f'. Notes: {notes}'
    update = JobUpdate(job_id=job.id, status='Assigned', remark=remark, staff_name=session['user_name'])
    db.session.add(update)
    db.session.commit()
    flash('Task approved and assigned to staff.')
    return redirect(url_for('dashboard'))

@app.route('/jobs/<int:job_id>/payment', methods=['POST'])
@login_required
@finance_required
def update_payment(job_id):
    job = Job.query.get_or_404(job_id)
    try:
        job.amount_invoiced = float(request.form.get('amount_invoiced') or job.amount_invoiced or 0)
        job.amount_received = float(request.form.get('amount_received') or job.amount_received or 0)
    except:
        pass
    notes = request.form.get('finance_notes', '').strip()
    remark = f'Payment updated. Invoiced: AED {job.amount_invoiced:,.0f} / Received: AED {job.amount_received:,.0f}'
    if notes:
        remark += f'. Notes: {notes}'
    update = JobUpdate(job_id=job.id, status=job.status, remark=remark, staff_name=session['user_name'])
    db.session.add(update)
    db.session.commit()
    flash('Payment updated.')
    return redirect(request.referrer or url_for('jobs'))

# ── Sub-tasks ─────────────────────────────────────────────────────────────────

@app.route('/jobs/<int:job_id>/subtasks/add', methods=['POST'])
@login_required
@admin_required
def add_subtask(job_id):
    Job.query.get_or_404(job_id)
    assigned = request.form.get('assigned_to')
    subtask = SubTask(
        job_id=job_id,
        title=request.form['title'],
        assigned_to=int(assigned) if assigned else None
    )
    db.session.add(subtask)
    db.session.commit()
    flash('Sub-task added.')
    return redirect(url_for('job_detail', job_id=job_id))

@app.route('/subtasks/<int:subtask_id>/done', methods=['POST'])
@login_required
def complete_subtask(subtask_id):
    subtask = SubTask.query.get_or_404(subtask_id)
    if session['role'] != 'admin' and subtask.assigned_to != session['user_id']:
        flash('Access denied')
        return redirect(url_for('jobs'))
    subtask.status = 'Done'
    subtask.remarks = request.form.get('remarks', '')
    subtask.completed_at = datetime.now()
    db.session.commit()
    flash('Sub-task marked done.')
    return redirect(url_for('job_detail', job_id=subtask.job_id))

@app.route('/subtasks/<int:subtask_id>/delete')
@login_required
@admin_required
def delete_subtask(subtask_id):
    subtask = SubTask.query.get_or_404(subtask_id)
    job_id = subtask.job_id
    db.session.delete(subtask)
    db.session.commit()
    flash('Sub-task removed.')
    return redirect(url_for('job_detail', job_id=job_id))

# ── Admin — Job Types ─────────────────────────────────────────────────────────

@app.route('/admin/jobtype/add', methods=['POST'])
@login_required
@admin_required
def admin_add_jobtype():
    name = request.form.get('name', '').strip()
    if name:
        if not JobType.query.filter_by(name=name).first():
            db.session.add(JobType(name=name))
            db.session.commit()
            flash(f'Job type "{name}" added')
        else:
            flash('Job type already exists')
    return redirect(url_for('admin_panel'))

@app.route('/admin/jobtype/<int:jobtype_id>/delete')
@login_required
@admin_required
def admin_delete_jobtype(jobtype_id):
    jt = JobType.query.get_or_404(jobtype_id)
    db.session.delete(jt)
    db.session.commit()
    flash(f'Job type "{jt.name}" removed')
    return redirect(url_for('admin_panel'))

# ─────────────────────────────────────────────────────────────────────────────

def init_db():
    with app.app_context():
        db.create_all()
        try:
            with db.engine.connect() as conn:
                conn.execute(db.text('ALTER TABLE lead ADD COLUMN IF NOT EXISTS potential_value FLOAT DEFAULT 0'))
                conn.execute(db.text('ALTER TABLE lead ADD COLUMN IF NOT EXISTS phone2 VARCHAR(20)'))
                conn.execute(db.text('ALTER TABLE job ADD COLUMN IF NOT EXISTS amount_invoiced FLOAT DEFAULT 0'))
                conn.execute(db.text('ALTER TABLE job ADD COLUMN IF NOT EXISTS finance_approved_by INTEGER'))
                conn.execute(db.text('ALTER TABLE job ADD COLUMN IF NOT EXISTS finance_approved_at TIMESTAMP'))
                conn.commit()
        except:
            pass
        try:
            admin = User.query.filter_by(email='admin@tahfeel.ae').first()
            if not admin:
                new_admin = User(
                    name='Admin', email='admin@tahfeel.ae',
                    password=generate_password_hash('tahfeel2026'), role='admin'
                )
                db.session.add(new_admin)
                db.session.commit()
                print('Admin user created')
            else:
                print('Admin already exists — skipping')
            if Service.query.count() == 0:
                for s in ['Trade License', 'Family Visa', 'PRO Services', 'Healthcare License', 'Umrah Package', 'Other']:
                    db.session.add(Service(name=s))
                db.session.commit()
                print('Default services created')
            if Source.query.count() == 0:
                for s in ['Walk-in', 'WhatsApp', 'Referral', 'Social Media', 'Website', 'Other']:
                    db.session.add(Source(name=s))
                db.session.commit()
                print('Default sources created')
            if JobType.query.count() == 0:
                for jt in ['Trade License', 'Family Visa', 'PRO Services', 'Healthcare License', 'Umrah Package', 'Other']:
                    db.session.add(JobType(name=jt))
                db.session.commit()
                print('Default job types created')
        except Exception as e:
            db.session.rollback()
            print(f'Init db error: {e}')

if __name__ == '__main__':
    init_db()
    app.run(debug=True, host='0.0.0.0', port=5000)
else:
    init_db()
