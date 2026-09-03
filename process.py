#!/usr/bin/env python3
"""
Attendance & Punctuality processor
-----------------------------------
Reads a biometric/GPS "Punches" export CSV and produces a single JSON file
(attendance_data.json) consumed by index.html and employee-details.html.

MULTI-MONTH SETUP: this script processes whichever folder it's pointed at.
Your data now lives under "<Fiscal Year>/<Month>/" folders, e.g.
"2026-2027/August-2026/punches.csv". You normally don't run this script
directly anymore — double-click refresh_dashboard.bat / .command at the
project root instead; it runs process.py against every month folder in
one go via refresh_all.py. (You can still run
`python3 process.py "2026-2027/August-2026"` by hand if you only want to
reprocess one month.)

Shift rules (grace = the shift's own minute, i.e. HH:MM:00-HH:MM:59 is on
time, HH:(MM+1):00 onward is late):
    Shift A  08:00 AM  -> Naveenkumar (T3001)
    Shift B  08:30 AM  -> Santhosh Ananthan, Mohammed Haroon, Fouziya Thabasum S
    Shift C  09:30 AM  -> everyone else
    Saturdays -> everyone reports to the 09:30 AM shift, regardless of normal shift.

Holidays:
    - Any day with zero punches from every employee is treated as a holiday.
    - The 2nd and 4th Saturday of every month is a fixed company holiday for
      everyone, even if someone happened to punch in that day (that punch is
      recorded separately as "holiday_worked" info, not counted in stats).
    - You can also declare extra holidays explicitly in holidays.csv (columns:
      Date, Reason) — e.g. festivals, bandhs, office closures. Anything listed
      there is excluded from working days too, with your Reason text shown on
      the dashboard instead of a generic label.
A day with zero punches for one employee (on a working day) = Absent.
A day with only one punch (an IN, no OUT) = Present but "Not Logged Out".

MID-PERIOD JOINERS / RESIGNATIONS:
So new hires aren't marked "absent" before they joined, and people who left
aren't marked "absent" after their last working day, add rows to:
    joined_employees.csv    -> Employee Number, Employee Name, Date of Joining, Shift, Note
        - Date of Joining: DD-MM-YYYY. Days before this are excluded from
          their stats entirely (not present, not absent).
        - Shift: one of "8:00 AM", "8:30 AM", "9:30 AM" (optional — defaults
          to 9:30 AM if left blank). Lets you assign a new hire's shift
          without touching this script.
        - Works even if the employee has zero punches so far — they'll still
          show up on the dashboard with a "Joined" note.
    resigned_employees.csv  -> Employee Number, Employee Name, Last Working Day, Note
        - Last Working Day: DD-MM-YYYY. Days after this are excluded from
          their stats entirely.
Re-run this script after editing any of these; it's safe to run repeatedly.

MANUAL CORRECTIONS (e.g. times reported over WhatsApp when the app failed
to capture a punch):
Add a row to manual_corrections.csv (same folder) with columns:
    Employee Number, Punch Date, Punch Time, Note
    - Employee Number: must match the ID used in punches.csv (e.g. 2001, T3001)
    - Punch Date: DD-MM-YYYY, same as the main export
    - Punch Time: HH:MM:SS, 24-hour
    - Note: free text, e.g. "Reported via WhatsApp - phone GPS was off"
Each row is merged in as if it were a real punch, so it can turn an "Absent"
day into "Present/Late", or supply a missing OUT time. The dashboard tags
any day touched this way as "Manual (WhatsApp)" so it stays auditable.
Re-run this script after adding rows; it's safe to run repeatedly.
"""

import csv
import json
import os
import datetime
from collections import defaultdict

SRC = "punches.csv"
MANUAL_SRC = "manual_corrections.csv"
HOLIDAYS_SRC = "holidays.csv"
RESIGNED_SRC = "resigned_employees.csv"
JOINED_SRC = "joined_employees.csv"
OUT = "attendance_data.json"
DATA_JS_OUT = "data.js"

# Collected as we go so problems show up on the dashboard, not just a crash
# in a terminal window nobody was watching.
WARNINGS = []


def warn(msg):
    WARNINGS.append(msg)
    print("WARNING:", msg)


