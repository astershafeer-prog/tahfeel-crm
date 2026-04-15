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
    return redirect(url_for('dashboard'))

@app.errorhandler(404)
def not_found(error):
    return redirect(url_for('dashboard'))

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
    due_date = db.Column(db.DateTime, default=lambda: datetime.now() + timedelta(hours=4))
    remarks = db.Column(db.Text)
    status = db.Column(db.String(50), default='New')
    created_at = db.Column(db.DateTime, default=datetime.now)
    customer_story = db.Column(db.Text)
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

class Service(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False, unique=True)

class Source(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False, unique=True)

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

def apply_lead_filters(leads, args, now):
    date_filter = args.get('date')
    status_filter = args.get('status')
    staff_filter = args.get('staff')
    if date_filter == 'today':
        leads = [l for l in leads if l.due_date.date() == now.date()]
    elif date_filter == 'week':
        week_start = now.date() - timedelta(days=now.weekday())
        week_end = week_start + timedelta(days=6)
        leads = [l for l in leads if week_start <= l.due_date.date() <= week_end]
    elif date_filter == 'month':
        leads = [l for l in leads if l.due_date.year == now.year and l.due_date.month == now.month]
    elif date_filter == 'custom':
        from_date = args.get('from')
        to_date = args.get('to')
        if from_date:
            from_dt = datetime.strptime(from_date, '%Y-%m-%d').date()
            leads = [l for l in leads if l.due_date.date() >= from_dt]
        if to_date:
            to_dt = datetime.strptime(to_date, '%Y-%m-%d').date()
            leads = [l for l in leads if l.due_date.date() <= to_dt]
    if status_filter:
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
    if session['role'] == 'admin':
        leads = Lead.query.order_by(Lead.due_date).all()
        total = len(leads)
        overdue = [l for l in leads if l.due_date < now and l.status not in ['Converted', 'Lost']]
        converted = [l for l in leads if l.status == 'Converted']
        pending = [l for l in leads if l.status not in ['Converted', 'Lost', 'New']]
        not_started = [l for l in leads if l.status == 'New']
        users = User.query.filter_by(active=True, role='staff').all()
        staff_stats = []
        for u in users:
            u_leads = [l for l in leads if l.assigned_to == u.id]
            staff_stats.append({
                'name': u.name,
                'total': len(u_leads),
                'pending': len([l for l in u_leads if l.status not in ['Converted', 'Lost', 'New']]),
                'not_started': len([l for l in u_leads if l.status == 'New']),
                'converted': len([l for l in u_leads if l.status == 'Converted']),
                'overdue': len([l for l in u_leads if l.due_date < now and l.status not in ['Converted', 'Lost']]),
            })
        return render_template('dashboard_admin.html', leads=leads, total=total,
                               overdue=overdue, converted=converted, pending=pending,
                               not_started=not_started, staff_stats=staff_stats,
                               users=users, now=now)
    else:
        leads = Lead.query.filter_by(assigned_to=session['user_id']).order_by(Lead.due_date).all()
        overdue = [l for l in leads if l.due_date < now and l.status not in ['Converted', 'Lost']]
        followups = LeadUpdate.query.filter(
            LeadUpdate.staff_name == session['user_name'],
            LeadUpdate.followup_date <= now + timedelta(days=1),
            LeadUpdate.followup_date >= now
        ).all()
        return render_template('dashboard_staff.html', leads=leads, overdue=overdue,
                               followups=followups, now=now)

