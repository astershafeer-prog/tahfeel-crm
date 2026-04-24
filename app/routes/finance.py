
@app.route('/close_job/<int:job_id>', methods=['GET', 'POST'])
def close_job(job_id):
    job = Job.query.get_or_404(job_id)
    form = JobCloseForm()

    if form.validate_on_submit():
        job.revenue = form.revenue.data
        job.pending_revenue = job.amount_invoiced - job.amount_received
        job.status = 'Closed'
        db.session.commit()
        # ...
