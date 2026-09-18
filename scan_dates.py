#!/usr/bin/env python3
"""
Stage 1: One-time initial synchronization - shifts historical files so oldest = today
Stage 2: Periodic processing - copies past files to dest, processes originals with date+4
"""

import os, re, json, gzip, logging, logging.handlers, shutil, time, datetime
from pathlib import Path
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed
from functools import partial
from threading import Lock

CONFIG_PATH = "/home/roundabout2/config.json"
LOG_DIR = "/home/roundabout2/logs"
LOG_FILE = os.path.join(LOG_DIR, "conversion.log")
CORRUPTED_BASE_DIR = "/home/roundabout2/corrupted"


def setup_logging():
    os.makedirs(LOG_DIR, exist_ok=True)
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)
    logger.handlers = []
    # Log rotation: max 10MB, keep 5 backup files
    fh = logging.handlers.RotatingFileHandler(
        LOG_FILE, maxBytes=10*1024*1024, backupCount=5, mode='w'
    )
    fh.setLevel(logging.INFO)
    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO)
    fmt = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    fh.setFormatter(fmt)
    ch.setFormatter(fmt)
    logger.addHandler(fh)
    logger.addHandler(ch)
    return logger


def load_config():
    with open(CONFIG_PATH, "r") as f:
        return json.load(f)


def extract_date_from_filename(filename, pattern):
    match = pattern.match(filename)
    return match.group(1) if match else None


def extract_datetime_from_filename(filename, vendor, pattern):
    """Extract full datetime (date + time) from filename for Stage 2."""
    match = pattern.match(filename)
    if not match:
        return None
    date_str = match.group(1)  # YYYYMMDD
    time_str = match.group(2)  # HHMM+TZMM or HHMM-TZMM
    try:
        date_obj = datetime.strptime(date_str, "%Y%m%d").date()
        # Extract time part (first 4 chars: HHMM)
        time_part = time_str[:4]
        hour = int(time_part[:2])
        minute = int(time_part[2:])
        return datetime(date_obj.year, date_obj.month, date_obj.day, hour, minute)
    except (ValueError, IndexError):
        return None


def scan_source_files(config, logger):
    vendor_dates, all_dates = {}, []
    for vn, vc in config.get("vendors", {}).items():
        fp = re.compile(vc["file_pattern"])
        sys_v = vc.get("systems")
        if sys_v:
            for sn, sc in sys_v.items():
                sd = sc["source_dir"]
                sk = f"{vn}/{sn}"
                if not os.path.exists(sd):
                    logger.warning(f"Source dir not found: {sd}")
                    continue
                dates, fc = [], 0
                for root, dirs, files in os.walk(sd):
                    for fn in files:
                        if fn.endswith(".gz"):
                            fc += 1
                            ds = extract_date_from_filename(fn, fp)
                            if ds:
                                try:
                                    dates.append(datetime.strptime(ds, "%Y%m%d").date())
                                except ValueError:
                                    pass
                vendor_dates[sk] = {
                    "dates": dates, "file_count": fc,
                    "oldest_date": min(dates) if dates else None,
                    "newest_date": max(dates) if dates else None
                }
                if dates:
                    all_dates.extend(dates)
                    logger.info(f"  {sk}: {fc} files, oldest={min(dates)}, newest={max(dates)}")
                else:
                    logger.info(f"  {sk}: {fc} files, no dates found")
        else:
            sd = vc["source_dir"]
            sk = vn
            if not os.path.exists(sd):
                logger.warning(f"Source dir not found: {sd}")
                continue
            dates, fc = [], 0
            for root, dirs, files in os.walk(sd):
                for fn in files:
                    if fn.endswith(".gz"):
                        fc += 1
                        ds = extract_date_from_filename(fn, fp)
                        if ds:
                            try:
                                dates.append(datetime.strptime(ds, "%Y%m%d").date())
                            except ValueError:
                                pass
            vendor_dates[sk] = {
                "dates": dates, "file_count": fc,
                "oldest_date": min(dates) if dates else None,
                "newest_date": max(dates) if dates else None
            }
            if dates:
                all_dates.extend(dates)
                logger.info(f"  {sk}: {fc} files, oldest={min(dates)}, newest={max(dates)}")
    return vendor_dates, all_dates


