import csv
import re
import os
import sys
import uuid
from datetime import datetime
from collections import defaultdict

OUTPUT_DIR = "ics_output"

def parse_iso_datetime(dt_str):
    if not dt_str:
        return None
    try:
        dt = datetime.strptime(dt_str.strip(), "%Y-%m-%dT%H:%M:%S%z")
        return dt.strftime("%Y%m%dT%H%M%SZ")
    except Exception:
        return None

def parse_reminders(reminder_str):
    """
    Parses multi-line reminder fields into a list of valid RFC 5545 TRIGGER values.
    """
    if not reminder_str:
        return []
    
    triggers = []
    lines = reminder_str.replace("\r", "").split("\n")
    
    for line in lines:
        cleaned = line.strip()
        if not cleaned or cleaned == "FREQ=NONE":
            continue
            
        if cleaned in ["PT0S", "P0D", "P0DT0H0M0S", "-P0DT0H0M0S"]:
            cleaned = "-PT0S"
        elif not cleaned.startswith("-") and not cleaned.startswith("+"):
            cleaned = "-" + cleaned
            
        triggers.append(cleaned)
        
    return triggers

def parse_repeat(repeat_str):
    if not repeat_str or "FREQ=NONE" in repeat_str:
        return None
    return repeat_str.replace("\n", ";").strip()

def map_priority(priority_str):
    try:
        p = int(priority_str)
        if p == 5:
            return 1  # High
        elif p == 3:
            return 5  # Medium
        elif p == 1:
            return 9  # Low
        elif p == 0:
            return 0  # None
        return p
    except (ValueError, TypeError):
        return 0

def sanitize_filename(name):
    clean = re.sub(r'[\\/*?:"<>|]', "_", name).strip()
    return clean if clean else "Default"

def convert_csv_to_ics(csv_file_path, output_dir):
    calendar_entries = defaultdict(list)

    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    if not os.path.exists(csv_file_path):
        print(f"ERROR: File '{csv_file_path}' not found!")
        return

    with open(csv_file_path, mode="r", encoding="utf-8-sig", errors="replace") as f:
        while True:
            pos = f.tell()
            line = f.readline()
            if not line:
                print("ERROR: Could not find CSV header row in file.")
                return
            if "Folder Name" in line or "Title" in line or "Kind" in line:
                f.seek(pos)
                break

        reader = csv.DictReader(f)

        total_rows = 0
        processed_rows = 0

        for idx, raw_row in enumerate(reader):
            total_rows += 1
            
            row = {}
            for k, v in raw_row.items():
                if k is not None:
                    clean_k = k.strip().strip('"').strip("'").lower()
                    row[clean_k] = (v or "").strip()

            title = row.get("title", "").replace("\n", " ").strip()
            content = row.get("content", "").replace("\r\n", "\\n").replace("\n", "\\n").strip()
            
            if not title and not content:
                continue

            kind = row.get("kind", "TEXT").upper()
            task_id = row.get("taskid", "")
            parent_id = row.get("parentid", "")
            
            folder_name = row.get("folder name", "")
            list_name = row.get("list name", "") or "Default"
            tags = [t.strip() for t in row.get("tags", "").split(",") if t.strip()]
            
            # File grouping logic
            if folder_name:
                calendar_key = f"{folder_name} - {list_name}"
            elif list_name.lower() in ["inbox", "default"]:
                calendar_key = list_name
            else:
                calendar_key = f"Archived - {list_name}"

            created_time = parse_iso_datetime(row.get("created time", ""))
            start_date = parse_iso_datetime(row.get("start date", ""))
            due_date = parse_iso_datetime(row.get("due date", ""))
            completed_time = parse_iso_datetime(row.get("completed time", ""))
            
            status = row.get("status", "0")
            priority = map_priority(row.get("priority", "0"))
            reminders = parse_reminders(raw_row.get("Reminder", ""))
            rrule = parse_repeat(row.get("repeat", ""))

            # CATEGORIES strictly contains Tags only
            categories = tags

            comp_type = "VJOURNAL" if kind == "NOTE" else "VTODO"
            
            block = [f"BEGIN:{comp_type}"]
            
            if task_id and task_id != "0":
                uid = f"ticktick-{task_id}@import"
            else:
                uid = f"ticktick-{idx+1}-{uuid.uuid4().hex[:6]}@import"
                
            block.append(f"UID:{uid}")
            
            if parent_id and parent_id != "0":
                block.append(f"RELATED-TO;RELTYPE=PARENT:ticktick-{parent_id}@import")
            
            if created_time:
                block.append(f"DTSTAMP:{created_time}")
                block.append(f"CREATED:{created_time}")
            
            block.append(f"SUMMARY:{title}")
            
            if content:
                block.append(f"DESCRIPTION:{content}")
                
            if categories:
                block.append(f"CATEGORIES:{','.join(categories)}")

            if comp_type == "VTODO":
                if start_date:
                    block.append(f"DTSTART:{start_date}")
                if due_date:
                    block.append(f"DUE:{due_date}")
                    
                if priority > 0:
                    block.append(f"PRIORITY:{priority}")
                
                # Status handling: 2 = COMPLETED, -1 = CANCELLED (abandoned), 0 = NEEDS-ACTION
                if status == "2":
                    block.append("STATUS:COMPLETED")
                    block.append("PERCENT-COMPLETE:100")
                    if completed_time:
                        block.append(f"COMPLETED:{completed_time}")
                elif status == "-1":
                    block.append("STATUS:CANCELLED")
                else:
                    block.append("STATUS:NEEDS-ACTION")

                if rrule:
                    block.append(f"RRULE:{rrule}")

                for trigger in reminders:
                    block.append("BEGIN:VALARM")
                    block.append("ACTION:DISPLAY")
                    block.append(f"DESCRIPTION:{title}")
                    block.append(f"TRIGGER:{trigger}")
                    block.append("END:VALARM")

            block.append(f"END:{comp_type}")
            calendar_entries[calendar_key].append("\n".join(block))
            processed_rows += 1

    print(f"Processed {processed_rows} tasks from {csv_file_path}.")

    for cal_key, entries in calendar_entries.items():
        file_name = f"{sanitize_filename(cal_key)}.ics"
        file_path = os.path.join(output_dir, file_name)
        
        ics_body = "BEGIN:VCALENDAR\nVERSION:2.0\nPRODID:-//TickTick to CalDAV Converter//EN\n"
        ics_body += "\n".join(entries)
        ics_body += "\nEND:VCALENDAR"

        with open(file_path, "w", encoding="utf-8") as f:
            f.write(ics_body)
            
        print(f"Created: {file_path} ({len(entries)} items)")

if __name__ == "__main__":
    csv_input = sys.argv[1] if len(sys.argv) > 1 else "ticktick_backup.csv"
    convert_csv_to_ics(csv_input, OUTPUT_DIR)