# PM File Analyzer - Roundabout2

Automated PM (Performance Management) file date converter for Nokia and Huawei network equipment.

## 📋 Overview

This tool scans source directories for PM data files, extracts dates from filenames, and converts them by mapping the oldest date to today's date. Files are processed in chronological order with automatic handling of corrupted files.

### Key Features

- **Multi-vendor support** — Nokia (MO4, MO5) and Huawei
- **Automatic date mapping** — Oldest date → today, oldest+1 → today+1, etc.
- **Date limitation** — Skips files with date ≥ today
- **Corrupted file handling** — Automatically moves corrupted files to dedicated directory
- **Progress logging** — Detailed logs with conversion statistics
- **Config-driven** — Easy to configure new vendors and systems

---

## 🏗 Architecture

```
┌─────────────────────────────────────────────────────┐
│              /home/roundabout/source/                │
│                                                      │
│  ┌──────────┐   ┌──────────┐   ┌─────────────┐     │
│  │  HWI     │   │ Nokia    │   │ Nokia       │     │
│  │ (Huawei) │   │ MO4      │   │ MO5         │     │
│  └────┬─────┘   └────┬─────┘   └──────┬──────┘     │
│       └───────────────┼────────────────┘             │
│                       ▼                              │
│            ┌──────────────────┐                       │
│            │  scan_dates.py   │                       │
│            │  - Scan dates    │                       │
│            │  - Convert files │                       │
│            └──────────────────┘                       │
│                       │                              │
│                       ▼                              │
│            ┌──────────────────┐                       │
│            │  /home/roundabout│                       │
│            │  /source/        │                       │
│            │  (converted)     │                       │
│            └──────────────────┘                       │
│                                                      │
│  Corrupted files → /home/roundabout2/corrupted/      │
└─────────────────────────────────────────────────────┘
```

---

## 📦 Installation

### Prerequisites

- **OS:** Linux (RHEL/CentOS/Ubuntu)
- **Python:** 3.8+
- **Disk:** Sufficient space for source files

### Step 1: Clone the Repository

```bash
git clone https://github.com/aabelit/Roundabout2.git /home/roundabout2
cd /home/roundabout2
```

### Step 2: Configure Source Directories

Edit `config.json`:

```json
{
    "vendors": {
        "huawei": {
            "source_dir": "/home/roundabout/source/HWI",
            "file_pattern": "A(\\d{8})\\.(\\d{4}\\+\\d{4})-(\\d{4}\\+\\d{4})_.*\\.xml\\.gz"
        },
        "nokia": {
            "source_dir": "/home/roundabout/source/NSN",
            "file_pattern": "PM(\\d{8})(\\d{4}\\+\\d{4}).*\\.xml\\.gz",
            "systems": {
                "MO4": {
                    "source_dir": "/home/roundabout/source/NSN/MO4"
                },
                "MO5": {
                    "source_dir": "/home/roundabout/source/NSN/MO5"
                }
            }
        }
    }
}
```

### Step 3: Verify Source Files

```bash
# Check source directories exist
ls -la /home/roundabout/source/

# Count files
find /home/roundabout/source -name "*.gz" | wc -l
```

---

## ⚙️ Configuration

### config.json Structure

| Field | Type | Description |
|-------|------|-------------|
| `vendors` | object | Vendor configurations |
| `vendors.{name}` | object | Individual vendor config |
| `vendors.{name}.source_dir` | string | Source directory path |
| `vendors.{name}.file_pattern` | string | Regex pattern to extract dates |
| `vendors.{name}.systems` | object | Nested systems (optional) |
| `vendors.{name}.systems.{sys}` | object | System configuration |
| `vendors.{name}.systems.{sys}.source_dir` | string | System source directory |

### File Pattern

The `file_pattern` must have the date as the **first capture group** `(\d{8})`.

**Huawei example:**
```
Pattern: A(\d{8})\.(\d{4}\+\d{4})-(\d{4}\+\d{4})_.*\.xml\.gz
File:    A20260731.1000+0300-1015+0300_NODE.xml.gz
Date:    20260731
```

**Nokia example:**
```
Pattern: PM(\d{8})(\d{4}\+\d{4}).*\.xml\.gz
File:    PM202607311004+030048LNBTS_-_410.xml.gz
Date:    20260731
```

---

## 🚀 Usage

### Run Conversion