def _atomic_gzip_write(dest_path, content):
    tmp_path = dest_path + '.tmp'
    with gzip.open(tmp_path, 'wb', compresslevel=1) as f_out:
        f_out.write(content)
    os.replace(tmp_path, dest_path)


def _replace_mo_time(match, date_str, target_date_str):
    p, od = match.group(1), match.group(2)
    ot, tz, q = match.group(3), match.group(4), match.group(5)
    tp = ot[:2] + ":" + ot[2:] + ":00" + tz[:3] + ":" + tz[3:]
    return f'{p}{target_date_str}-{tp}{q}'


def _replace_hwi_time(match, date_str, target_date_str):
    p, od = match.group(1), match.group(2)
    ot, q = match.group(3), match.group(4)
    # Format target date with dashes: 20260922 -> 2026-09-22
    formatted_date = f'{target_date_str[:4]}-{target_date_str[4:6]}-{target_date_str[6:8]}'
    # Replace ALL dates in XML with target date
    return f'{p}{formatted_date}{ot}{q}'


def _process_mo_file(sp, nf, ds, tds, tp, cd):
    fn = os.path.basename(sp)
    try:
        with gzip.open(sp, 'rb') as f:
            content = f.read()
        try:
            tc = content.decode('utf-8')
        except UnicodeDecodeError:
            tc = content.decode('latin-1')
        nc = tp.sub(partial(_replace_mo_time, date_str=ds, target_date_str=tds), tc)
        dp = os.path.join(os.path.dirname(sp), nf)
        tmp_path = dp + '.tmp'
        with gzip.open(tmp_path, 'wb', compresslevel=1) as f_out:
            f_out.write(nc.encode('utf-8'))
        os.replace(tmp_path, dp)
        os.remove(sp)
        return (True, fn, 'converted')
    except Exception as e:
        em = str(e)
        if 'Compressed file ended' in em or 'corrupted' in em.lower():
            os.makedirs(cd, exist_ok=True)
            cp = os.path.join(cd, fn)
            try:
                shutil.move(sp, cp)
                return (False, fn, 'corrupted')
            except Exception as me:
                return (False, fn, f'move_failed: {me}')
        return (False, fn, f'error: {e}')


def _process_hwi_file(sp, nf, ds, tds, tp, cd):
    fn = os.path.basename(sp)
    try:
        with gzip.open(sp, 'rb') as f:
            content = f.read()
        try:
            tc = content.decode('utf-8')
        except UnicodeDecodeError:
            tc = content.decode('latin-1')
        nc = tp.sub(partial(_replace_hwi_time, date_str=ds, target_date_str=tds), tc)
        dp = os.path.join(os.path.dirname(sp), nf)
        tmp_path = dp + '.tmp'
        with gzip.open(tmp_path, 'wb', compresslevel=1) as f_out:
            f_out.write(nc.encode('utf-8'))
        os.replace(tmp_path, dp)
        os.remove(sp)
        return (True, fn, 'converted')
    except Exception as e:
        em = str(e)
        if 'Compressed file ended' in em or 'corrupted' in em.lower():
            os.makedirs(cd, exist_ok=True)
            cp = os.path.join(cd, fn)
            try:
                shutil.move(sp, cp)
                return (False, fn, 'corrupted')
            except Exception as me:
                return (False, fn, f'move_failed: {me}')
        return (False, fn, f'error: {e}')


