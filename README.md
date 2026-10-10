# TickTick to CalDAV converter

Simple script for converting a backup from TickTick to ICS files containing VTODO format to be imported into CalDAV.

Usage:
```
python(3) ticktick_to_caldav.py <TickTick-backup-DATE.csv PATH>
```

Output:
```
ics_output/
- Inbox.ics
- <FOLDER_NAME#> - <LIST_NAME#>.ics
- Archived - <LIST_NAME#>.ics
- ...
```