# Excel silently rewrites dates depending on the machine's regional settings
# (typing 21-08-2026 can come back as 21/08/2026, 8/21/2026, 2026-08-21...).
# Try every format we're likely to see instead of assuming one.
DATE_FORMATS = ["%d-%m-%Y", "%d/%m/%Y", "%Y-%m-%d", "%m/%d/%Y", "%d.%m.%Y", "%d-%m-%y", "%d/%m/%y"]
TIME_FORMATS = ["%H:%M:%S", "%H:%M", "%I:%M:%S %p", "%I:%M %p"]


def parse_date_flex(raw, context=""):
    s = (raw or "").strip()
    if not s:
        return None
    for fmt in DATE_FORMATS:
        try:
            return datetime.datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    warn(f"Could not read date '{raw}' {context} — row skipped. Use DD-MM-YYYY (e.g. 21-08-2026).")
    return None


def parse_time_flex(raw, context=""):
    s = (raw or "").strip()
    if not s:
        return None
    for fmt in TIME_FORMATS:
        try:
            return datetime.datetime.strptime(s, fmt).time()
        except ValueError:
            continue
    warn(f"Could not read time '{raw}' {context} — row skipped. Use 24-hour HH:MM:SS (e.g. 09:25:00).")
    return None


# ---- Shift configuration -------------------------------------------------
SHIFT_A = {"code": "A", "label": "8:00 AM", "hour": 8, "minute": 0}
SHIFT_B = {"code": "B", "label": "8:30 AM", "hour": 8, "minute": 30}
SHIFT_C = {"code": "C", "label": "9:30 AM", "hour": 9, "minute": 30}
SATURDAY_SHIFT = SHIFT_C

EMP_SHIFT = {
    "T3001": SHIFT_A,      # Naveenkumar
    "2055": SHIFT_B,       # Santhosh Ananthan
    "2050": SHIFT_B,       # Mohammed Haroon
    "2056": SHIFT_B,       # Fouziya Thabasum S
    # all others default to SHIFT_C (assigned below when first seen)
}


SHIFT_BY_LABEL = {"8:00 AM": SHIFT_A, "8:30 AM": SHIFT_B, "9:30 AM": SHIFT_C}


def shift_for(emp_id, punch_date):
    """Return the shift dict that applies to this employee on this date."""
    base = EMP_SHIFT.get(emp_id, SHIFT_C)
    if punch_date.strftime("%A") == "Saturday":
        return SATURDAY_SHIFT
    return base


def is_late(punch_time, shift):
    """Grace period = the shift's own minute. Late starts at the next minute."""
    shift_total_seconds = shift["hour"] * 3600 + shift["minute"] * 60 + 59
    punch_total_seconds = punch_time.hour * 3600 + punch_time.minute * 60 + punch_time.second
    return punch_total_seconds > shift_total_seconds


def late_by_seconds(punch_time, shift):
    shift_start = shift["hour"] * 3600 + shift["minute"] * 60
    grace_end = shift_start + 59
    punch_total_seconds = punch_time.hour * 3600 + punch_time.minute * 60 + punch_time.second
    diff = punch_total_seconds - grace_end
    return max(diff, 0)


def fmt_hms(total_seconds):
    h = total_seconds // 3600
    m = (total_seconds % 3600) // 60
    s = total_seconds % 60
    parts = []
    if h:
        parts.append(f"{h}h")
    if m:
        parts.append(f"{m}m")
    if not h and not m:
        parts.append(f"{s}s")
    return " ".join(parts) if parts else "0m"


def nth_saturday_holidays(calendar_days):
    """Company policy: the 2nd and 4th Saturday of every month is a holiday."""
    saturdays_by_month = defaultdict(list)
    for d in calendar_days:
        if d.strftime("%A") == "Saturday":
            saturdays_by_month[(d.year, d.month)].append(d)

    policy_holidays = set()
    for month_key, sats in saturdays_by_month.items():
        sats.sort()
        for idx, d in enumerate(sats, start=1):  # idx = 1st, 2nd, 3rd... Saturday
            if idx in (2, 4):
                policy_holidays.add(d)
    return policy_holidays


