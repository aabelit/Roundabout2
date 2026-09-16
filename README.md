# PM File Analyzer - Roundabout2

Automated PM (Performance Management) file date converter for Nokia and Huawei network equipment.

## 📋 Overview

This tool scans source directories for PM data files, extracts dates from filenames, and converts them using a two-stage process:

- **Stage 1 (Initial Synchronization):** One-time conversion that shifts historical files so the oldest date becomes today
- **Stage 2 (Periodic Processing):** Runs every 15 minutes, copying past files to destination and processing originals with date+4

### Key Features

- **Multi-vendor support** — Nokia (MO4, MO5) and Huawei (HWI)
- **Two-stage processing** — Stage 1 (one-time) + Stage 2 (periodic)
- **Automatic date mapping** — Oldest date → today, oldest+1 → today+1, etc.
- **Corrupted file handling** — Automatically moves corrupted files to dedicated directory
- **Progress logging** — Detailed logs with conversion statistics
- **Config-driven** — Easy to configure vendors, systems, and Stage 2 parameters

---

## 🏗 Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                   /home/roundabout/source/                           │
│                                                                      │
│  ┌──────────┐   ┌──────────┐   ┌─────────────┐                     │
│  │  HWI     │   │ Nokia    │   │ Nokia       │                     │
│  │ (Huawei) │   │ MO4      │   │ MO5         │                     │
│  └────┬─────┘   └────┬─────┘   └──────┬──────┘                     │
│       └───────────────┼────────────────┘                             │
│                       ▼                                              │
│            ┌──────────────────┐                                      │
│            │   scan_dates.py  │                                      │
│            │                  │                                      │
│            │  Stage 1:        │  One-time initial sync               │
│            │  Stage 2:        │  Periodic (every 15 min)             │
│            └──────────────────┘                                      │
│                       │                                              │
│          ┌────────────┴────────────┐                                │
│          ▼                         ▼                                │
│  ┌──────────────────┐      ┌──────────────────┐                    │
│  │ /home/roundabout │      │ /home/roundabout │                    │
│  │ /source/         │      │ /dest/           │                    │
│  │ (converted)      │      │ (copied past)    │                    │
│  └──────────────────┘      └──────────────────┘                    │
│                                                                      │
│  Corrupted files → /home/roundabout2/corrupted/                     │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 📦 Installation

### Prerequisites

- **OS:** Linux (RHEL/CentOS/Ubuntu)
- **Python:** 3.8+
- **Disk:** Sufficient space for source and destination files
- **Recommended:** SSD storage for optimal performance

### Step 1: Clone the Repository

```bash
git clone https://github.com/aabelit/Roundabout2.git /home/roundabout2
cd /home/roundabout2
```