def convert_mo_files(config, logger, system_key, today, date_range_end,
                     corrupted_dir, max_workers=4):
    vn, sn = system_key.split("/")
    nc = config["vendors"]["nokia"]
    mc = nc["systems"][sn]
    sd = mc["source_dir"]
    fp = re.compile(nc["file_pattern"])
    if not os.path.exists(sd):
        logger.error(f"{system_key} source directory not found: {sd}")
        return
    dm = config.get("global_date_map", {})
    logger.info("=" * 60)
    logger.info(f"CONVERTING {system_key}")
    logger.info("=" * 60)

    files_to_process = []
    for root, dirs, files in os.walk(sd):
        for fn in files:
            if not fn.endswith(".gz"):
                continue
            ds = extract_date_from_filename(fn, fp)
            if not ds:
                continue
            try:
                src_date = datetime.strptime(ds, "%Y%m%d").date()
            except ValueError:
                continue
            if src_date not in dm:
                continue
            if src_date > date_range_end:
                continue
            td = dm[src_date]
            tds = td.strftime("%Y%m%d")
            nf = fn.replace(ds, tds, 1)
            sp = os.path.join(root, fn)
            files_to_process.append((
                sp, nf, ds, tds,
                re.compile(r"((?:begin|end)Time\s*=\s*[\"'])(\d{8})(\d{4})(\+\d{4})([\"'])"),
                corrupted_dir
            ))

    logger.info(f"  Found {len(files_to_process)} files to process")
    stats = {"total": 0, "converted": 0, "errors": 0, "skipped": 0}
    stats_lock = Lock()

    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        futs = {ex.submit(_process_mo_file, *a): a for a in files_to_process}
        completed = 0
        for fut in as_completed(futs):
            ok, fn, st = fut.result()
            with stats_lock:
                stats["total"] += 1
                if ok:
                    stats["converted"] += 1
                elif st == 'corrupted':
                    stats["skipped"] += 1
                    logger.warning(f"  Moved corrupted: {fn}")
                else:
                    stats["errors"] += 1
                    logger.error(f"  Error: {fn} -> {st}")
            completed += 1
            if completed % 1000 == 0:
                logger.info(f"  {system_key} Progress: {completed}/{stats['total']}")

    logger.info("=" * 60)
    logger.info(f"{system_key} CONVERSION COMPLETE")
    logger.info(f"  Total: {stats['total']}, Converted: {stats['converted']}, "
                f"Skipped: {stats['skipped']}, Errors: {stats['errors']}")
    logger.info("=" * 60)


def convert_hwi_files(config, logger, today, date_range_end, corrupted_dir,
                      max_workers=4):
    hc = config["vendors"]["huawei"]
    sd = hc["source_dir"]
    fp = re.compile(hc["file_pattern"])
    if not os.path.exists(sd):
        logger.error(f"HWI source directory not found: {sd}")
        return
    dm = config.get("global_date_map", {})
    logger.info("=" * 60)
    logger.info("CONVERTING HWI")
    logger.info("=" * 60)

    files_to_process = []
    for root, dirs, files in os.walk(sd):
        for fn in files:
            if not fn.endswith(".gz"):
                continue
            ds = extract_date_from_filename(fn, fp)
            if not ds:
                continue
            try:
                src_date = datetime.strptime(ds, "%Y%m%d").date()
            except ValueError:
                continue
            if src_date not in dm:
                continue
            if src_date > date_range_end:
                continue
            td = dm[src_date]
            tds = td.strftime("%Y%m%d")
            nf = fn.replace(ds, tds, 1)
            sp = os.path.join(root, fn)
            files_to_process.append((
                sp, nf, ds, tds,
                re.compile(r"((?:begin|end)Time\s*=\s*[\"'])(\d{4}-\d{2}-\d{2})(T\d{2}:\d{2}:\d{2}\+\d{2}:\d{2})([\"'])"),
                corrupted_dir
            ))

    logger.info(f"  Found {len(files_to_process)} files to process")
    stats = {"total": 0, "converted": 0, "errors": 0, "skipped": 0}
    stats_lock = Lock()

    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        futs = {ex.submit(_process_hwi_file, *a): a for a in files_to_process}
        completed = 0
        for fut in as_completed(futs):
            ok, fn, st = fut.result()
            with stats_lock:
                stats["total"] += 1
                if ok:
                    stats["converted"] += 1
                elif st == 'corrupted':
                    stats["skipped"] += 1
                    logger.warning(f"  Moved corrupted: {fn}")
                else:
                    stats["errors"] += 1
                    logger.error(f"  Error: {fn} -> {st}")
            completed += 1
            if completed % 1000 == 0:
                logger.info(f"  HWI Progress: {completed}/{stats['total']}")

    logger.info("=" * 60)
    logger.info("HWI CONVERSION COMPLETE")
    logger.info(f"  Total: {stats['total']}, Converted: {stats['converted']}, "
                f"Skipped: {stats['skipped']}, Errors: {stats['errors']}")
    logger.info("=" * 60)


