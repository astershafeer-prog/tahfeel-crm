from flask import Flask, render_template, request, redirect, url_for, session, flash
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timedelta
from functools import wraps
import os

app = Flask(__name__)
app.secret_key = 'tahfeel2026secretkey'
basedir = os.path.abspath(os.path.dirname(__file__))
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(basedir, 'tahfeel.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

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
        pending = [l for l in leads if l.status not in ['Converted', 'Lost']]
        users = User.query.filter_by(active=True).all()
        return render_template('dashboard_admin.html', leads=leads, total=total,
                               overdue=overdue, converted=converted, pending=pending,
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

@app.route('/leads/add', methods=['GET', 'POST'])
@login_required
def add_lead():
    users = User.query.filter_by(active=True, role='staff').all()
    if request.method == 'POST':
        due = request.form.get('due_date')
        due_dt = datetime.strptime(due, '%Y-%m-%dT%H:%M') if due else datetime.now() + timedelta(hours=4)
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
    return render_template('add_lead.html', users=users)

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
            lead_id=lead.id,
            stage=stage,
            remark=remark,
            staff_name=session['user_name'],
            followup_date=followup_dt,
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

@app.route('/users', methods=['GET', 'POST'])
@login_required
@admin_required
def manage_users():
    if request.method == 'POST':
        user = User(
            name=request.form['name'],
            email=request.form['email'],
            password=generate_password_hash(request.form['password']),
            role=request.form['role']
        )
        db.session.add(user)
        db.session.commit()
        flash('User added')
        return redirect(url_for('manage_users'))
    users = User.query.all()
    return render_template('users.html', users=users)

@app.route('/users/<int:user_id>/toggle')
@login_required
@admin_required
def toggle_user(user_id):
    user = User.query.get_or_404(user_id)
    user.active = not user.active
    db.session.commit()
    return redirect(url_for('manage_users'))

def init_db():
    with app.app_context():
        db.create_all()
        if not User.query.filter_by(email='admin@tahfeel.ae').first():
            admin = User(
                name='Admin',
                email='admin@tahfeel.ae',
                password=generate_password_hash('tahfeel2026'),
                role='admin'
            )
            db.session.add(admin)
            db.session.commit()

init_db()

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