### Step 2: Configure Source Directories and Stage 2

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
    },
    "stage2": {
        "interval_minutes": 15,
        "dest_base_dir": "/home/roundabout/dest",
        "date_offset_days": 4
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
| `stage2` | object | Stage 2 configuration |
| `stage2.interval_minutes` | int | How often Stage 2 runs (default: 15) |
| `stage2.dest_base_dir` | string | Base directory for copied files |
| `stage2.date_offset_days` | int | Days to add to current date (default: 4) |

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

## 🔄 Two-Stage Processing

### Stage 1: Initial Synchronization

**Runs once at startup.**

**Purpose:** Shift all historical files so the oldest date becomes today's date.

**Behavior:**
1. Scans all source directories for `.gz` files
2. Extracts dates from filenames using configured patterns
3. Finds the **global oldest date** across ALL systems
4. Maps: oldest → today, oldest+1 → today+1, oldest+2 → today+2, etc.
5. Processes only files with dates **before today** (skips today and future)
6. Converts files in-place (replaces original with converted version)
7. Moves corrupted files to `/home/roundabout2/corrupted/{system}/`
8. Prints **"Initial synchronisation done"** when complete

**Date Mapping Example:**
```
Global oldest: 2026-07-31 (Huawei)
Today:         2026-09-16

Mapping:
  2026-07-31 → 2026-09-16 (offset: +0 days)
  2026-08-01 → 2026-09-17 (offset: +1 days)
  2026-08-02 → 2026-09-18 (offset: +2 days)
  2026-08-03 → 2026-09-19 (offset: +3 days)

Skipped: Files with date ≥ 2026-09-16 (already today or later)
```

**Output:**
```
STAGE 1: Initial Synchronization
============================================================
  huawei: 1735864 files, oldest=2026-07-31, newest=2026-08-03
  nokia/MO4: 425552 files, oldest=2026-09-16, newest=2026-12-19
  nokia/MO5: 420673 files, oldest=2026-09-16, newest=2026-11-01

start_date=2026-07-31
end_date=2026-08-03

Date range to process: 2026-07-31 to 2026-08-03
Today: 2026-09-16
Files in range: 4 unique dates

  2026-07-31 -> 2026-09-16 (offset: +0 days)
  2026-08-01 -> 2026-09-17 (offset: +1 days)
  2026-08-02 -> 2026-09-18 (offset: +2 days)
  2026-08-03 -> 2026-09-19 (offset: +3 days)

Starting MO4 conversion...
  Found 0 files to process  (all dates >= today, skipped)
...
Initial synchronisation done
```

---

### Stage 2: Periodic Processing

**Runs every N minutes (configurable).**

**Purpose:** Copy past files to destination and process originals with date+4.

**Behavior:**
1. Checks full datetime (date + time) from filename against current time
2. For files where datetime is **already in the past**:
   - **Copies** file to destination directory (unchanged)
   - **Modifies** original in source (changes date to current date + N days)
3. Destinations are separate per system (`dest/hwi/`, `dest/mo4/`, `dest/mo5/`)
4. Runs in a loop until stopped

**Example (current time: 2026-09-16 14:00, offset: 4 days):**
```
File: A20260915.1000+0300-1015+0300_NODE.xml.gz
Datetime in filename: 2026-09-15 10:00 (in the past)

Actions:
  1. Copy to: /home/roundabout/dest/hwi/A20260915.1000+0300-1015+0300_NODE.xml.gz
  2. Modify original:
     Filename: A20260919.1000+0300-1015+0300_NODE.xml.gz  (date → 2026-09-19)
     XML: beginTime="2026-09-19T10:00:00+03:00"
```

---

## 📊 Output

### Console Output (Stage 1)

```
STAGE 1: Initial Synchronization
============================================================
  huawei: 1735864 files, oldest=2026-07-31, newest=2026-08-03
  nokia/MO4: 425552 files, oldest=2026-09-16, newest=2026-12-19
  nokia/MO5: 420673 files, oldest=2026-09-16, newest=2026-11-01

start_date=2026-07-31
end_date=2026-08-03

Date range to process: 2026-07-31 to 2026-08-03
Today: 2026-09-16
Files in range: 4 unique dates
============================================================

  2026-07-31 -> 2026-09-16 (offset: +0 days)
  2026-08-01 -> 2026-09-17 (offset: +1 days)
  2026-08-02 -> 2026-09-18 (offset: +2 days)
  2026-08-03 -> 2026-09-19 (offset: +3 days)

Starting MO4 conversion...
  Found 0 files to process
  MO4 CONVERSION COMPLETE
  Total: 0, Converted: 0, Skipped: 0, Errors: 0

Starting MO5 conversion...
  Found 0 files to process
  MO5 CONVERSION COMPLETE
  Total: 0, Converted: 0, Skipped: 0, Errors: 0

Starting HWI conversion...
  Found 1730090 files to process
  HWI Progress: 1000/1730090
  HWI Progress: 2000/1730090
  ...
  HWI CONVERSION COMPLETE
  Total: 1730090, Converted: 1725000, Skipped: 5000, Errors: 90

============================================================
ALL STAGE 1 CONVERSIONS COMPLETE
============================================================
Initial synchronisation done

Stage 2 will run every 15 minutes
Press Ctrl+C to stop

STAGE 2 RUN - 2026-09-16 14:15:00
============================================================
Processing hwu/HWI...
  Source: /home/roundabout/source/HWI
  Dest: /home/roundabout/dest/hwi
  Target date: 2026-09-20
  Found 500 files to process
  HWI Progress: 100/500
  ...
  HWI Complete: 498 processed, 2 errors, 0 corrupted
...
STAGE 2 RUN COMPLETE - 1500 files processed, 6 errors
============================================================
```

### Log File

**Location:** `/home/roundabout2/logs/conversion.log`

**Contains:**
- Date scanning results
- Date mapping
- Conversion progress
- Corrupted file warnings
- Final statistics
- Stage 2 run logs

### Corrupted Files

**Location:** `/home/roundabout2/corrupted/{system_name}/`

**Structure:**
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

/home/roundabout/dest/      # Stage 2 destination (created automatically)
├── hwi/                    # Huawei copied files
├── mo4/                    # Nokia MO4 copied files
└── mo5/                    # Nokia MO5 copied files
```

---

## 🔍 Date Conversion Details

### Global Date Mapping (Stage 1)

All systems use the **same global date mapping**:

```
Oldest date in source (e.g., 2026-07-31) → Today (e.g., 2026-09-16)
Oldest + 1 day (e.g., 2026-08-01)        → Today + 1 day (e.g., 2026-09-17)
Oldest + 2 days (e.g., 2026-08-02)       → Today + 2 days (e.g., 2026-09-18)
...
```

**Rule:** Files with date ≥ today are **skipped** (not converted).

---

### Nokia (MO4/MO5) Date Conversion

#### Filename Conversion

**Pattern:** `PM{YYYYMMDD}{HHMM+TZ}...xml.gz`

| Component | Before | After | Notes |
|-----------|--------|-------|-------|
| Date | `20260731` | `20260916` | Mapped to today |
| Time | `1004+0300` | `1004+0300` | **Unchanged** |
| Full | `PM202607311004+0300...` | `PM202609161004+0300...` | Date replaced |

**Example:**
```
Before: PM202607311004+030048LNBTS_-_410.xml.gz
After:  PM202609161004+030048LNBTS_-_410.xml.gz
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
<measCollec beginTime="2026-09-16T10:04:00+03:00"/>
<measData>
    <granPeriod duration="PT900S" endTime="2026-09-16T10:19:00+03:00"/>
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
Output: 2026-09-16T10:04:00+03:00
        ^^^^^^^^  ^^^^^^^  ^^^^^
        date      time     timezone
```

---

### Huawei (HWI) Date Conversion

#### Filename Conversion

**Pattern:** `A{YYYYMMDD}.{HHMM+TZ}-{HHMM+TZ}_...xml.gz`

| Component | Before | After | Notes |
|-----------|--------|-------|-------|
| Date | `20260731` | `20260916` | Mapped to today |
| Time Range | `1000+0300-1015+0300` | `1000+0300-1015+0300` | **Unchanged** |
| Full | `A20260731.1000+0300-1015+0300_...` | `A20260916.1000+0300-1015+0300_...` | Date replaced |

**Example:**
```
Before: A20260731.1000+0300-1015+0300_2912SUVAL41.xml.gz
After:  A20260916.1000+0300-1015+0300_2912SUVAL41.xml.gz
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
<measCollec beginTime="2026-09-16T15:45:00+03:00"/>
</fileHeader>
<measData>
    <managedElement userLabel="2912SUVAL41"/>
    <measInfo measInfoId="1526726659">
        <granPeriod duration="PT900S" endTime="2026-09-16T16:00:00+03:00"/>
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
Output: 2026-09-16T15:45:00+03:00
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
- ✅ Files with date ≥ today are skipped (Stage 1)
- ✅ Full datetime checked against current time (Stage 2)
- ✅ Corrupted files moved to `/home/roundabout2/corrupted/{system}/`

---

## 📋 Function Reference

### `setup_logging()`
Sets up file and console logging.
- Creates log directory if needed
- Configures file handler (`/home/roundabout2/logs/conversion.log`)
- Configures console handler
- Returns logger instance

### `load_config()`
Loads configuration from `config.json`.
- Returns parsed JSON as dictionary

### `extract_date_from_filename(filename, pattern)`
Extracts date string from filename using regex pattern.
- **Parameters:**
  - `filename` (str): Filename to parse
  - `pattern` (CompiledRegex): Compiled regex pattern
- **Returns:** Date string (YYYYMMDD) or None

### `scan_source_files(config, logger)`
Scans all source directories and extracts dates from filenames.
- **Parameters:**
  - `config` (dict): Configuration dictionary
  - `logger` (Logger): Logger instance
- **Returns:** Tuple of (vendor_dates, all_dates)
  - `vendor_dates`: Dict of {system_key: {dates, file_count, oldest_date, newest_date}}
  - `all_dates`: List of all dates found across all systems

### `stage1_conversion(config, logger)`
**Stage 1:** One-time initial synchronization.
- Scans all source directories
- Finds global oldest date
- Maps oldest → today, oldest+1 → today+1, etc.
- Processes only files with dates before today
- Converts files in-place
- Moves corrupted files to `/home/roundabout2/corrupted/`
- Prints "Initial synchronisation done" when complete

### `convert_mo_files(config, logger, system_key, today, date_range_end, corrupted_dir, max_workers)`
Converts Nokia MO files (MO4/MO5).
- **Parameters:**
  - `config` (dict): Configuration dictionary
  - `logger` (Logger): Logger instance
  - `system_key` (str): System key (e.g., "nokia/MO4")
  - `today` (date): Today's date
  - `date_range_end` (date): End of date range to process
  - `corrupted_dir` (str): Directory for corrupted files
  - `max_workers` (int): Number of parallel workers (default: 4)
- Uses ThreadPoolExecutor for parallel processing
- Handles corrupted files automatically

### `convert_hwi_files(config, logger, today, date_range_end, corrupted_dir, max_workers)`
Converts Huawei HWI files.
- **Parameters:** Same as `convert_mo_files`
- Uses ThreadPoolExecutor for parallel processing
- Handles corrupted files automatically

### `stage2_run(config, logger)`
**Stage 2:** Periodic processing.
- Checks full datetime (date + time) from filename
- Copies past files to destination directory
- Modifies originals with date+4
- **Parameters:**
  - `config` (dict): Configuration dictionary (must include `stage2` section)
  - `logger` (Logger): Logger instance
- Destinations: `{dest_base_dir}/{system}/` (e.g., `/home/roundabout/dest/hwi/`)

### `main()`
Main entry point.
1. Sets up logging
2. Loads configuration
3. Runs Stage 1 (one-time)
4. Enters Stage 2 loop (every N minutes)
5. Ctrl+C to stop

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

### Performance Issues

The script processes ~2500-3000 files/min on HDD. For faster processing:
- **Move source files to SSD** (10-30x speedup)
- **Increase workers** (not recommended, diminishing returns)
- **Use zstd compression** (requires format change)

---

## 📝 Version History

| Version | Date | Changes |
|---------|------|---------|
| 1.0.0 | 2026-09-15 | Initial release |
| 2.0.0 | 2026-09-16 | Added Stage 1 (initial sync) and Stage 2 (periodic processing) |

---

## 📄 License

This project is proprietary software.

---

## 🤝 Support

For issues or questions, please contact the development team.
