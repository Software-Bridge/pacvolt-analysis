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
from pathlib import Path
from datetime import datetime, timedelta


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

    with open(fault_file, 'r') as f:
        reader = csv.reader(f)

        # Skip first line (metadata)
        next(reader)

        # Skip second line (column headers)
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

            except (ValueError, IndexError) as e:
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
    with open(input_file, 'r') as infile:
        reader = csv.reader(infile)

        # Skip first line (metadata/header)
        next(reader)

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

        # Open output file
        with open(output_file, 'w', newline='') as outfile:
            writer = csv.writer(outfile)

            # Write output header
            writer.writerow(['scet', 'name', 'value', 'unit'])

            # Write fault data first (if available)
            for fault_row in fault_data:
                writer.writerow(fault_row)

            # Process each data row
            for row in reader:
                if not row or len(row) < len(headers):
                    continue

                time_value = row[time_col_idx]
                # Convert time offset to full SCET timestamp
                scet_timestamp = parse_time_offset_to_scet(time_value)
                scet_datetime = datetime.strptime(scet_timestamp, '%Y-%jT%H:%M:%S')

                # Apply time filtering
                if min_datetime and scet_datetime < min_datetime:
                    continue
                if max_datetime and scet_datetime > max_datetime:
                    continue

                # For each data column, write an output row
                for col_idx, col_name, col_unit in data_columns:
                    value = row[col_idx]
                    writer.writerow([scet_timestamp, col_name, value, col_unit])


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
        """
    )

    parser.add_argument(
        '-i', '--input',
        required=True,
        help='Input CSV file path'
    )

    parser.add_argument(
        '-o', '--output',
        required=True,
        help='Output CSV file path'
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
        '-f', '--fault-file',
        type=str,
        help='Optional fault data CSV file to integrate into the output. '
             'Fault data will be inserted before other data.'
    )

    args = parser.parse_args()

    # Expand user paths
    input_path = Path(args.input).expanduser()
    output_path = Path(args.output).expanduser()

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

    # Create output directory if it doesn't exist
    output_path.parent.mkdir(parents=True, exist_ok=True)

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
    except Exception as e:
        print(f"Error during conversion: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()
