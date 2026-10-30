"""
Optional: fill a DEVELOPMENT database with sample users, projects and timesheets.

    python manage.py seed_demo
    python manage.py seed_demo --password "Something-Long-1234"

Creates one administrator (demo_admin) and four employees. The command refuses
to run when DEBUG is off so demo accounts never reach a real server.
"""
import random
from datetime import time, timedelta
from decimal import Decimal

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from timesheets.hours import calculate_total_hours, split_regular_overtime
from timesheets.models import Project, TimesheetEntry
from timesheets.services import change_status

User = get_user_model()

EMPLOYEES = [
    ("amara", "Amara", "Okafor", "Engineering", "Software Developer", "42.00"),
    ("ben", "Ben", "Lindqvist", "Engineering", "QA Analyst", "38.00"),
    ("carla", "Carla", "Mendoza", "Operations", "Operations Coordinator", "34.50"),
    ("dev", "Dev", "Raman", "Finance", "Accounts Officer", "36.00"),
]
PROJECTS = [
    ("Website Redesign", "WEB-01", "Northwind Traders"),
    ("Mobile App Build", "APP-02", "Contoso Retail"),
    ("Quarterly Audit Support", "AUD-03", "Internal"),
    ("Office Relocation", "OPS-04", "Internal"),
]
TASKS = [
    "Implemented feature work and code review",
    "Client workshop and requirements follow-up",
    "Testing, bug triage and regression checks",
    "Prepared documentation and status report",
    "Data reconciliation and ledger checks",
    "Vendor coordination and scheduling",
]


class Command(BaseCommand):
    help = "Create demo users, projects and timesheet entries (development only)."

    def add_arguments(self, parser):
        parser.add_argument("--password", default="Demo-Pass-2026!x",
                            help="Password given to every demo account.")

    @transaction.atomic
    def handle(self, *args, **options):
        if not settings.DEBUG:
            raise CommandError("seed_demo only runs with DJANGO_DEBUG=True (development).")
        rng = random.Random(42)
        password = options["password"]

        admin, created = User.objects.get_or_create(
            username="demo_admin",
            defaults={"first_name": "Dana", "last_name": "Whitfield", "email": "dana@example.com",
                      "is_staff": True, "is_superuser": True},
        )
        if created:
            admin.set_password(password)
            admin.save()
            admin.profile.department = "Administration"
            admin.profile.job_title = "Office Manager"
            admin.profile.save()

        employees = []
        for username, first, last, dept, title, rate in EMPLOYEES:
            user, created = User.objects.get_or_create(
                username=username,
                defaults={"first_name": first, "last_name": last, "email": f"{username}@example.com"},
            )
            if created:
                user.set_password(password)
                user.save()
                user.profile.department = dept
                user.profile.job_title = title
                user.profile.hourly_rate = Decimal(rate)
                user.profile.save()
            employees.append(user)

        projects = []
        for name, code, client in PROJECTS:
            project, _ = Project.objects.get_or_create(
                code=code, defaults={"name": name, "client_name": client, "status": Project.Status.ACTIVE},
            )
            projects.append(project)

        if TimesheetEntry.objects.exists():
            self.stdout.write(self.style.WARNING("Timesheet entries already exist; skipping sample entries."))
        else:
            today = timezone.localdate()
            count = 0
            for employee in employees:
                for offset in range(1, 75):
                    day = today - timedelta(days=offset)
                    if day.weekday() >= 5 or rng.random() < 0.12:
                        continue
                    start_hour = rng.choice([7, 8, 8, 9])
                    length = rng.choice([7, 8, 8, 8, 9, 10])
                    start = time(start_hour, rng.choice([0, 0, 30]))
                    end_minutes = (start_hour * 60 + start.minute + length * 60 + 45) % 1440
                    end = time(end_minutes // 60, end_minutes % 60)
                    total = calculate_total_hours(start, end, 45)
                    regular, overtime = split_regular_overtime(total)
                    entry = TimesheetEntry.objects.create(
                        employee=employee, created_by=employee,
                        project=rng.choice(projects), work_date=day,
                        task_description=rng.choice(TASKS), time_in=start, time_out=end,
                        break_minutes=45, regular_hours=regular, overtime_hours=overtime,
                        hours_source=TimesheetEntry.HoursSource.CALCULATED,
                        work_location=rng.choice(["Head office", "Remote", "Client site"]),
                    )
                    count += 1
                    roll = rng.random()
                    if offset > 21 or roll < 0.35:
                        change_status(entry, TimesheetEntry.Status.SUBMITTED, employee)
                        if offset > 21 or roll < 0.2:
                            if rng.random() < 0.9:
                                change_status(entry, TimesheetEntry.Status.APPROVED, admin)
                            else:
                                change_status(entry, TimesheetEntry.Status.REJECTED, admin,
                                              comment="Please add the client name and resubmit.")
            self.stdout.write(self.style.SUCCESS(f"Created {count} sample timesheet entries."))

        self.stdout.write(self.style.SUCCESS("Demo data ready."))
        self.stdout.write(f"  Administrator: demo_admin / {password}")
        self.stdout.write(f"  Employees:     {', '.join(e[0] for e in EMPLOYEES)} / {password}")
        self.stdout.write(self.style.WARNING("  Demo passwords are for local development only."))
