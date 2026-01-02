#!/usr/bin/env python3
"""
PacVolt Analysis (pva) - CSV Data Format Converter

This tool converts wide-format CSV data files to a normalized long-format CSV
with columns: scet, name, value, unit
"""

import argparse
import csv
import sys
import os
import tempfile
from pathlib import Path
from datetime import datetime, timedelta
from flask import Flask
import webbrowser
import threading
import time
from io import StringIO
import warnings
warnings.filterwarnings('ignore')


def open_csv_file(file_path):
    """
    Open a CSV file and return a csv.reader, filtering out NUL bytes.

    This is necessary because Docker volume mounts on some systems can introduce
    NUL bytes when reading files, which causes csv.reader to fail.

    Args:
        file_path: Path to the CSV file

    Returns:
        csv.reader object
    """
    # Read the file and filter out NUL bytes
    with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
        content = f.read()

    # Remove NUL bytes
    content = content.replace('\x00', '')

    # Create a StringIO object and return a csv.reader
    return csv.reader(StringIO(content))


def extract_unit_from_column_name(column_name):
    """
    Extract unit from column name if present in parentheses.

    Examples:
        AvgVin(U) -> ('AvgVin', 'U')
        AvgAmps(I) -> ('AvgAmps', 'I')
        PSats -> ('PSats', '')
    """
    if '(' in column_name and column_name.endswith(')'):
        name_part = column_name[:column_name.index('(')]
        unit_part = column_name[column_name.index('(') + 1:-1]
        return name_part, unit_part
    return column_name, ''


def parse_time_offset_to_scet(time_str, base_date_str='2025-354T00:00:00'):
    """
    Convert a time offset string to a full SCET timestamp.

    Args:
        time_str: Time string in format HH:MM:SS.f (e.g., "00:00:01.0")
        base_date_str: Base date in ISO 8601 ordinal format (e.g., "2025-354T00:00:00")

    Returns:
        Full timestamp string in ISO 8601 format (e.g., "2025-354T00:00:01")
    """
    # Parse base date (ordinal format: YYYY-DDDTHH:MM:SS)
    base_date = datetime.strptime(base_date_str, '%Y-%jT%H:%M:%S')

    # Parse time offset (format: HH:MM:SS.f)
    time_parts = time_str.split(':')
    hours = int(time_parts[0])
    minutes = int(time_parts[1])

    # Handle seconds with fractional part
    seconds_parts = time_parts[2].split('.')
    seconds = int(seconds_parts[0])
    microseconds = 0
    if len(seconds_parts) > 1:
        # Convert fractional seconds to microseconds
        frac = seconds_parts[1].ljust(6, '0')[:6]  # Pad or truncate to 6 digits
        microseconds = int(frac)

    # Create timedelta and add to base date
    offset = timedelta(hours=hours, minutes=minutes, seconds=seconds, microseconds=microseconds)
    result_datetime = base_date + offset

    # Format as ISO 8601 with ordinal date
    # Format: YYYY-DDDTHH:MM:SS
    return result_datetime.strftime('%Y-%jT%H:%M:%S')


def parse_margin(margin_str):
    """
    Parse a margin string into a timedelta.

    Args:
        margin_str: String in format '#s' (seconds) or '#m' (minutes)
                   e.g., "10s" for 10 seconds, "5m" for 5 minutes

    Returns:
        timedelta object

    Raises:
        ValueError: If format is invalid
    """
    if not margin_str:
        return timedelta(0)

    margin_str = margin_str.strip()

    if margin_str.endswith('s'):
        # Seconds
        try:
            seconds = int(margin_str[:-1])
            return timedelta(seconds=seconds)
        except ValueError:
            raise ValueError(f"Invalid margin format: {margin_str}. Expected format: '#s' (e.g., '10s')")
    elif margin_str.endswith('m'):
        # Minutes
        try:
            minutes = int(margin_str[:-1])
            return timedelta(minutes=minutes)
        except ValueError:
            raise ValueError(f"Invalid margin format: {margin_str}. Expected format: '#m' (e.g., '5m')")
    else:
        raise ValueError(f"Invalid margin format: {margin_str}. Expected format: '#s' or '#m' (e.g., '10s' or '5m')")


def identify_fault_clusters(fault_data, cluster_threshold_minutes=10):
    """
    Identify fault clusters based on time proximity.

    Faults within the threshold time of each other are grouped into the same cluster.

    Args:
        fault_data: List of fault data tuples (scet, name, value, unit)
        cluster_threshold_minutes: Maximum time gap (in minutes) between faults in the same cluster

    Returns:
        List of dictionaries, each containing:
            - 'min_time': earliest fault timestamp in cluster (datetime)
            - 'max_time': latest fault timestamp in cluster (datetime)
            - 'fault_count': number of faults in cluster
    """
    if not fault_data:
        return []

    # Extract unique fault timestamps (sorted)
    fault_timestamps = []
    for row in fault_data:
        scet = row[0]  # First element is the timestamp
        try:
            dt = datetime.strptime(scet, '%Y-%jT%H:%M:%S')
            if dt not in fault_timestamps:
                fault_timestamps.append(dt)
        except ValueError:
            continue

    fault_timestamps.sort()

    if not fault_timestamps:
        return []

    # Identify clusters
    clusters = []
    current_cluster_start = fault_timestamps[0]
    current_cluster_end = fault_timestamps[0]
    fault_count = 1

    threshold = timedelta(minutes=cluster_threshold_minutes)

    for i in range(1, len(fault_timestamps)):
        time_gap = fault_timestamps[i] - fault_timestamps[i-1]

        if time_gap <= threshold:
            # Part of current cluster
            current_cluster_end = fault_timestamps[i]
            fault_count += 1
        else:
            # Start new cluster
            clusters.append({
                'min_time': current_cluster_start,
                'max_time': current_cluster_end,
                'fault_count': fault_count
            })
            current_cluster_start = fault_timestamps[i]
            current_cluster_end = fault_timestamps[i]
            fault_count = 1

    # Add the last cluster
    clusters.append({
        'min_time': current_cluster_start,
        'max_time': current_cluster_end,
        'fault_count': fault_count
    })

    return clusters