def load_holidays_csv(path):
    """holidays.csv columns: Date, Reason. Returns {date: reason}."""
    out = {}
    if not os.path.exists(path):
        return out
    with open(path, encoding="utf-8-sig") as f:
        for i, r in enumerate(csv.DictReader(f), start=2):  # row 2 = first data row (1 = header)
            date_str = (r.get("Date") or "").strip()
            reason = (r.get("Reason") or "").strip()
            if not date_str:
                continue
            d = parse_date_flex(date_str, f"in {HOLIDAYS_SRC} row {i}")
            if d is None:
                continue
            out[d] = reason or "Declared holiday"
    return out


def load_joined_employees(path):
    """joined_employees.csv columns: Employee Number, Employee Name, Date of Joining, Shift, Note.
       Returns {emp_id: {"name":..., "joining_date": date, "shift": shift_dict|None, "note":...}}"""
    out = {}
    if not os.path.exists(path):
        return out
    with open(path, encoding="utf-8-sig") as f:
        for i, r in enumerate(csv.DictReader(f), start=2):
            emp_id = (r.get("Employee Number") or "").strip()
            date_str = (r.get("Date of Joining") or "").strip()
            if not emp_id and not date_str:
                continue  # blank row, ignore quietly
            if not emp_id:
                warn(f"{JOINED_SRC} row {i}: missing Employee Number — row skipped.")
                continue
            d = parse_date_flex(date_str, f"in {JOINED_SRC} row {i} (Employee {emp_id})")
            if d is None:
                continue
            name = (r.get("Employee Name") or "").strip()
            shift_label = (r.get("Shift") or "").strip()
            note = (r.get("Note") or "").strip()
            if shift_label and shift_label not in SHIFT_BY_LABEL:
                warn(f"{JOINED_SRC} row {i}: Shift '{shift_label}' not recognised (use 8:00 AM / 8:30 AM / 9:30 AM) — defaulting to 9:30 AM.")
            out[emp_id] = {
                "name": name,
                "joining_date": d,
                "shift": SHIFT_BY_LABEL.get(shift_label),
                "note": note or "New joiner",
            }
    return out


def load_resigned_employees(path):
    """resigned_employees.csv columns: Employee Number, Employee Name, Last Working Day, Note.
       Returns {emp_id: {"name":..., "last_day": date, "note":...}}"""
    out = {}
    if not os.path.exists(path):
        return out
    with open(path, encoding="utf-8-sig") as f:
        for i, r in enumerate(csv.DictReader(f), start=2):
            emp_id = (r.get("Employee Number") or "").strip()
            date_str = (r.get("Last Working Day") or "").strip()
            if not emp_id and not date_str:
                continue
            if not emp_id:
                warn(f"{RESIGNED_SRC} row {i}: missing Employee Number — row skipped.")
                continue
            d = parse_date_flex(date_str, f"in {RESIGNED_SRC} row {i} (Employee {emp_id})")
            if d is None:
                continue
            name = (r.get("Employee Name") or "").strip()
            note = (r.get("Note") or "").strip()
            out[emp_id] = {
                "name": name,
                "last_day": d,
                "note": note or "Resigned",
            }
    return out


def load_manual_corrections(path, known_ids):
    """Read manual_corrections.csv if present. Returns:
       extra_punches[emp_id][date] = [time, ...]
       manual_notes[(emp_id, date)] = ["note1", ...]
    """
    extra_punches = defaultdict(lambda: defaultdict(list))
    manual_notes = defaultdict(list)
    if not os.path.exists(path):
        return extra_punches, manual_notes

    with open(path, encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))

    for i, r in enumerate(rows, start=2):
        emp_id = (r.get("Employee Number") or "").strip()
        date_str = (r.get("Punch Date") or "").strip()
        time_str = (r.get("Punch Time") or "").strip()
        note = (r.get("Note") or "").strip()
        if not emp_id and not date_str and not time_str:
            continue  # blank row
        if not emp_id:
            warn(f"{MANUAL_SRC} row {i}: missing Employee Number — row skipped.")
            continue
        if emp_id not in known_ids:
            warn(f"{MANUAL_SRC} row {i}: Employee Number '{emp_id}' doesn't match anyone in {SRC} "
                 f"or {JOINED_SRC} — check for typos or extra spaces. Row skipped.")
            continue
        d = parse_date_flex(date_str, f"in {MANUAL_SRC} row {i} (Employee {emp_id})")
        t = parse_time_flex(time_str, f"in {MANUAL_SRC} row {i} (Employee {emp_id})")
        if d is None or t is None:
            continue
        extra_punches[emp_id][d].append(t)
        manual_notes[(emp_id, d)].append(note or "Manually entered (WhatsApp)")

    return extra_punches, manual_notes