```bash
cd /home/roundabout2
python3 scan_dates.py
```

### Run in Background

```bash
nohup python3 scan_dates.py > /dev/null 2>&1 &
```

### Check Progress

```bash
# View log file
tail -f /home/roundabout2/logs/conversion.log

# View last 50 lines
tail -50 /home/roundabout2/logs/conversion.log
```

### Stop Conversion

```bash
pkill -9 -f scan_dates.py
```

---

## 📊 Output

### Console Output

```
start_date=2026-07-31
end_date=2026-08-03

Global oldest date: 2026-07-31
Today's date: 2026-09-15
Date range: 4 days

  2026-07-31 -> 2026-09-15 (offset: +0 days)
  2026-08-01 -> 2026-09-16 (offset: +1 days)
  2026-08-02 -> 2026-09-17 (offset: +2 days)
  2026-08-03 -> 2026-09-18 (offset: +3 days)
```

### Log File

Location: `/home/roundabout2/logs/conversion.log`

Contains:
- Date scanning results
- Date mapping
- Conversion progress
- Corrupted file warnings
- Final statistics

### Corrupted Files

Location: `/home/roundabout2/corrupted/{system_name}/`

Structure:
```
/home/roundabout2/corrupted/
├── nokia/
│   ├── MO4/
│   │   ├── PM202608010501+030048LNBTS_-_1715.xml.gz
│   │   └── ...
│   └── MO5/
│       └── ...
└── HWI/
    └── ...
```

---

## 🔄 Processing Flow

### 1. Date Scanning
- Scan all source directories
- Extract dates from filenames using configured patterns
- Find global oldest and newest dates

### 2. Date Mapping
- Map oldest date → today
- Map oldest+1 → today+1
- Continue for all dates in range
- Skip files with date ≥ today

### 3. File Conversion
- For each system (MO4, MO5, HWI):
  - Read gzipped XML file
  - Replace dates in filename
  - Replace dates in XML content
  - Write converted file
  - Remove original file
  - Move corrupted files to `/home/roundabout2/corrupted/`

### 4. Statistics
- Total files processed
- Files converted
- Files skipped (corrupted)
- Files with errors

---

## 📁 Directory Structure

```
/home/roundabout2/
├── scan_dates.py           # Main conversion script
├── config.json             # Configuration file
├── README.md               # This file
├── .gitignore              # Git ignore file
├── logs/                   # Log files
│   └── conversion.log
├── corrupted/              # Corrupted files
│   ├── nokia/
│   │   ├── MO4/
│   │   └── MO5/
│   └── HWI/
└── create_config.py        # Config generator (optional)
```

---

## 🔍 Date Conversion Details

### Global Date Mapping

All systems use the **same global date mapping**:

```
Oldest date in source (e.g., 2026-07-31) → Today (e.g., 2026-09-15)
Oldest + 1 day (e.g., 2026-08-01)        → Today + 1 day (e.g., 2026-09-16)
Oldest + 2 days (e.g., 2026-08-02)       → Today + 2 days (e.g., 2026-09-17)
...
```

**Rule:** Files with date ≥ today are **skipped** (not converted).

---

### Nokia (MO4/MO5) Date Conversion

#### Filename Conversion

**Pattern:** `PM{YYYYMMDD}{HHMM+TZ}...xml.gz`

| Component | Before | After | Notes |
|-----------|--------|-------|-------|
| Date | `20260731` | `20260915` | Mapped to today |
| Time | `1004+0300` | `1004+0300` | **Unchanged** |
| Full | `PM202607311004+0300...` | `PM202609151004+0300...` | Date replaced |

**Example:**
```
Before: PM202607311004+030048LNBTS_-_410.xml.gz
After:  PM202609151004+030048LNBTS_-_410.xml.gz
```

#### XML Content Conversion

**Before:**
```xml
<measCollec beginTime="202607311004+0300"/>
<measData>
    <granPeriod duration="PT900S" endTime="202607311019+0300"/>
</measData>
```

**After:**
```xml
<measCollec beginTime="2026-09-15T10:04:00+03:00"/>
<measData>
    <granPeriod duration="PT900S" endTime="2026-09-15T10:19:00+03:00"/>
</measData>
```

