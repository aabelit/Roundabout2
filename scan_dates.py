#!/usr/bin/env python3
"""
Scan source files, find date range, and convert MO4 files.
Date mapping: oldest_date → today, oldest_date+1 → today+1, etc.
"""

import os
import re
import json
import shutil
import logging
from pathlib import Path
from datetime import datetime, timedelta

CONFIG_PATH = "/home/roundabout2/config.json"
SOURCE_DIR = "/home/roundabout/source"
LOG_DIR = "/home/roundabout2/logs"
LOG_FILE = os.path.join(LOG_DIR, "conversion.log")

def setup_logging():
    """Setup logging to file and console"""
    os.makedirs(LOG_DIR, exist_ok=True)
    
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)
    
    # File handler
    fh = logging.FileHandler(LOG_FILE, mode='w')
    fh.setLevel(logging.INFO)
    
    # Console handler
    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO)
    
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    fh.setFormatter(formatter)
    ch.setFormatter(formatter)
    
    logger.addHandler(fh)
    logger.addHandler(ch)
    
    return logger

def load_config():
    """Load configuration from config.json"""
    with open(CONFIG_PATH, "r") as f:
        return json.load(f)

def extract_date_from_filename(filename, pattern):
    """Extract date string from filename using the configured pattern."""
    match = pattern.match(filename)
    if match:
        return match.group(1)  # First capture group is always the date
    return None

def extract_time_from_filename(filename, pattern):
    """Extract time info from filename for Nokia files."""
    match = pattern.match(filename)
    if match and len(match.groups()) >= 2:
        time_str = match.group(2)  # e.g., "1004+0300"
        return time_str
    return None

def scan_source_files(config, logger):
    """Scan all source directories and extract dates from filenames."""
    vendor_dates = {}
    all_dates = []
    
    vendors = config.get("vendors", {})
    
    for vendor_name, vendor_config in vendors.items():
        systems = vendor_config.get("systems", None)
        file_pattern = re.compile(vendor_config["file_pattern"])
        
        if systems:
            for system_name, system_config in systems.items():
                source_dir = system_config["source_dir"]
                system_key = f"{vendor_name}/{system_name}"
                
                if not os.path.exists(source_dir):
                    logger.warning(f"Source directory not found: {source_dir}")
                    continue
                
                dates = []
                file_count = 0
                
                for root, dirs, files in os.walk(source_dir):
                    for filename in files:
                        if filename.endswith(".gz"):
                            file_count += 1
                            date_str = extract_date_from_filename(filename, file_pattern)
                            if date_str:
                                try:
                                    date_obj = datetime.strptime(date_str, "%Y%m%d").date()
                                    dates.append(date_obj)
                                except ValueError:
                                    pass
                
                vendor_dates[system_key] = {
                    "dates": dates,
                    "file_count": file_count,
                    "oldest_date": min(dates) if dates else None,
                    "newest_date": max(dates) if dates else None
                }
                
                if dates:
                    all_dates.extend(dates)
                    logger.info(f"  {system_key}: {file_count} files, oldest={min(dates)}, newest={max(dates)}")
                else:
                    logger.info(f"  {system_key}: {file_count} files, no dates found")
        else:
            source_dir = vendor_config["source_dir"]
            system_key = vendor_name
            
            if not os.path.exists(source_dir):
                logger.warning(f"Source directory not found: {source_dir}")
                continue
            
            dates = []
            file_count = 0
            
            for root, dirs, files in os.walk(source_dir):
                for filename in files:
                    if filename.endswith(".gz"):
                        file_count += 1
                        date_str = extract_date_from_filename(filename, file_pattern)
                        if date_str:
                            try:
                                date_obj = datetime.strptime(date_str, "%Y%m%d").date()
                                dates.append(date_obj)
                            except ValueError:
                                pass
            
            vendor_dates[system_key] = {
                "dates": dates,
                "file_count": file_count,
                "oldest_date": min(dates) if dates else None,
                "newest_date": max(dates) if dates else None
            }
            
            if dates:
                all_dates.extend(dates)
                logger.info(f"  {system_key}: {file_count} files, oldest={min(dates)}, newest={max(dates)}")
    
    return vendor_dates, all_dates

