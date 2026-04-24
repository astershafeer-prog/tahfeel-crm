
@app.route('/reports/pending_revenue')
def pending_revenue_report():
    jobs = Job.query.filter(Job.status == 'Closed', Job.pending_revenue > 0).all()
    return render_template('pending_revenue_report.html', jobs=jobs)