def filter_data_by_clusters(all_rows, fault_clusters, margin_delta=None):
    """
    Filter data rows to only include those within fault cluster time ranges (with optional margin).

    Args:
        all_rows: List of data rows (tuples of scet, name, value, unit)
        fault_clusters: List of fault cluster dictionaries with 'min_time' and 'max_time'
        margin_delta: Optional timedelta to extend cluster ranges

    Returns:
        Filtered list of rows
    """
    if not fault_clusters:
        return all_rows

    # Build extended cluster ranges
    cluster_ranges = []
    for cluster in fault_clusters:
        min_time = cluster['min_time']
        max_time = cluster['max_time']

        if margin_delta:
            min_time = min_time - margin_delta
            max_time = max_time + margin_delta

        cluster_ranges.append((min_time, max_time))

    # Filter rows
    filtered_rows = []
    for row in all_rows:
        scet = row[0]
        try:
            row_time = datetime.strptime(scet, '%Y-%jT%H:%M:%S')

            # Check if row time is within any cluster range
            in_range = False
            for min_time, max_time in cluster_ranges:
                if min_time <= row_time <= max_time:
                    in_range = True
                    break

            if in_range:
                filtered_rows.append(row)
        except ValueError:
            # Keep rows with invalid timestamps
            filtered_rows.append(row)

    return filtered_rows


def parse_fault_data(fault_file, min_time=None, max_time=None):
    """
    Parse fault data from a CSV file.

    Args:
        fault_file: Path to fault data CSV file
        min_time: Optional minimum SCET timestamp for filtering
        max_time: Optional maximum SCET timestamp for filtering

    Returns:
        List of tuples: [(scet, name, value, unit), ...]
    """
    fault_rows = []

    # Parse time boundaries if provided
    min_datetime = None
    max_datetime = None

    if min_time:
        min_datetime = datetime.strptime(min_time, '%Y-%jT%H:%M:%S')
    if max_time:
        max_datetime = datetime.strptime(max_time, '%Y-%jT%H:%M:%S')

    reader = open_csv_file(fault_file)

    # Skip first line (metadata)
    next(reader)

    # Skip second line (metadata for fault files, may vary)
    next(reader)

    # Skip third line (column headers)
    next(reader)

    # Process fault data rows
    for row in reader:
        if not row or len(row) < 4:
            continue

        # Column 2 and 3 combine to make scet timestamp
        # Column 4 is the value
        date_part = row[1].strip()  # Column 2 (0-indexed: column 1)
        time_part = row[2].strip()  # Column 3 (0-indexed: column 2)
        value = row[3].strip()       # Column 4 (0-indexed: column 3)

        # Parse and normalize to SCET format (YYYY-DDDTHH:MM:SS)
        try:
            # Try parsing as ordinal date format (YYYY-DDD)
            if 'T' in date_part:
                # Already combined format
                scet_datetime = datetime.strptime(f"{date_part}", '%Y-%jT%H:%M:%S')
            elif '-' in date_part and len(date_part.split('-')) == 2:
                # Ordinal date format: "2025-354"
                scet_datetime = datetime.strptime(f"{date_part}T{time_part}", '%Y-%jT%H:%M:%S')
            elif '/' in date_part:
                # Calendar date format: "12/20/2025" or "2025/12/20"
                # Try MM/DD/YYYY format first
                try:
                    dt = datetime.strptime(date_part, '%m/%d/%Y')
                except ValueError:
                    # Try DD/MM/YYYY format
                    try:
                        dt = datetime.strptime(date_part, '%d/%m/%Y')
                    except ValueError:
                        # Try YYYY/MM/DD format
                        dt = datetime.strptime(date_part, '%Y/%m/%d')

                # Parse time and combine
                time_parts = time_part.split(':')
                scet_datetime = dt.replace(
                    hour=int(time_parts[0]),
                    minute=int(time_parts[1]),
                    second=int(time_parts[2].split('.')[0]) if len(time_parts) > 2 else 0
                )
            else:
                # Try ISO format YYYY-MM-DD
                dt = datetime.strptime(date_part, '%Y-%m-%d')
                time_parts = time_part.split(':')
                scet_datetime = dt.replace(
                    hour=int(time_parts[0]),
                    minute=int(time_parts[1]),
                    second=int(time_parts[2].split('.')[0]) if len(time_parts) > 2 else 0
                )

            # Format as ISO 8601 ordinal date: YYYY-DDDTHH:MM:SS
            scet_timestamp = scet_datetime.strftime('%Y-%jT%H:%M:%S')

            # Apply time filtering if specified
            if min_datetime and scet_datetime < min_datetime:
                continue
            if max_datetime and scet_datetime > max_datetime:
                continue

            # Add fault row: (scet, name, value, unit)
            fault_rows.append((scet_timestamp, 'Fault', value, 'none'))

        except (ValueError, IndexError):
            # Skip rows with invalid timestamps
            continue

    return fault_rows