def stage1_conversion(config, logger):
    """Stage 1: One-time initial synchronization.
    Processes files with dates before today.
    Oldest date across ALL systems -> today, then +1, +2, etc.
    """
    logger.info("=" * 60)
    logger.info("STAGE 1: Initial Synchronization")
    logger.info("=" * 60)

    vendor_dates, all_dates = scan_source_files(config, logger)

    if not all_dates:
        logger.info("No dates found - nothing to process")
        logger.info("Initial synchronisation done")
        return

    oldest = min(all_dates).strftime('%Y-%m-%d')
    newest = max(all_dates).strftime('%Y-%m-%d')
    logger.info(f"\nstart_date={oldest}")
    logger.info(f"end_date={newest}")

    today = datetime.now().date()
    # Only process files with dates before today
    fd = [d for d in all_dates if d < today]

    if not fd:
        logger.info(f"No files found before today ({today})")
        logger.info("Initial synchronisation done")
        return

    dm = {}
    drs = min(fd)
    dre = max(fd)
    logger.info(f"\nDate range to process: {drs} to {dre}")
    logger.info(f"Today: {today}")
    logger.info(f"Files in range: {len(set(fd))} unique dates")
    logger.info("=" * 60)

    for sd2 in sorted(set(fd)):
        offset = (sd2 - drs).days
        td = today + timedelta(days=offset)
        dm[sd2] = td
        logger.info(f"  {sd2} -> {td} (offset: +{offset} days)")

    config["global_oldest_date"] = drs
    config["global_today"] = today
    config["global_date_map"] = dm

    cd = CORRUPTED_BASE_DIR
    logger.info("\nStarting MO4 conversion...")
    convert_mo_files(config, logger, "nokia/MO4", today, dre, cd)

    logger.info("\nStarting MO5 conversion...")
    convert_mo_files(config, logger, "nokia/MO5", today, dre, cd)

    logger.info("\nStarting HWI conversion...")
    convert_hwi_files(config, logger, today, dre, cd)

    logger.info("\n" + "=" * 60)
    logger.info("ALL STAGE 1 CONVERSIONS COMPLETE")
    logger.info("=" * 60)
    logger.info("Initial synchronisation done")