def main():
    with open(SRC, encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))

    employees = {}  # emp_id -> name
    # punches[emp_id][date] = list of datetime.time
    punches = defaultdict(lambda: defaultdict(list))
    all_dates = set()

    for i, r in enumerate(rows, start=2):
        emp_id = (r.get("Employee Number") or "").strip()
        name = (r.get("Employee Name") or "").strip()
        date_str = (r.get("Punch Date") or "").strip()
        time_str = (r.get("Punch Time") or "").strip()
        if not emp_id:
            warn(f"{SRC} row {i}: missing Employee Number — row skipped.")
            continue
        d = parse_date_flex(date_str, f"in {SRC} row {i} (Employee {emp_id})")
        t = parse_time_flex(time_str, f"in {SRC} row {i} (Employee {emp_id})")
        if d is None or t is None:
            continue
        employees[emp_id] = name
        punches[emp_id][d].append(t)
        all_dates.add(d)

    # ---- Joined / resigned employees (loaded first so a brand-new hire's
    # ID is already "known" by the time we validate manual_corrections.csv)
    joined = load_joined_employees(JOINED_SRC)
    resigned = load_resigned_employees(RESIGNED_SRC)

    for emp_id, info in joined.items():
        if info["name"] and emp_id not in employees:
            employees[emp_id] = info["name"]
        if info["shift"]:
            EMP_SHIFT[emp_id] = info["shift"]
        all_dates.add(info["joining_date"])

    for emp_id, info in resigned.items():
        if info["name"] and emp_id not in employees:
            employees[emp_id] = info["name"]
        all_dates.add(info["last_day"])

    # ---- Merge manual (WhatsApp) corrections --------------------------
    extra_punches, manual_notes = load_manual_corrections(MANUAL_SRC, set(employees.keys()))
    manual_days = set()  # (emp_id, date) touched by a manual entry
    for emp_id, by_date in extra_punches.items():
        for d, times in by_date.items():
            punches[emp_id][d].extend(times)
            all_dates.add(d)
            manual_days.add((emp_id, d))

    # ---- Explicit holidays.csv ------------------------------------------
    explicit_holidays = load_holidays_csv(HOLIDAYS_SRC)
    all_dates.update(explicit_holidays.keys())

    min_date, max_date = min(all_dates), max(all_dates)

    # Build the full calendar of days in range, Mon-Sat only (Sunday = weekly off)
    calendar_days = []
    d = min_date
    while d <= max_date:
        if d.strftime("%A") != "Sunday":
            calendar_days.append(d)
        d += datetime.timedelta(days=1)

    # A day is a company holiday if NOBODY punched at all that day, OR it
    # falls on the 2nd/4th Saturday of the month (company policy), OR it's
    # explicitly listed in holidays.csv.
    punched_dates = set()
    for emp_id in punches:
        punched_dates.update(punches[emp_id].keys())

    policy_holidays = nth_saturday_holidays(calendar_days)
    zero_punch_holidays = {d for d in calendar_days if d not in punched_dates}
    declared_holidays = set(explicit_holidays.keys()) & set(calendar_days)
    holidays_set = zero_punch_holidays | policy_holidays | declared_holidays

    def holiday_reason(d):
        if d in explicit_holidays:
            return explicit_holidays[d]
        if d in policy_holidays:
            return "2nd/4th Saturday — company holiday"
        return "No punches recorded — assumed holiday"

    # Any punches recorded on a day now marked a holiday (2nd/4th Saturday or
    # an explicitly declared one) are kept as an FYI list, not counted in stats.
    holiday_worked = []
    for d in sorted(policy_holidays | declared_holidays):
        if d in punched_dates:
            for emp_id, by_date in punches.items():
                if d in by_date:
                    times = sorted(by_date[d])
                    holiday_worked.append({
                        "emp_id": emp_id,
                        "name": employees.get(emp_id, emp_id),
                        "date": d.isoformat(),
                        "punches": [t.strftime("%H:%M:%S") for t in times],
                    })

    working_days = sorted(d for d in calendar_days if d not in holidays_set)
    holidays = sorted(holidays_set)
    holiday_reasons = {d.isoformat(): holiday_reason(d) for d in holidays}

    emp_ids_sorted = sorted(employees.keys(), key=lambda e: employees[e])

    daily_records = []       # flat list, one row per employee per working day
    per_employee_summary = {}

    for emp_id in emp_ids_sorted:
        name = employees[emp_id]
        shift_default = EMP_SHIFT.get(emp_id, SHIFT_C)

        join_info = joined.get(emp_id)
        resign_info = resigned.get(emp_id)
        emp_start = join_info["joining_date"] if join_info else working_days[0]
        emp_end = resign_info["last_day"] if resign_info else working_days[-1]
        emp_working_days = [d for d in working_days if emp_start <= d <= emp_end]

        summary = {
            "id": emp_id,
            "name": name,
            "shift": shift_default["label"],
            "shift_code": shift_default["code"],
            "present": 0,
            "absent": 0,
            "late": 0,
            "late_after_10am": 0,
            "on_time": 0,
            "no_logout": 0,
            "manual_entries": 0,
            "working_days": len(emp_working_days),
            "employment_status": "Resigned" if resign_info else ("Joined mid-period" if join_info else "Active"),
            "joining_date": join_info["joining_date"].isoformat() if join_info else None,
            "joining_note": join_info["note"] if join_info else None,
            "last_working_day": resign_info["last_day"].isoformat() if resign_info else None,
            "resigned_note": resign_info["note"] if resign_info else None,
        }

        for d in emp_working_days:
            times = sorted(punches[emp_id].get(d, []))
            shift = shift_for(emp_id, d)
            record = {
                "emp_id": emp_id,
                "name": name,
                "date": d.isoformat(),
                "weekday": d.strftime("%A"),
                "shift_label": shift["label"] + (" (Sat)" if d.strftime("%A") == "Saturday" else ""),
            }

            is_manual = (emp_id, d) in manual_days
            if is_manual:
                record["manual_entry"] = True
                record["manual_note"] = "; ".join(manual_notes[(emp_id, d)])
                summary["manual_entries"] += 1
            else:
                record["manual_entry"] = False
                record["manual_note"] = None

            if not times:
                record["status"] = "Absent"
                record["in_time"] = None
                record["out_time"] = None
                record["late_by"] = None
                record["punch_count"] = 0
                summary["absent"] += 1
            else:
                in_time = times[0]
                out_time = times[-1] if len(times) > 1 else None
                late = is_late(in_time, shift)
                record["in_time"] = in_time.strftime("%H:%M:%S")
                record["out_time"] = out_time.strftime("%H:%M:%S") if out_time else None
                record["punch_count"] = len(times)
                record["late_by"] = fmt_hms(late_by_seconds(in_time, shift)) if late else None

                summary["present"] += 1
                if late:
                    summary["late"] += 1
                    record["status"] = "Late"
                else:
                    summary["on_time"] += 1
                    record["status"] = "On Time"

                # "Late after 10 AM" only applies to employees whose own
                # (non-Saturday) shift is the 9:30 AM shift — i.e. Shift C
                # people. It flags a stricter, more visible threshold beyond
                # normal lateness: arriving at/after 10:00:00, not just past
                # the 9:30 grace minute.
                record["late_after_10am"] = (
                    shift_default["code"] == "C" and in_time >= datetime.time(10, 0, 0)
                )
                if record["late_after_10am"]:
                    summary["late_after_10am"] += 1

                if out_time is None:
                    summary["no_logout"] += 1
                    record["no_logout"] = True
                else:
                    record["no_logout"] = False

            daily_records.append(record)

        summary["attendance_pct"] = round(100 * summary["present"] / summary["working_days"], 1) if summary["working_days"] else 0
        summary["punctuality_pct"] = round(100 * summary["on_time"] / summary["present"], 1) if summary["present"] else 0
        per_employee_summary[emp_id] = summary

    data = {
        "generated_at": datetime.datetime.now().isoformat(timespec="seconds"),
        "source_file": SRC,
        "date_range": {"start": min_date.isoformat(), "end": max_date.isoformat()},
        "working_days": [d.isoformat() for d in working_days],
        "holidays": [d.isoformat() for d in holidays],
        "holiday_reasons": holiday_reasons,
        "holiday_worked": holiday_worked,
        "joined_employees": [
            {"emp_id": eid, "name": employees.get(eid, info["name"]), "joining_date": info["joining_date"].isoformat(), "note": info["note"]}
            for eid, info in sorted(joined.items(), key=lambda kv: kv[1]["joining_date"])
        ],
        "resigned_employees": [
            {"emp_id": eid, "name": employees.get(eid, info["name"]), "last_working_day": info["last_day"].isoformat(), "note": info["note"]}
            for eid, info in sorted(resigned.items(), key=lambda kv: kv[1]["last_day"])
        ],
        "shift_rules": {
            "A": "8:00 AM (Naveenkumar)",
            "B": "8:30 AM (Santhosh, Haroon, Fouziya)",
            "C": "9:30 AM (all others)",
            "saturday": "Everyone reports at 9:30 AM on Saturdays",
            "grace": "On time up to HH:MM:59 of the shift minute; late begins at HH:(MM+1):00",
            "holiday_policy": "2nd and 4th Saturday of every month is a paid holiday for everyone",
        },
        "manual_corrections_file": MANUAL_SRC if os.path.exists(MANUAL_SRC) else None,
        "manual_entries_count": len(manual_days),
        "total_late_after_10am": sum(s["late_after_10am"] for s in per_employee_summary.values()),
        "warnings": WARNINGS,
        "employees": per_employee_summary,
        "daily_records": daily_records,
    }

    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

    # The dashboard pages (index.html / employee-details.html) load data.js
    # via <script src="data.js">, NOT attendance_data.json directly (browsers
    # block loading local JSON files with fetch() due to CORS/file:// rules).
    # So we also write the same data out as a JS file that just assigns it
    # to a global variable.
    with open(DATA_JS_OUT, "w", encoding="utf-8") as f:
        f.write("window.ATTENDANCE_DATA = ")
        json.dump(data, f)
        f.write(";")

    print(f"Wrote {OUT}")
    print(f"Wrote {DATA_JS_OUT}")
    print(f"Employees: {len(employees)}  Working days: {len(working_days)}  Holidays: {holidays}")
    if holiday_worked:
        print(f"Punches recorded on a policy holiday (excluded from stats): {len(holiday_worked)}")
    total_late = sum(s["late"] for s in per_employee_summary.values())
    total_absent = sum(s["absent"] for s in per_employee_summary.values())
    total_no_logout = sum(s["no_logout"] for s in per_employee_summary.values())
    print(f"Total late instances: {total_late}  Total absent-days: {total_absent}  Total no-logout: {total_no_logout}")
    if manual_days:
        print(f"Manual (WhatsApp) corrections merged: {len(manual_days)} day(s)")
    elif os.path.exists(MANUAL_SRC):
        print(f"{MANUAL_SRC} found but had no valid rows.")
    else:
        print(f"No {MANUAL_SRC} found — add one to merge WhatsApp-reported times.")
    if joined:
        print(f"Joined mid-period: {', '.join(employees.get(e, e) for e in joined)}")
    if resigned:
        print(f"Resigned: {', '.join(employees.get(e, e) for e in resigned)}")
    if explicit_holidays:
        print(f"Declared holidays from {HOLIDAYS_SRC}: {[d.isoformat() for d in sorted(explicit_holidays)]}")

    print()
    if WARNINGS:
        print(f"⚠ {len(WARNINGS)} row(s) were skipped — see warnings above, and they'll also show on the dashboard.")
    else:
        print("✔ No warnings — every row in every CSV was read cleanly.")
    print(f"✔ {OUT} and data.js are now up to date as of {data['generated_at']}.")


if __name__ == "__main__":
    import sys
    # Allow running this script against a specific month folder, e.g.:
    #   python3 process.py "2026-2027/August-2026"
    # refresh_all.py uses this to batch-process every month folder in one go.
    # If no folder is given, it processes CSVs sitting next to this script
    # (old single-folder behaviour), for backward compatibility.
    if len(sys.argv) > 1:
        target_dir = sys.argv[1]
        if not os.path.isdir(target_dir):
            print(f"ERROR: folder '{target_dir}' does not exist.")
            sys.exit(1)
        os.chdir(target_dir)

    if not os.path.exists(SRC):
        print(f"ERROR: '{SRC}' not found in this folder. Put your punch export next to this script, named exactly '{SRC}', and run again.")
    else:
        main()
