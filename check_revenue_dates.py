# Quick script to check revenue dates vs closed dates
from app import app, db, Job
from datetime import datetime

with app.app_context():
    # Get recently closed tasks
    closed = Job.query.filter(
        Job.status.in_(['Closed', 'Closed - Pending Partner Commission'])
    ).order_by(Job.created_at.desc()).limit(20).all()
    
    print("\n=== CLOSED TASKS - REVENUE DATE CHECK ===\n")
    print(f"{'ID':<6} {'Customer':<30} {'Revenue':<10} {'Closed Date':<12} {'Revenue Date':<12} {'Match?'}")
    print("-" * 100)
    
    for j in closed:
        cust = j.customer.name[:28] if j.customer else "N/A"
        rev = j.revenue or 0
        
        # Get last status update to "Closed"
        closed_update = None
        for upd in j.updates:
            if 'Closed' in upd.notes:
                closed_update = upd.created_at.date()
                break
        
        rev_date = j.revenue_date if j.revenue_date else None
        match = "✓" if (closed_update and rev_date and closed_update == rev_date) else "✗"
        
        print(f"{j.id:<6} {cust:<30} {rev:<10.0f} {str(closed_update):<12} {str(rev_date):<12} {match}")