def _stage2_process_mo_file(sp, nf, tds, tp, dest_dir):
    """Process a single MO file for Stage 2: copy to dest, modify original."""
    fn = os.path.basename(sp)
    try:
        with gzip.open(sp, 'rb') as f:
            content = f.read()
        try:
            tc = content.decode('utf-8')
        except UnicodeDecodeError:
            tc = content.decode('latin-1')

        # Copy to dest (unchanged) — use ORIGINAL filename
        dest_path = os.path.join(dest_dir, fn)
        os.makedirs(os.path.dirname(dest_path), exist_ok=True)
        with gzip.open(dest_path + '.tmp', 'wb', compresslevel=1) as f_out:
            f_out.write(content)
        os.replace(dest_path + '.tmp', dest_path)

        # Modify original in source (change date to current date + 4)
        nc = tp.sub(partial(_replace_mo_time, date_str=tds[:-8], target_date_str=tds), tc)
        tmp_path = sp + '.tmp'
        with gzip.open(tmp_path, 'wb', compresslevel=1) as f_out:
            f_out.write(nc.encode('utf-8'))
        os.replace(tmp_path, sp)

        # Rename file to new date
        new_path = sp.replace(fn, nf, 1)
        os.rename(sp, new_path)

        return (True, fn, 'processed')
    except Exception as e:
        em = str(e)
        if 'Compressed file ended' in em or 'corrupted' in em.lower():
            return (False, fn, 'corrupted')
        return (False, fn, f'error: {e}')


def _stage2_process_hwi_file(sp, nf, tds, tp, dest_dir):
    """Process a single HWI file for Stage 2: copy to dest, modify original."""
    fn = os.path.basename(sp)
    try:
        with gzip.open(sp, 'rb') as f:
            content = f.read()
        try:
            tc = content.decode('utf-8')
        except UnicodeDecodeError:
            tc = content.decode('latin-1')

        # Copy to dest (unchanged) — use ORIGINAL filename
        dest_path = os.path.join(dest_dir, fn)
        os.makedirs(os.path.dirname(dest_path), exist_ok=True)
        with gzip.open(dest_path + '.tmp', 'wb', compresslevel=1) as f_out:
            f_out.write(content)
        os.replace(dest_path + '.tmp', dest_path)

        # Extract original date from filename (first 8 chars after A)
        original_date = fn[1:9]
        # Modify original in source (change date to current date + 4)
        nc = tp.sub(partial(_replace_hwi_time, date_str=original_date, target_date_str=tds), tc)
        tmp_path = sp + '.tmp'
        with gzip.open(tmp_path, 'wb', compresslevel=1) as f_out:
            f_out.write(nc.encode('utf-8'))
        os.replace(tmp_path, sp)

        # Rename file to new date
        new_path = sp.replace(fn, nf, 1)
        os.rename(sp, new_path)

        return (True, fn, 'processed')
    except Exception as e:
        em = str(e)
        if 'Compressed file ended' in em or 'corrupted' in em.lower():
            return (False, fn, 'corrupted')
        return (False, fn, f'error: {e}')


def _cleanup_dest_dir(dest_dir, pattern, keep_hours, logger):
    """Clean up destination directory - keep only files from last N hours.
    Files are identified by date in filename.
    """
    cutoff = datetime.now() - timedelta(hours=keep_hours)
    to_delete = []

    if not os.path.exists(dest_dir):
        return 0

    for fn in os.listdir(dest_dir):
        if not fn.endswith(".gz"):
            continue
        dt = extract_datetime_from_filename(fn, "unknown", pattern)
        if dt is None:
            continue
        if dt < cutoff:
            to_delete.append(os.path.join(dest_dir, fn))

    deleted = 0
    for fpath in to_delete:
        try:
            os.remove(fpath)
            deleted += 1
        except Exception:
            pass

    return deleted


