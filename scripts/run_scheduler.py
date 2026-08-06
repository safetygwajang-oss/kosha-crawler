"""상주 스케줄러 (Docker/서버용)"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger
from kosha_crawler import crawl, settings
from kosha_crawler.utils import setup_logging

log = setup_logging("scheduler")


def job():
    log.info("스케줄 크롤링 시작")
    try:
        crawl()
    except Exception as e:
        log.exception(f"크롤링 실패: {e}")


if __name__ == "__main__":
    scheduler = BlockingScheduler(timezone=settings.TIMEZONE)
    scheduler.add_job(
        job,
        CronTrigger(hour=settings.CRON_HOUR, minute=settings.CRON_MINUTE),
        id="daily_kosha_crawl",
        replace_existing=True,
    )
    log.info(f"스케줄러 시작: 매일 {settings.CRON_HOUR:02d}:{settings.CRON_MINUTE:02d} ({settings.TIMEZONE})")
    job()
    scheduler.start()