@app.route('/leads')
@login_required
@admin_required
def all_leads():
    now = datetime.now()
    leads = Lead.query.order_by(Lead.due_date).all()
    users = User.query.filter_by(active=True).filter(User.role.in_(['staff', 'admin'])).all()
    leads = apply_lead_filters(leads, request.args, now)
    return render_template('all_leads.html', leads=leads, now=now, users=users)

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
    headers = ['Name', 'Company', 'Phone', 'Email', 'Address', 'Source',
               'Service', 'Lead Type', 'Assigned To', 'Due Date', 'Status', 'Remarks', 'Created']
    ws.append(headers)
    header_font = Font(bold=True, color="FFFFFF")
    header_fill = PatternFill(start_color="133E87", end_color="133E87", fill_type="solid")
    for cell in ws[1]:
        cell.font = header_font
        cell.fill = header_fill
    for lead in leads:
        ws.append([
            lead.name, lead.company or '', lead.phone or '', lead.email or '',
            lead.address or '', lead.source or '', lead.service or '', lead.lead_type or '',
            lead.assignee.name if lead.assignee else '',
            lead.due_date.strftime('%d %b %Y') if lead.due_date else '',
            lead.status or '', lead.remarks or '',
            lead.created_at.strftime('%d %b %Y') if lead.created_at else '',
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
    users = User.query.filter_by(active=True).filter(User.role.in_(['staff', 'admin'])).all()
    services = Service.query.order_by(Service.name).all()
    sources = Source.query.order_by(Source.name).all()
    if request.method == 'POST':
        due = request.form.get('due_date')
        due_dt = datetime.strptime(due, '%Y-%m-%d') if due else datetime.now() + timedelta(hours=4)
        lead = Lead(
            name=request.form['name'],
            company=request.form.get('company'),
            phone=request.form.get('phone'),
            email=request.form.get('email'),
            address=request.form.get('address'),
            source=request.form.get('source'),
            service=request.form.get('service'),
            representative=session['user_name'],
            lead_type=request.form.get('lead_type', 'New'),
            assigned_to=int(request.form['assigned_to']) if request.form.get('assigned_to') else None,
            due_date=due_dt,
            remarks=request.form.get('remarks')
        )
        db.session.add(lead)
        db.session.commit()
        flash('Lead added successfully')
        return redirect(url_for('dashboard'))
    return render_template('add_lead.html', users=users, services=services, sources=sources)

@app.route('/leads/<int:lead_id>', methods=['GET', 'POST'])
@login_required
def lead_detail(lead_id):
    lead = Lead.query.get_or_404(lead_id)
    if request.method == 'POST':
        stage = request.form['stage']
        remark = request.form['remark']
        followup = request.form.get('followup_date')
        followup_dt = datetime.strptime(followup, '%Y-%m-%dT%H:%M') if followup else None
        update = LeadUpdate(
            lead_id=lead.id, stage=stage, remark=remark,
            staff_name=session['user_name'], followup_date=followup_dt,
            lost_reason=request.form.get('lost_reason'),
            future_potential=request.form.get('future_potential')
        )
        lead.status = stage
        if request.form.get('customer_story'):
            lead.customer_story = request.form.get('customer_story')
        db.session.add(update)
        db.session.commit()
        flash('Update saved')
        return redirect(url_for('lead_detail', lead_id=lead_id))
    return render_template('lead_detail.html', lead=lead)

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
                    due_date=datetime.now() + timedelta(hours=4)
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
    from flask import make_response
    import io
    wb = Workbook()
    ws = wb.active
    ws.title = "Leads"
    headers = ['Name*', 'Company', 'Phone*', 'Email', 'Address',
               'Source', 'Service', 'Lead Type', 'Remarks', 'Assigned To']
    ws.append(headers)
    ws.append(['John Smith', 'ABC Trading LLC', '+971501234567',
               'john@abc.ae', 'Dubai', 'WhatsApp', 'Trade License', 'New',
               'Interested in mainland license', 'Aslam'])
    ws.append(['Sara Ahmed', '', '+971509876543', '', 'Sharjah',
               'Referral', 'Family Visa', 'New', '', 'Anfal'])
    from openpyxl.styles import Font, PatternFill
    header_font = Font(bold=True, color="FFFFFF")
    header_fill = PatternFill(start_color="133E87", end_color="133E87", fill_type="solid")
    for cell in ws[1]:
        cell.font = header_font
        cell.fill = header_fill
    for col in ws.columns:
        max_length = max(len(str(cell.value or '')) for cell in col)
        ws.column_dimensions[col[0].column_letter].width = max_length + 4
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
    lead = Lead.query.get_or_404(lead_id)
    users = User.query.filter_by(active=True).filter(User.role.in_(['staff', 'admin'])).all()
    services = Service.query.order_by(Service.name).all()
    sources = Source.query.order_by(Source.name).all()
    if request.method == 'POST':
        lead.name = request.form['name']
        lead.company = request.form.get('company')
        lead.phone = request.form.get('phone')
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
    return render_template('edit_lead.html', lead=lead, users=users, services=services, sources=sources)

@app.route('/leads/<int:lead_id>/delete')
@login_required
@admin_required
def delete_lead(lead_id):
    lead = Lead.query.get_or_404(lead_id)
    LeadUpdate.query.filter_by(lead_id=lead_id).delete()
    db.session.delete(lead)
    db.session.commit()
    flash('Lead deleted successfully')
    return redirect(url_for('dashboard'))

@app.route('/admin', methods=['GET', 'POST'])
@login_required
@admin_required
def admin_panel():
    users = User.query.order_by(User.name).all()
    services = Service.query.order_by(Service.name).all()
    sources = Source.query.order_by(Source.name).all()
    return render_template('admin_panel.html', users=users, services=services, sources=sources)

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

@app.route('/admin/staff/<int:user_id>/toggle')
@login_required
@admin_required
def admin_toggle_staff(user_id):
    user = User.query.get_or_404(user_id)
    if user.role == 'admin':
        flash('Admin accounts cannot be deactivated')
        return redirect(url_for('admin_panel'))
    user.active = not user.active
    db.session.commit()
    return redirect(url_for('admin_panel'))

@app.route('/admin/staff/<int:user_id>/delete')
@login_required
@admin_required
def admin_delete_staff(user_id):
    user = User.query.get_or_404(user_id)
    if user.role == 'admin':
        flash('Admin accounts cannot be deleted')
        return redirect(url_for('admin_panel'))
    db.session.delete(user)
    db.session.commit()
    flash('Staff member removed')
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
    return redirect(url_for('admin_toggle_staff', user_id=user_id))

def init_db():
    with app.app_context():
        db.create_all()
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
        except Exception as e:
            db.session.rollback()
            print(f'Init db error: {e}')

if __name__ == '__main__':
    init_db()
    app.run(debug=True, host='0.0.0.0', port=5000)
else:
    init_db()