def convert_csv(input_file, output_file, min_time=None, max_time=None, fault_file=None):
    """
    Convert wide-format CSV to long-format CSV.

    Input format:
        - First line: metadata/header (skipped)
        - Second line: column names (RecNr, ..., Time)
        - Data lines: one row per time point with multiple measurements

    Output format:
        - Columns: scet, name, value, unit
        - One row per measurement per time point

    Args:
        input_file: Path to input CSV file
        output_file: Path to output CSV file
        min_time: Optional minimum SCET timestamp (ISO 8601 format). Data before this time is excluded.
        max_time: Optional maximum SCET timestamp (ISO 8601 format). Data after this time is excluded.
        fault_file: Optional path to fault data CSV file. Fault data will be inserted before regular data.
    """
    # Parse fault data if provided
    fault_data = []
    if fault_file:
        fault_data = parse_fault_data(fault_file, min_time, max_time)

    # Parse time boundaries if provided
    min_datetime = None
    max_datetime = None

    if min_time:
        min_datetime = datetime.strptime(min_time, '%Y-%jT%H:%M:%S')
    if max_time:
        max_datetime = datetime.strptime(max_time, '%Y-%jT%H:%M:%S')
    reader = open_csv_file(input_file)

    # Read first line (metadata) to extract base date
    metadata_line = next(reader)
    base_date_str = '2025-354T00:00:00'  # Default

    if metadata_line and len(metadata_line) >= 4:
        # Parse base date from metadata line
        # Format: 1P-120/240V-200A-60Hz,WINDOW_LVR50,DD/MM/YYYY,HH:MM:SS,V1.0
        date_str = metadata_line[2].strip()
        time_str = metadata_line[3].strip()
        try:
            # Parse DD/MM/YYYY format
            base_dt = datetime.strptime(date_str, '%d/%m/%Y')
            # Add time component
            time_parts = time_str.split(':')
            base_dt = base_dt.replace(
                hour=int(time_parts[0]) if len(time_parts) > 0 else 0,
                minute=int(time_parts[1]) if len(time_parts) > 1 else 0,
                second=int(time_parts[2].split('.')[0]) if len(time_parts) > 2 else 0
            )
            # Convert to ordinal format
            base_date_str = base_dt.strftime('%Y-%jT%H:%M:%S')
        except (ValueError, IndexError):
            # If parsing fails, use default
            base_date_str = '2025-354T00:00:00'

    # Read column headers
    headers = next(reader)

    # Find indices
    time_col_idx = len(headers) - 1  # Last column
    recnr_col_idx = 0  # First column

    # Get data column names (exclude RecNr and Time)
    data_columns = []
    for i, header in enumerate(headers):
        if i != recnr_col_idx and i != time_col_idx:
            name, unit = extract_unit_from_column_name(header)
            data_columns.append((i, name, unit))

    # Collect all output rows for sorting
    all_rows = []

    # Add fault data (already filtered during parsing)
    all_rows.extend(fault_data)

    # Process and collect data rows
    for row in reader:
        if not row or len(row) < len(headers):
            continue

        time_value = row[time_col_idx]
        # Convert time offset to full SCET timestamp using base date from file header
        scet_timestamp = parse_time_offset_to_scet(time_value, base_date_str)
        scet_datetime = datetime.strptime(scet_timestamp, '%Y-%jT%H:%M:%S')

        # Apply time filtering
        if min_datetime and scet_datetime < min_datetime:
            continue
        if max_datetime and scet_datetime > max_datetime:
            continue

        # For each data column, collect an output row
        for col_idx, col_name, col_unit in data_columns:
            value = row[col_idx]
            all_rows.append((scet_timestamp, col_name, value, col_unit))

    # Sort all rows by timestamp (first element of tuple)
    all_rows.sort(key=lambda x: datetime.strptime(x[0], '%Y-%jT%H:%M:%S'))

    # Write sorted data to output file
    with open(output_file, 'w', newline='') as outfile:
        writer = csv.writer(outfile)

        # Write output header
        writer.writerow(['scet', 'name', 'value', 'unit'])

        # Write all sorted rows
        for row in all_rows:
            writer.writerow(row)


def convert_log_to_csv(log_file, csv_file):
    """
    Convert a .log file to .csv with UTF-8 encoding.

    Args:
        log_file: Path to input .log file
        csv_file: Path to output .csv file
    """
    with open(log_file, 'r', encoding='utf-8', errors='replace') as infile:
        content = infile.read()

    with open(csv_file, 'w', encoding='utf-8', newline='') as outfile:
        outfile.write(content)


def get_time_range_from_csv(csv_file, is_fault_file=False):
    """
    Get the time range (min and max timestamps) from a CSV file.

    Args:
        csv_file: Path to CSV file
        is_fault_file: True if this is a fault file, False for data files

    Returns:
        Tuple of (min_datetime, max_datetime) or (None, None) if no valid data
    """
    min_dt = None
    max_dt = None

    try:
        reader = open_csv_file(csv_file)

        # Read first line (metadata) to extract base date for data files
        metadata_line = next(reader, None)
        base_date_str = None

        if not is_fault_file and metadata_line:
            # Parse base date from metadata line
            # Format: 1P-120/240V-200A-60Hz,WINDOW_LVR50,DD/MM/YYYY,HH:MM:SS,V1.0
            if len(metadata_line) >= 4:
                date_str = metadata_line[2].strip()
                time_str = metadata_line[3].strip()
                try:
                    # Parse DD/MM/YYYY format
                    base_dt = datetime.strptime(date_str, '%d/%m/%Y')
                    # Add time component
                    time_parts = time_str.split(':')
                    base_dt = base_dt.replace(
                        hour=int(time_parts[0]) if len(time_parts) > 0 else 0,
                        minute=int(time_parts[1]) if len(time_parts) > 1 else 0,
                        second=int(time_parts[2].split('.')[0]) if len(time_parts) > 2 else 0
                    )
                    # Convert to ordinal format
                    base_date_str = base_dt.strftime('%Y-%jT%H:%M:%S')
                except (ValueError, IndexError):
                    # If parsing fails, use default
                    base_date_str = '2025-354T00:00:00'

        # Skip second line (metadata for fault files, headers for data files)
        next(reader, None)

        # For fault files, skip third line (column headers)
        if is_fault_file:
            next(reader, None)

        for row in reader:
            if not row:
                continue

            try:
                if is_fault_file:
                    # Fault file: columns 2 and 3 for date/time
                    if len(row) < 4:
                        continue
                    date_part = row[1].strip()
                    time_part = row[2].strip()

                    # Parse date (handle various formats)
                    if '-' in date_part and len(date_part.split('-')) == 2:
                        # Ordinal format
                        dt = datetime.strptime(f"{date_part}T{time_part}", '%Y-%jT%H:%M:%S')
                    elif '/' in date_part:
                        try:
                            dt = datetime.strptime(date_part, '%m/%d/%Y')
                        except ValueError:
                            try:
                                dt = datetime.strptime(date_part, '%d/%m/%Y')
                            except ValueError:
                                dt = datetime.strptime(date_part, '%Y/%m/%d')
                        time_parts = time_part.split(':')
                        dt = dt.replace(
                            hour=int(time_parts[0]),
                            minute=int(time_parts[1]),
                            second=int(time_parts[2].split('.')[0]) if len(time_parts) > 2 else 0
                        )
                    else:
                        dt = datetime.strptime(date_part, '%Y-%m-%d')
                        time_parts = time_part.split(':')
                        dt = dt.replace(
                            hour=int(time_parts[0]),
                            minute=int(time_parts[1]),
                            second=int(time_parts[2].split('.')[0]) if len(time_parts) > 2 else 0
                        )
                else:
                    # Data file: last column is time
                    if len(row) < 2:
                        continue
                    time_value = row[-1].strip()
                    # Use base date from file header
                    if base_date_str:
                        dt_str = parse_time_offset_to_scet(time_value, base_date_str)
                    else:
                        dt_str = parse_time_offset_to_scet(time_value)
                    dt = datetime.strptime(dt_str, '%Y-%jT%H:%M:%S')

                if min_dt is None or dt < min_dt:
                    min_dt = dt
                if max_dt is None or dt > max_dt:
                    max_dt = dt

            except (ValueError, IndexError):
                continue

    except FileNotFoundError:
        return None, None

    return min_dt, max_dt


