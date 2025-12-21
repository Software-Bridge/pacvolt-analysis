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



def convert_csv(input_file, output_file):
    """
    Convert wide-format CSV to long-format CSV.

    Input format:
        - First line: metadata/header (skipped)
        - Second line: column names (RecNr, ..., Time)
        - Data lines: one row per time point with multiple measurements

    Output format:
        - Columns: scet, name, value, unit
        - One row per measurement per time point
    """
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

            # Process each data row
            for row in reader:
                if not row or len(row) < len(headers):
                    continue

                time_value = row[time_col_idx]
                # Convert time offset to full SCET timestamp
                scet_timestamp = parse_time_offset_to_scet(time_value)

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
  %(prog)s -i input.csv -o output.csv
  %(prog)s --input data/24prev.csv --output data/converted.csv
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

    args = parser.parse_args()

    # Expand user paths
    input_path = Path(args.input).expanduser()
    output_path = Path(args.output).expanduser()

    # Validate input file exists
    if not input_path.exists():
        print(f"Error: Input file not found: {input_path}", file=sys.stderr)
        sys.exit(1)

    # Create output directory if it doesn't exist
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if args.verbose:
        print(f"Converting: {input_path}")
        print(f"Output to: {output_path}")

    try:
        convert_csv(input_path, output_path)
        if args.verbose:
            print("Conversion completed successfully!")
    except Exception as e:
        print(f"Error during conversion: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()
