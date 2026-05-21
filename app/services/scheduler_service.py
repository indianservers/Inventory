from datetime import datetime

from app.extensions import db
from app.models import Product, ScheduledJob, ScheduledJobLog
from app.services.communication_service import send_low_stock_alert


def run_scheduled_jobs():
    results = []
    for job in ScheduledJob.query.filter_by(is_active=True).all():
        log = ScheduledJobLog(job_id=job.id, status="Running", started_at=datetime.utcnow())
        db.session.add(log)
        db.session.flush()
        try:
            if job.job_type == "low_stock_alert":
                count = 0
                for product in Product.query.filter(Product.current_stock <= Product.reorder_level).all():
                    send_low_stock_alert(product)
                    count += 1
                log.message = f"Processed {count} low stock item(s)."
            else:
                log.message = "Scheduled job foundation recorded the run. Configure provider/report handler for live delivery."
            job.last_run_at = datetime.utcnow()
            log.status = "Success"
        except Exception as exc:
            log.status = "Failed"
            log.message = str(exc)
        log.finished_at = datetime.utcnow()
        results.append(log)
    db.session.commit()
    return results