def convert_mo4_files(config, logger):
    """Convert MO4 files: replace dates with offset from today."""
    nokia_config = config["vendors"]["nokia"]
    mo4_config = nokia_config["systems"]["MO4"]
    source_dir = mo4_config["source_dir"]
    file_pattern = re.compile(nokia_config["file_pattern"])
    
    if not os.path.exists(source_dir):
        logger.error(f"MO4 source directory not found: {source_dir}")
        return
    
    # Get date range
    vendor_dates, all_dates = scan_source_files(config, logger)
    
    if not all_dates:
        logger.error("No dates found in source files")
        return
    
    oldest_date = min(all_dates)
    newest_date = max(all_dates)
    today = datetime.now().date()
    
    logger.info("=" * 60)
    logger.info("MO4 CONVERSION")
    logger.info("=" * 60)
    logger.info(f"Oldest date in source: {oldest_date}")
    logger.info(f"Newest date in source: {newest_date}")
    logger.info(f"Today's date: {today}")
    logger.info(f"Date range: {(newest_date - oldest_date).days + 1} days")
    logger.info("=" * 60)
    
    # Create date mapping
    date_map = {}
    current_date = today
    for src_date in sorted(set(all_dates)):
        offset = (src_date - oldest_date).days
        target_date = today + timedelta(days=offset)
        date_map[src_date] = target_date
        logger.info(f"  {src_date} -> {target_date} (offset: +{offset} days)")
    
    logger.info("=" * 60)
    logger.info("CONVERTING FILES")
    logger.info("=" * 60)
    
    stats = {"total": 0, "converted": 0, "errors": 0}
    
    for root, dirs, files in os.walk(source_dir):
        for filename in files:
            if not filename.endswith(".gz"):
                continue
            
            stats["total"] += 1
            date_str = extract_date_from_filename(filename, file_pattern)
            
            if not date_str:
                continue
            
            try:
                src_date = datetime.strptime(date_str, "%Y%m%d").date()
            except ValueError:
                continue
            
            if src_date not in date_map:
                continue
            
            target_date = date_map[src_date]
            target_date_str = target_date.strftime("%Y%m%d")
            
            # Extract time from filename
            time_str = extract_time_from_filename(filename, file_pattern)
            
            # Build new filename
            # Original: PM202607311004+030048LNBTS_-_410.xml.gz
            # New:      PM202609151004+030048LNBTS_-_410.xml.gz
            new_filename = filename.replace(date_str, target_date_str, 1)
            
            # Read and decode gzipped file
            source_path = os.path.join(root, filename)
            try:
                import gzip
                with gzip.open(source_path, 'rb') as f_in:
                    content = f_in.read()
                
                # Decode content
                try:
                    text_content = content.decode('utf-8')
                except UnicodeDecodeError:
                    text_content = content.decode('latin-1')
                
                # Replace beginTime and endTime in XML
                # Format: endTime="202607311004+0300" or beginTime="202607311004+0300"
                # Replace with: endTime="2026-09-15T10:04:00+03:00"
                
                # Pattern for beginTime/endTime in XML
                time_pattern = re.compile(r'((?:begin|end)Time\s*=\s*["\'])(\d{8})(\d{4})(\+\d{4})(["\'])')
                
                def replace_time(match):
                    prefix = match.group(1)
                    old_date = match.group(2)  # 20260731
                    old_time = match.group(3)  # 1004
                    old_tz = match.group(4)   # +0300
                    quote = match.group(5)
                    
                    if old_date == date_str:
                        # Convert time format: 1004+0300 -> 10:04:00+03:00
                        time_part = old_time[:2] + ":" + old_time[2:] + ":00" + old_tz[:3] + ":" + old_tz[3:]
                        new_datetime = f"{target_date_str}-{time_part}"
                        return f'{prefix}{new_datetime}{quote}'
                    return match.group(0)
                
                new_content = time_pattern.sub(replace_time, text_content)
                
                # Write converted file
                dest_path = os.path.join(root, new_filename)
                with gzip.open(dest_path, 'wb') as f_out:
                    f_out.write(new_content.encode('utf-8'))
                
                # Remove old file
                os.remove(source_path)
                
                stats["converted"] += 1
                if stats["converted"] % 1000 == 0:
                    logger.info(f"  Progress: {stats['converted']}/{stats['total']} files converted")
                
            except Exception as e:
                error_msg = str(e)
                if "Compressed file ended" in error_msg or "corrupted" in error_msg.lower():
                    # Skip corrupted files
                    logger.warning(f"  Skipping corrupted file: {filename} - {error_msg}")
                    stats["skipped"] = stats.get("skipped", 0) + 1
                else:
                    stats["errors"] += 1
                    logger.error(f"  Error processing {filename}: {e}")
    
    logger.info("=" * 60)
    logger.info("CONVERSION COMPLETE")
    logger.info(f"  Total files: {stats['total']}")
    logger.info(f"  Converted: {stats['converted']}")
    logger.info(f"  Errors: {stats['errors']}")
    logger.info("=" * 60)

def main():
    logger = setup_logging()
    
    logger.info("=" * 60)
    logger.info("Source File Date Scanner & Converter")
    logger.info("=" * 60)
    
    # Load config
    config = load_config()
    
    # Scan source files
    vendor_dates, all_dates = scan_source_files(config, logger)
    
    # Output start_date and end_date
    if all_dates:
        oldest = min(all_dates).strftime('%Y-%m-%d')
        newest = max(all_dates).strftime('%Y-%m-%d')
        logger.info(f"\nstart_date={oldest}")
        logger.info(f"end_date={newest}")
        
        # Convert MO4 files
        logger.info("\nStarting MO4 conversion...")
        convert_mo4_files(config, logger)
    else:
        logger.info("No dates found")

if __name__ == "__main__":
    main()