def stage2_run(config, logger):
    """Stage 2: Periodic processing.
    Copies past files to dest, processes originals with date+4.
    Cleans up old files from dest directory.
    """
    stage2_cfg = config.get("stage2", {})
    dest_base = stage2_cfg.get("dest_base_dir", "/home/roundabout/dest")
    date_offset = stage2_cfg.get("date_offset_days", 4)
    keep_hours = stage2_cfg.get("time_to_cleanup", 2)  # Hours to keep files

    logger.info("=" * 60)
    logger.info(f"STAGE 2 RUN - {datetime.now()}")
    logger.info("=" * 60)
    system_start_times = {}
    stage2_oldest_date = None
    stage2_newest_date = None

    today = datetime.now()
    target_date = (today + timedelta(days=date_offset)).strftime("%Y%m%d")
    target_date_iso = (today + timedelta(days=date_offset)).strftime("%Y-%m-%d")

    systems = []
    for vn, vc in config.get("vendors", {}).items():
        sys_v = vc.get("systems")
        if sys_v:
            for sn, sc in sys_v.items():
                systems.append({
                    "vendor": vn,
                    "system": sn,
                    "source_dir": sc["source_dir"],
                    "pattern": re.compile(vc["file_pattern"]),
                    "system_type": f"{vn}/{sn}"
                })
        else:
            systems.append({
                "vendor": vn,
                "system": vn,
                "source_dir": vc["source_dir"],
                "pattern": re.compile(vc["file_pattern"]),
                "system_type": vn.lower()
            })

    total_processed = 0
    total_errors = 0

    for sys_info in systems:
        sd = sys_info["source_dir"]
        stype = sys_info["system_type"]
        sname = f"{sys_info['vendor']}/{sys_info['system']}"
        dest_dir = os.path.join(dest_base, stype)
        os.makedirs(dest_dir, exist_ok=True)

        logger.info(f"\nProcessing {sname}...")
        logger.info(f"  Source: {sd}")
        system_start_times[sname] = {"oldest": None, "newest": None, "files": 0}
        logger.info(f"  Dest: {dest_dir}")
        logger.info(f"  Target date: {target_date}")

        files_to_process = []
        for root, dirs, files in os.walk(sd):
            for fn in files:
                if not fn.endswith(".gz"):
                    continue
                dt = extract_datetime_from_filename(fn, stype, sys_info["pattern"])
                if dt is None:
                    continue
                if dt >= today:
                    continue  # Not in the past yet

                # Track oldest/newest file dates (only for files being processed)
                if stage2_oldest_date is None or dt < stage2_oldest_date:
                    stage2_oldest_date = dt
                if stage2_newest_date is None or dt > stage2_newest_date:
                    stage2_newest_date = dt
                if system_start_times[sname]["oldest"] is None or dt < system_start_times[sname]["oldest"]:
                    system_start_times[sname]["oldest"] = dt
                if system_start_times[sname]["newest"] is None or dt > system_start_times[sname]["newest"]:
                    system_start_times[sname]["newest"] = dt

                # Extract date from filename for replacement
                ds = sys_info["pattern"].match(fn).group(1)
                # Build new filename with target date
                nf = fn.replace(ds, target_date, 1)
                sp = os.path.join(root, fn)

                files_to_process.append((sp, nf, target_date, stype))

        logger.info(f"  Found {len(files_to_process)} files to process")

        stats = {"processed": 0, "errors": 0, "corrupted": 0}
        stats_lock = Lock()

        with ThreadPoolExecutor(max_workers=4) as ex:
            futs = {}
            for sp, nf, tds, stype in files_to_process:
                if stype == "nokia":
                    tp = re.compile(r"((?:begin|end)Time\s*=\s*[\"'])(\d{8})(\d{4})(\+\d{4})([\"'])")
                    futs[ex.submit(_stage2_process_mo_file, sp, nf, tds, tp, dest_dir)] = (sp, nf)
                else:
                    tp = re.compile(r"((?:begin|end)Time\s*=\s*[\"'])(\d{4}-\d{2}-\d{2})(T\d{2}:\d{2}:\d{2}\+\d{2}:\d{2})([\"'])")
                    futs[ex.submit(_stage2_process_hwi_file, sp, nf, tds, tp, dest_dir)] = (sp, nf)

            completed = 0
            for fut in as_completed(futs):
                ok, fn, st = fut.result()
                with stats_lock:
                    if ok:
                        stats["processed"] += 1
                    elif st == 'corrupted':
                        stats["corrupted"] += 1
                    else:
                        stats["errors"] += 1
                completed += 1
                if completed % 500 == 0:
                    logger.info(f"  {sname} Progress: {completed}/{len(files_to_process)}")
                # Periodic cleanup during processing
                if completed % 5000 == 0:
                    cleaned = _cleanup_dest_dir(dest_dir, sys_info["pattern"], keep_hours, logger)
                    if cleaned > 0:
                        logger.info(f"  Periodic cleanup: removed {cleaned} old files")

        total_processed += stats["processed"]
        total_errors += stats["errors"] + stats["corrupted"]
        logger.info(f"  {sname} Complete: {stats['processed']} processed, "
                    f"{stats['errors']} errors, {stats['corrupted']} corrupted")
        system_start_times[sname]["files"] = len(files_to_process)

    # Cleanup: remove files older than keep_hours from dest directories
    logger.info(f"\nCleaning up dest directories (keeping last {keep_hours} hours)...")
    total_cleaned = 0
    for sys_info in systems:
        stype = sys_info["system_type"]
        dest_dir = os.path.join(dest_base, stype)
        cleaned = _cleanup_dest_dir(dest_dir, sys_info["pattern"], keep_hours, logger)
        total_cleaned += cleaned
        if cleaned > 0:
            logger.info(f"  {stype}: removed {cleaned} old files")

    logger.info("=" * 60)
    logger.info(f"STAGE 2 RUN COMPLETE - {total_processed} processed, {total_errors} errors, {total_cleaned} cleaned")
    logger.info(f"Stage 2 run: oldest_file={stage2_oldest_date.strftime('%Y-%m-%d %H:%M') if stage2_oldest_date else 'N/A'}, newest_file={stage2_newest_date.strftime('%Y-%m-%d %H:%M') if stage2_newest_date else 'N/A'}")
    for sys_info in systems:
        sname = f"{sys_info['vendor']}/{sys_info['system']}"
        sd = sys_info['source_dir']
        info = system_start_times.get(sname, {"oldest": None, "newest": None, "files": 0})
        oldest_str = info['oldest'].strftime('%Y-%m-%d %H:%M') if info['oldest'] else 'N/A'
        newest_str = info['newest'].strftime('%Y-%m-%d %H:%M') if info['newest'] else 'N/A'
        logger.info(f"  {sname}: oldest={oldest_str}, newest={newest_str}, files={info['files']}")
    
    # Log dest folder status
    logger.info("=" * 60)
    logger.info("DEST FOLDER STATUS")
    logger.info("=" * 60)
    for v in ["huawei", "nokia"]:
        dest = f"/home/roundabout/dest/{v}"
        if os.path.exists(dest):
            total = 0
            for root, dirs, files in os.walk(dest):
                total += len([f for f in files if f.endswith(".gz")])
            logger.info(f"  {v}: {total} files")
    logger.info("=" * 60)


def main():
    logger = setup_logging()
    config = load_config()

    # Stage 1: Run once at startup
    if config.get("skip_stage1", False):
        logger.info("Stage 1 skipped (skip_stage1=true)")
    else:
        stage1_conversion(config, logger)

    # Stage 2: Run periodically
    stage2_cfg = config.get("stage2", {})
    interval = stage2_cfg.get("interval_minutes", 15) * 60

    logger.info(f"\nStage 2 will run every {stage2_cfg.get('interval_minutes', 15)} minutes")
    logger.info("Press Ctrl+C to stop")

    while True:
        try:
            stage2_run(config, logger)
            logger.info(f"\nNext Stage 2 run in {stage2_cfg.get('interval_minutes', 15)} minutes...")
            time.sleep(interval)
        except KeyboardInterrupt:
            logger.info("\nStage 2 loop stopped by user")
            break
        except Exception as e:
            logger.error(f"Stage 2 error: {e}")
            time.sleep(60)  # Wait 1 minute before retrying


if __name__ == "__main__":
    main()




