def check_overlap(range1_min, range1_max, range2_min, range2_max):
    """
    Check if two time ranges overlap.

    Args:
        range1_min, range1_max: First time range
        range2_min, range2_max: Second time range

    Returns:
        True if ranges overlap, False otherwise
    """
    if range1_min is None or range1_max is None or range2_min is None or range2_max is None:
        return False

    # Ranges overlap if one starts before the other ends
    return range1_min <= range2_max and range2_min <= range1_max


def process_directory_mode(directory, output_file, margin=None, overlap_policy='ONLY_RECENT', exclude_policy='NONE', verbose=False):
    """
    Process all files in a directory to generate combined output.

    Args:
        directory: Path to directory containing .log files
        output_file: Path to output CSV file
        margin: Optional margin string (e.g., '5m', '10s') to extend time ranges
        overlap_policy: Policy for handling overlapping files ('ONLY_RECENT' or 'ALL')
        exclude_policy: Policy for excluding data ('NONE' or 'ALL')
        verbose: Enable verbose output

    Returns:
        True on success, False on error
    """
    dir_path = Path(directory)
    if not dir_path.exists() or not dir_path.is_dir():
        print(f"Error: Directory not found: {directory}", file=sys.stderr)
        return False

    # Define the expected files
    log_files = ['24HR.log', '24prev.log', 'FaultLog.log', 'Month.log']
    data_files = ['24HR.log', '24prev.log', 'Month.log']

    if verbose:
        print(f"Processing directory: {directory}")
        print("Converting .log files to .csv with UTF-8 encoding...")

    # Convert all .log files to .csv
    for log_file in log_files:
        log_path = dir_path / log_file
        csv_path = dir_path / log_file.replace('.log', '.csv')

        if not log_path.exists():
            if verbose:
                print(f"  Warning: {log_file} not found, skipping...")
            continue

        if verbose:
            print(f"  Converting {log_file} -> {csv_path.name}")

        convert_log_to_csv(log_path, csv_path)

    # Generate intermediate output files for debugging (24HR-out.csv, 24prev-out.csv)
    if verbose:
        print("\nGenerating intermediate output files for debugging...")

    for data_file_name in ['24HR.csv', '24prev.csv']:
        data_file = dir_path / data_file_name
        if data_file.exists():
            output_name = data_file_name.replace('.csv', '-out.csv')
            intermediate_output = dir_path / output_name

            if verbose:
                print(f"  Converting {data_file_name} -> {output_name}")

            try:
                convert_csv(
                    input_file=data_file,
                    output_file=intermediate_output,
                    fault_file=None,
                    min_time=None,
                    max_time=None
                )
            except Exception as e:
                print(f"  Warning: Could not convert {data_file_name}: {e}", file=sys.stderr)

    # Get time range from FaultLog.csv
    fault_csv = dir_path / 'FaultLog.csv'
    if not fault_csv.exists():
        print("Error: FaultLog.csv not found after conversion", file=sys.stderr)
        return False

    if verbose:
        print("\nAnalyzing FaultLog.csv time range...")

    fault_min, fault_max = get_time_range_from_csv(fault_csv, is_fault_file=True)

    if fault_min is None or fault_max is None:
        print("Error: Could not determine time range from FaultLog.csv", file=sys.stderr)
        return False

    if verbose:
        print(f"  FaultLog time range: {fault_min.strftime('%Y-%jT%H:%M:%S')} to {fault_max.strftime('%Y-%jT%H:%M:%S')}")

    # Apply margin if specified
    if margin:
        try:
            margin_delta = parse_margin(margin)
        except ValueError as e:
            print(f"Error: {e}", file=sys.stderr)
            return False

        fault_min = fault_min - margin_delta
        fault_max = fault_max + margin_delta

        if verbose:
            print(f"  Applying margin: {margin}")
            print(f"  Extended time range: {fault_min.strftime('%Y-%jT%H:%M:%S')} to {fault_max.strftime('%Y-%jT%H:%M:%S')}")

    if verbose:
        print("\nChecking for overlapping data files...")

    # Check which data files overlap with FaultLog (in priority order)
    overlapping_files = []

    for data_file in data_files:
        csv_path = dir_path / data_file.replace('.log', '.csv')

        if not csv_path.exists():
            if verbose:
                print(f"  {csv_path.name}: Not found, skipping...")
            continue

        data_min, data_max = get_time_range_from_csv(csv_path, is_fault_file=False)

        if data_min is None or data_max is None:
            if verbose:
                print(f"  {csv_path.name}: No valid data found")
            continue

        has_overlap = check_overlap(fault_min, fault_max, data_min, data_max)

        if verbose:
            print(f"  {csv_path.name}: {data_min.strftime('%Y-%jT%H:%M:%S')} to {data_max.strftime('%Y-%jT%H:%M:%S')} - {'OVERLAP' if has_overlap else 'no overlap'}")

        if has_overlap:
            overlapping_files.append(csv_path)

    # Validate that at least one file overlaps
    if len(overlapping_files) == 0:
        print("\nError: No data files overlap with FaultLog.csv time range", file=sys.stderr)
        return False

    if overlap_policy == 'ONLY_RECENT':
        # Select first overlapping file (priority: 24HR.csv, 24prev.csv, Month.csv)
        overlapping_file = overlapping_files[0]

        if len(overlapping_files) > 1:
            print(f"\n✓ Multiple overlapping files found: {', '.join([f.name for f in overlapping_files])}")
            print(f"✓ Selecting first in priority order: {overlapping_file.name}")
        else:
            print(f"\n✓ Using {overlapping_file.name} as data source (overlaps with FaultLog.csv)")

        if verbose:
            print(f"\nGenerating output: {output_file}")
            if margin:
                print(f"Filtering data to extended time range: {fault_min.strftime('%Y-%jT%H:%M:%S')} to {fault_max.strftime('%Y-%jT%H:%M:%S')}")
            else:
                print(f"Filtering data to FaultLog time range: {fault_min.strftime('%Y-%jT%H:%M:%S')} to {fault_max.strftime('%Y-%jT%H:%M:%S')}")

        # Identify fault clusters for analysis
        fault_data = parse_fault_data(
            fault_csv,
            min_time=fault_min.strftime('%Y-%jT%H:%M:%S'),
            max_time=fault_max.strftime('%Y-%jT%H:%M:%S')
        )
        fault_clusters = identify_fault_clusters(fault_data)

        if verbose and fault_clusters:
            print(f"\n  Identified {len(fault_clusters)} fault cluster(s):")
            for i, cluster in enumerate(fault_clusters, 1):
                duration = cluster['max_time'] - cluster['min_time']
                duration_str = str(duration).split('.')[0]  # Remove microseconds
                print(f"    Cluster {i}: {cluster['min_time'].strftime('%Y-%jT%H:%M:%S')} to {cluster['max_time'].strftime('%Y-%jT%H:%M:%S')}")
                print(f"              Duration: {duration_str}, Faults: {cluster['fault_count']}")

        # Generate output using convert_csv with FaultLog and overlapping file
        # Filter data to only include timestamps within FaultLog time range
        convert_csv(
            input_file=overlapping_file,
            output_file=output_file,
            fault_file=fault_csv,
            min_time=fault_min.strftime('%Y-%jT%H:%M:%S'),
            max_time=fault_max.strftime('%Y-%jT%H:%M:%S')
        )

        # Apply exclusion policy if specified
        if exclude_policy == 'ALL' and fault_clusters:
            margin_delta = None
            if margin:
                try:
                    margin_delta = parse_margin(margin)
                except ValueError:
                    pass  # Already handled earlier

            # Read the output file
            all_rows = []
            with open(output_file, 'r', encoding='utf-8', errors='ignore') as f:
                reader = csv.reader(f)
                next(reader)  # Skip header
                for row in reader:
                    all_rows.append(tuple(row))

            original_count = len(all_rows)

            # Filter data
            all_rows = filter_data_by_clusters(all_rows, fault_clusters, margin_delta)

            # Write filtered data back
            with open(output_file, 'w', newline='') as f:
                writer = csv.writer(f)
                writer.writerow(['scet', 'name', 'value', 'unit'])
                for row in all_rows:
                    writer.writerow(row)

            if verbose:
                excluded_count = original_count - len(all_rows)
                print(f"\n  Data exclusion applied:")
                print(f"    Original rows: {original_count:,}")
                print(f"    Excluded rows: {excluded_count:,} ({100*excluded_count/original_count:.1f}%)")
                print(f"    Remaining rows: {len(all_rows):,}")

    else:  # overlap_policy == 'ALL'
        # Merge data from all overlapping files, excluding duplicate time ranges
        print(f"\n✓ Multiple overlapping files found: {', '.join([f.name for f in overlapping_files])}")
        print(f"✓ Merging data from all overlapping files (excluding duplicate time ranges)")

        if verbose:
            print(f"\nGenerating output: {output_file}")
            if margin:
                print(f"Filtering data to extended time range: {fault_min.strftime('%Y-%jT%H:%M:%S')} to {fault_max.strftime('%Y-%jT%H:%M:%S')}")
            else:
                print(f"Filtering data to FaultLog time range: {fault_min.strftime('%Y-%jT%H:%M:%S')} to {fault_max.strftime('%Y-%jT%H:%M:%S')}")

        # Collect data from all files, tracking covered time ranges
        all_rows = []
        covered_ranges = []  # List of (min, max) tuples

        # First, process fault data separately using the full fault range
        if verbose:
            print(f"  Processing FaultLog.csv: {fault_min.strftime('%Y-%jT%H:%M:%S')} to {fault_max.strftime('%Y-%jT%H:%M:%S')}")

        fault_data = parse_fault_data(
            fault_csv,
            min_time=fault_min.strftime('%Y-%jT%H:%M:%S'),
            max_time=fault_max.strftime('%Y-%jT%H:%M:%S')
        )
        all_rows.extend(fault_data)

        # Identify fault clusters
        fault_clusters = identify_fault_clusters(fault_data)

        if verbose and fault_clusters:
            print(f"\n  Identified {len(fault_clusters)} fault cluster(s):")
            for i, cluster in enumerate(fault_clusters, 1):
                duration = cluster['max_time'] - cluster['min_time']
                duration_str = str(duration).split('.')[0]  # Remove microseconds
                print(f"    Cluster {i}: {cluster['min_time'].strftime('%Y-%jT%H:%M:%S')} to {cluster['max_time'].strftime('%Y-%jT%H:%M:%S')}")
                print(f"              Duration: {duration_str}, Faults: {cluster['fault_count']}")

        # Then process each data file
        for file_path in overlapping_files:
            # Get the time range of this file
            file_min, file_max = get_time_range_from_csv(file_path, is_fault_file=False)

            # Calculate the intersection of this file's range with the fault range
            segment_min = max(fault_min, file_min)
            segment_max = min(fault_max, file_max)

            # Determine which parts of this segment are not already covered
            # For simplicity, we'll exclude this file if its entire range overlaps with already covered ranges
            # A more sophisticated approach would handle partial overlaps, but for now we use a simple check
            is_fully_covered = False
            for cov_min, cov_max in covered_ranges:
                if segment_min >= cov_min and segment_max <= cov_max:
                    is_fully_covered = True
                    break

            if is_fully_covered:
                if verbose:
                    print(f"  Skipping {file_path.name} - time range fully covered by previous files")
                continue

            # Calculate the uncovered portion
            # For now, we'll use a simple approach: include data from ranges not fully covered
            # We'll use the segment but exclude exact timestamp duplicates later
            if verbose:
                print(f"  Processing {file_path.name}: {segment_min.strftime('%Y-%jT%H:%M:%S')} to {segment_max.strftime('%Y-%jT%H:%M:%S')}")

            # Create a temporary output file
            temp_file = tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.csv')
            temp_path = temp_file.name
            temp_file.close()

            try:
                # Process this file without fault data (fault data processed separately)
                convert_csv(
                    input_file=file_path,
                    output_file=temp_path,
                    fault_file=None,
                    min_time=segment_min.strftime('%Y-%jT%H:%M:%S'),
                    max_time=segment_max.strftime('%Y-%jT%H:%M:%S')
                )

                # Read the temporary file and collect rows
                with open(temp_path, 'r', encoding='utf-8', errors='ignore') as f:
                    reader = csv.reader(f)
                    next(reader)  # Skip header
                    for row in reader:
                        all_rows.append(tuple(row))

                # Track this range as covered
                covered_ranges.append((segment_min, segment_max))

            finally:
                # Clean up temporary file
                Path(temp_path).unlink()

        # Apply exclusion policy if specified
        if exclude_policy == 'ALL' and fault_clusters:
            margin_delta = None
            if margin:
                try:
                    margin_delta = parse_margin(margin)
                except ValueError:
                    pass  # Already handled earlier

            original_count = len(all_rows)
            all_rows = filter_data_by_clusters(all_rows, fault_clusters, margin_delta)

            if verbose:
                excluded_count = original_count - len(all_rows)
                print(f"\n  Data exclusion applied:")
                print(f"    Original rows: {original_count:,}")
                print(f"    Excluded rows: {excluded_count:,} ({100*excluded_count/original_count:.1f}%)")
                print(f"    Remaining rows: {len(all_rows):,}")

        # Sort all rows by timestamp (no deduplication - keep all measurements)
        all_rows.sort(key=lambda x: datetime.strptime(x[0], '%Y-%jT%H:%M:%S'))

        # Write to output file
        with open(output_file, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(['scet', 'name', 'value', 'unit'])
            for row in all_rows:
                writer.writerow(row)

        if verbose:
            print(f"  Merged {len(all_rows)} rows from {len(overlapping_files)} files")

    return True


def create_plot_html(output_file):
    """
    Create an interactive plot of the output data using dtat/plotly.

    Args:
        output_file: Path to the output CSV file

    Returns:
        HTML string containing the plot, or None if plotting fails
    """
    try:
        # Import plotting libraries (optional dependencies)
        import pandas as pd
        import dtat
        import dtat.plot as dtatplot
        from dtat.dataconnectors.csvconnector import CSVConnector
        from dtat.types import CustomizedTrace
        import plotly.io as pio

        # Check if output file exists and has data
        if not Path(output_file).exists():
            return None

        # Load data using dtat CSV connector
        data_for_set = CSVConnector(str(output_file)).get_data()

        # Create the stacked graph
        fig, c, m, t = dtatplot.make_stacked_graph(
            data_for_set,
            x_var="scet",
            y_vars=[["AvgVin", "AvgVout"], ["Fault"], ["AvgAmps"], ["Avg_kVA"], ["Avg_kW"]],
            customize_dict={
                'AvgVin': CustomizedTrace(
                    color='red',
                ),
                'Fault': CustomizedTrace(
                    size=12,
                    symbol='diamond',
                    color='red',
                    plot_lines=False
                )
            }
        )

        # Convert plot to HTML (include plotlyjs to make it self-contained)
        plot_html = fig.to_html(include_plotlyjs='cdn', full_html=False)

        return plot_html

    except ImportError as e:
        # dtat or plotly not available
        print(f"Warning: Plotting libraries not available: {e}", file=sys.stderr)
        return None
    except Exception as e:
        # Any other error during plotting
        print(f"Warning: Could not create plot: {e}", file=sys.stderr)
        return None


def generate_summary_html(input_files, output_file, fault_file=None, plot_html=None):
    """
    Generate HTML page showing input and output files.

    Args:
        input_files: List of input file paths
        output_file: Output file path
        fault_file: Optional fault file path

    Returns:
        HTML string
    """
    # Convert paths to absolute paths for display
    input_files_html = ""
    for input_file in input_files:
        abs_path = Path(input_file).absolute()
        input_files_html += f"    {abs_path}<br>\n"

    output_abs = Path(output_file).absolute()

    fault_section = ""
    if fault_file:
        fault_abs = Path(fault_file).absolute()
        fault_section = f"""
<div class="section">
    <strong>Fault File:</strong>
    <div class="file-path">
        {fault_abs}
    </div>
</div>
"""

    # Add plot section if plot HTML is provided
    plot_section = ""
    if plot_html:
        plot_section = f"""
        <div style="margin-top: 40px; font-size: 14px; opacity: 0.8;">
            Processing completed successfully!
        </div>
        <div style="margin-top: 30px; background: white; padding: 20px; border-radius: 10px;">
            <h2 style="color: #333; margin-top: 0;">Data Visualization</h2>
            {plot_html}
        </div>
"""
    else:
        plot_section = """
        <div style="margin-top: 40px; font-size: 14px; opacity: 0.8;">
            Processing completed successfully!
        </div>
"""

    html = f"""
<!DOCTYPE html>
<html>
<head>
    <title>PacVolt Analysis - File Summary</title>
    <style>
        body {{
            margin: 0;
            padding: 20px;
            font-family: 'Courier New', monospace;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
        }}
        .container {{
            max-width: 1200px;
            background: rgba(0, 0, 0, 0.3);
            padding: 30px;
            border-radius: 10px;
        }}
        h1 {{
            margin-top: 0;
            font-size: 32px;
        }}
        .section {{
            margin-bottom: 30px;
        }}
        strong {{
            font-size: 18px;
            display: block;
            margin-bottom: 10px;
        }}
        .file-path {{
            background: rgba(0, 0, 0, 0.2);
            padding: 10px;
            border-radius: 5px;
            font-size: 14px;
            word-break: break-all;
        }}
    </style>
</head>
<body>
    <div class="container">
        <h1>PacVolt Analysis - File Summary</h1>

        <div class="section">
            <strong>Input Files:</strong>
            <div class="file-path">
{input_files_html}            </div>
        </div>

        {fault_section}

        <div class="section">
            <strong>Output File:</strong>
            <div class="file-path">
                {output_abs}
            </div>
        </div>

        {plot_section}
    </div>
</body>
</html>
"""
    return html


def start_web_server(input_files, output_file, fault_file=None, plot_html=None, port=5000):
    """
    Start a Flask web server to display file summary and plot.

    Args:
        input_files: List of input file paths
        output_file: Output file path
        fault_file: Optional fault file path
        plot_html: Optional HTML string containing the plot
        port: Port to run the server on (default 5000)
    """
    app = Flask(__name__)

    html_content = generate_summary_html(input_files, output_file, fault_file, plot_html)

    @app.route('/')
    def summary():
        return html_content

    # Suppress Flask development server warning
    import logging
    log = logging.getLogger('werkzeug')
    log.setLevel(logging.ERROR)

    print("=" * 60)
    print("Starting web server...")
    print("=" * 60)
    print(f"Access the file summary at: http://localhost:{port}")
    print("Press Ctrl+C to stop the server")
    print("=" * 60)

    # Open browser after a short delay
    def open_browser():
        time.sleep(1)
        webbrowser.open(f'http://localhost:{port}')

    threading.Thread(target=open_browser, daemon=True).start()

    # Run the server
    app.run(host='0.0.0.0', port=port, debug=False)


def main():
    """Main entry point for the CLI tool."""
    parser = argparse.ArgumentParser(
        description='Convert wide-format CSV data to normalized long-format CSV',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  Basic conversion:
    %(prog)s -i input.csv -o output.csv
    %(prog)s --input data/24prev.csv --output data/converted.csv

  Filter by time range:
    %(prog)s -i input.csv -o output.csv --min-time 2025-354T12:00:00
    %(prog)s -i input.csv -o output.csv --max-time 2025-354T18:00:00
    %(prog)s -i input.csv -o output.csv --min-time 2025-354T12:00:00 --max-time 2025-354T18:00:00

  Extract last 10%% of data (for 24-hour dataset starting at 2025-354T00:00:00):
    %(prog)s -i 24prev.csv -o output.csv --min-time 2025-354T21:36:00 -v

  Include fault data:
    %(prog)s -i input.csv -o output.csv -f FaultLog.log
    %(prog)s -i input.csv -o output.csv --fault-file FaultLog.log -v

  Directory mode (auto-detect overlapping data):
    %(prog)s -d data/testing_12.20.25 -o output.csv -v
    %(prog)s --dir data/testing_12.20.25 --output output.csv

  Directory mode with time margin (extend FaultLog time range):
    %(prog)s -d data/testing_12.20.25 -o output.csv -m 5m -v
    %(prog)s -d data/testing_12.20.25 -o output.csv --margin 30s -v

  Directory mode with overlap policy (merge all overlapping files):
    %(prog)s -d data/testing_12.20.25 -o output.csv -p ALL -v
    %(prog)s -d data/testing_12.20.25 -o output.csv --overlap ONLY_RECENT -v

  Directory mode with data exclusion (only include data near fault clusters):
    %(prog)s -d data/testing_12.20.25 -o output.csv -e ALL -v
    %(prog)s -d data/testing_12.20.25 -o output.csv -e ALL -m 5m -v
        """
    )

    parser.add_argument(
        '-i', '--input',
        type=str,
        help='Input CSV file path (required unless using --dir)'
    )

    parser.add_argument(
        '-o', '--output',
        required=True,
        help='Output CSV file path'
    )

    parser.add_argument(
        '-d', '--dir',
        type=str,
        help='Directory containing .log files (24HR.log, 24prev.log, FaultLog.log, Month.log). '
             'Automatically converts to CSV and finds overlapping data.'
    )

    parser.add_argument(
        '-v', '--verbose',
        action='store_true',
        help='Enable verbose output'
    )

    parser.add_argument(
        '--min-time',
        type=str,
        help='Minimum SCET timestamp (ISO 8601 ordinal format: YYYY-DDDTHH:MM:SS). '
             'Data before this time will be excluded.'
    )

    parser.add_argument(
        '--max-time',
        type=str,
        help='Maximum SCET timestamp (ISO 8601 ordinal format: YYYY-DDDTHH:MM:SS). '
             'Data after this time will be excluded.'
    )

    parser.add_argument(
        '-m', '--margin',
        type=str,
        help='Time margin to extend the FaultLog time range (format: #s for seconds, #m for minutes). '
             'Example: "5m" adds 5 minutes before and after the FaultLog time range. '
             'Only applicable with --dir option.'
    )

    parser.add_argument(
        '-p', '--overlap',
        type=str,
        choices=['ONLY_RECENT', 'ALL'],
        default='ONLY_RECENT',
        help='Policy for handling multiple overlapping data files. '
             'ONLY_RECENT (default): use only the first overlapping file (priority: 24HR.csv, 24prev.csv, Month.csv). '
             'ALL: merge data from all overlapping files, excluding duplicate time ranges. '
             'Only applicable with --dir option.'
    )

    parser.add_argument(
        '-e', '--exclude',
        type=str,
        choices=['NONE', 'ALL'],
        default='NONE',
        help='Data exclusion policy based on fault clusters. '
             'NONE (default): include all data within FaultLog time range. '
             'ALL: exclude data outside fault cluster time ranges (with optional --margin). '
             'Only applicable with --dir option.'
    )

    parser.add_argument(
        '-f', '--fault-file',
        type=str,
        help='Optional fault data CSV file to integrate into the output. '
             'Fault data will be inserted before other data.'
    )

    parser.add_argument(
        '--no-browser',
        action='store_true',
        help='Skip opening the browser with file summary after processing'
    )

    args = parser.parse_args()

    # Validate argument combinations
    if args.dir and (args.input or args.fault_file):
        print("Error: --dir cannot be used with --input or --fault-file", file=sys.stderr)
        sys.exit(1)

    if not args.dir and not args.input:
        print("Error: Either --dir or --input must be specified", file=sys.stderr)
        sys.exit(1)

    if args.margin and not args.dir:
        print("Error: --margin can only be used with --dir option", file=sys.stderr)
        sys.exit(1)

    if args.overlap != 'ONLY_RECENT' and not args.dir:
        print("Error: --overlap can only be used with --dir option", file=sys.stderr)
        sys.exit(1)

    if args.exclude != 'NONE' and not args.dir:
        print("Error: --exclude can only be used with --dir option", file=sys.stderr)
        sys.exit(1)

    # Expand output path
    output_path = Path(args.output).expanduser()

    # Create output directory if it doesn't exist
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Directory mode
    if args.dir:
        dir_path = Path(args.dir).expanduser()

        if args.verbose:
            print("=" * 60)
            print("DIRECTORY MODE")
            print("=" * 60)

        success = process_directory_mode(dir_path, output_path, margin=args.margin, overlap_policy=args.overlap, exclude_policy=args.exclude, verbose=args.verbose)

        if success:
            if args.verbose:
                print("\n" + "=" * 60)
                print("✓ Conversion completed successfully!")
                print("=" * 60)

            # Collect input files for display
            input_files = []
            for data_file in ['24HR.csv', '24prev.csv', 'Month.csv']:
                file_path = dir_path / data_file
                if file_path.exists():
                    input_files.append(file_path)

            fault_file = dir_path / 'FaultLog.csv'
            if not fault_file.exists():
                fault_file = None

            # Start web server unless --no-browser is specified
            if not args.no_browser:
                # Create plot HTML if output file exists
                if args.verbose:
                    print("\nGenerating data visualization...")
                plot_html = create_plot_html(output_path)
                if plot_html and args.verbose:
                    print("  ✓ Plot created successfully")
                elif args.verbose:
                    print("  Note: Plot generation skipped (dependencies may not be installed)")

                start_web_server(input_files, output_path, fault_file=fault_file, plot_html=plot_html, port=5000)

            sys.exit(0)
        else:
            sys.exit(1)

    # File mode
    else:
        input_path = Path(args.input).expanduser()

        fault_path = None
        if args.fault_file:
            fault_path = Path(args.fault_file).expanduser()

        # Validate input file exists
        if not input_path.exists():
            print(f"Error: Input file not found: {input_path}", file=sys.stderr)
            sys.exit(1)

        # Validate fault file exists if provided
        if fault_path and not fault_path.exists():
            print(f"Error: Fault file not found: {fault_path}", file=sys.stderr)
            sys.exit(1)

        if args.verbose:
            print(f"Converting: {input_path}")
            print(f"Output to: {output_path}")
            if fault_path:
                print(f"Including fault data from: {fault_path}")
            if args.min_time:
                print(f"Filtering: excluding data before {args.min_time}")
            if args.max_time:
                print(f"Filtering: excluding data after {args.max_time}")

        try:
            convert_csv(input_path, output_path,
                       min_time=getattr(args, 'min_time', None),
                       max_time=getattr(args, 'max_time', None),
                       fault_file=fault_path)
            if args.verbose:
                print("Conversion completed successfully!")

            # Start web server unless --no-browser is specified
            if not args.no_browser:
                # Create plot HTML if output file exists
                if args.verbose:
                    print("\nGenerating data visualization...")
                plot_html = create_plot_html(output_path)
                if plot_html and args.verbose:
                    print("  ✓ Plot created successfully")
                elif args.verbose:
                    print("  Note: Plot generation skipped (dependencies may not be installed)")

                start_web_server([input_path], output_path, fault_file=fault_path, plot_html=plot_html, port=5000)

        except Exception as e:
            print(f"Error during conversion: {e}", file=sys.stderr)
            sys.exit(1)


if __name__ == '__main__':
    main()