**Conversion Rules:**
1. **Filename:** Replace only the date portion (`YYYYMMDD`)
2. **XML `beginTime`/`endTime`:** Convert format from `YYYYMMDDHHMM+TZ` to `YYYY-MM-DDTHH:MM:SS+TZ:00`
3. **Time portion:** Preserved exactly (HH:MM:SS)
4. **Timezone:** Preserved exactly (+03:00)

**Format Transformation:**
```
Input:  202607311004+0300
Output: 2026-09-15T10:04:00+03:00
        ^^^^^^^^  ^^^^^^^  ^^^^^
        date      time     timezone
```

---

### Huawei (HWI) Date Conversion

#### Filename Conversion

**Pattern:** `A{YYYYMMDD}.{HHMM+TZ}-{HHMM+TZ}_...xml.gz`

| Component | Before | After | Notes |
|-----------|--------|-------|-------|
| Date | `20260731` | `20260915` | Mapped to today |
| Time Range | `1000+0300-1015+0300` | `1000+0300-1015+0300` | **Unchanged** |
| Full | `A20260731.1000+0300-1015+0300_...` | `A20260915.1000+0300-1015+0300_...` | Date replaced |

**Example:**
```
Before: A20260731.1000+0300-1015+0300_2912SUVAL41.xml.gz
After:  A20260915.1000+0300-1015+0300_2912SUVAL41.xml.gz
```

#### XML Content Conversion

**Before:**
```xml
<measCollec beginTime="2026-07-31T15:45:00+03:00"/>
</fileHeader>
<measData>
    <managedElement userLabel="2912SUVAL41"/>
    <measInfo measInfoId="1526726659">
        <granPeriod duration="PT900S" endTime="2026-07-31T16:00:00+03:00"/>
    </measInfo>
</measData>
```

**After:**
```xml
<measCollec beginTime="2026-09-15T15:45:00+03:00"/>
</fileHeader>
<measData>
    <managedElement userLabel="2912SUVAL41"/>
    <measInfo measInfoId="1526726659">
        <granPeriod duration="PT900S" endTime="2026-09-15T16:00:00+03:00"/>
    </measInfo>
</measData>
```

**Conversion Rules:**
1. **Filename:** Replace only the date portion (`YYYYMMDD`)
2. **XML `beginTime`/`endTime`:** Replace only the date portion (`YYYY-MM-DD`)
3. **Time portion:** Preserved exactly (`HH:MM:SS`)
4. **Timezone:** Preserved exactly (`+03:00`)

**Format Transformation:**
```
Input:  2026-07-31T15:45:00+03:00
Output: 2026-09-15T15:45:00+03:00
        ^^^^^^^^  ^^^^^^^^^^^^^^^
        date      time+timezone (unchanged)
```

---

### Conversion Summary

| Vendor | Filename Date | XML Date Format | Time Preserved |
|--------|---------------|-----------------|----------------|
| Nokia | `YYYYMMDD` → `YYYYMMDD` | `YYYYMMDDHHMM+TZ` → `YYYY-MM-DDTHH:MM:SS+TZ:00` | ✅ Yes |
| Huawei | `YYYYMMDD` → `YYYYMMDD` | `YYYY-MM-DD` → `YYYY-MM-DD` | ✅ Yes |

**Key Points:**
- ✅ Dates are mapped globally (oldest → today)
- ✅ Times are preserved exactly
- ✅ Timezones are preserved exactly
- ✅ Files with date ≥ today are skipped
- ✅ Corrupted files moved to `/home/roundabout2/corrupted/{system}/`

---

## 🛠 Troubleshooting

### No Files Found

```bash
# Check source directories
ls -la /home/roundabout/source/

# Check file patterns
python3 -c "
import re
pattern = re.compile(r'PM(\d{8})(\d{4}\+\d{4}).*\.xml\.gz')
test = 'PM202607311004+030048LNBTS_-_410.xml.gz'
print(pattern.match(test))
"
```

### Corrupted Files

Corrupted files are automatically moved to `/home/roundabout2/corrupted/`. Check the log for details:

```bash
grep "corrupted" /home/roundabout2/logs/conversion.log
```

### Permission Errors

```bash
# Fix permissions
chmod -R 755 /home/roundabout2/
chown -R root:root /home/roundabout2/
```

---

## 📝 Version History

| Version | Date | Changes |
|---------|------|---------|
| 1.0.0 | 2026-09-15 | Initial release |

---

## 📄 License

This project is proprietary software.

---

## 🤝 Support

For issues or questions, please contact the development team.
