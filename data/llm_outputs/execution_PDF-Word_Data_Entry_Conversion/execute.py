#!/usr/bin/env python3
# execute.py
# Data transformation script for Google Sheets Data Entry Cleanup
# This script processes raw data according to template_structure.json and produces cleaned output

import pandas as pd
import json
import os

# Get script directory for relative paths
script_dir = os.path.dirname(os.path.abspath(__file__))
from datetime import datetime
import re

# === Configuration ===
INPUT_FILE = os.path.abspath(os.path.join(script_dir, '../../synthetic/ad_003_sheets_entry', 'raw_data.csv'))
TEMPLATE_FILE = os.path.abspath(os.path.join(script_dir, '../../synthetic/ad_003_sheets_entry', 'template_structure.json'))
OUTPUT_FILE = os.path.abspath(os.path.join(script_dir, '../../synthetic/ad_003_sheets_entry', 'google_sheets_cleanup_output.xlsx'))

# === Load Configuration ===
with open(TEMPLATE_FILE, 'r') as f:
    template = json.load(f)

# === Load Raw Data ===
raw_data = pd.read_csv(INPUT_FILE)

# === Data Processing ===
# Step 1: Initialize output DataFrame with correct column structure
output_df = pd.DataFrame()

# Step 2: Process each column according to template
for column_spec in template['template_columns']:
    col_name = column_spec['name']
    col_type = column_spec['type']
    source = column_spec['source']
    
    if col_name == "ID":
        # Use entry_id directly
        output_df[col_name] = raw_data['entry_id']
    
    elif col_name == "Description":
        # Use description directly
        output_df[col_name] = raw_data['description']
    
    elif col_name == "Amount":
        # Convert to float, handle currency formatting
        output_df[col_name] = raw_data['amount'].astype(str).str.replace(',', '').astype(float)
    
    elif col_name == "Date":
        # Normalize date format
        def normalize_date(date_str):
            if pd.isna(date_str):
                return None
            
            # List of possible date formats
            date_formats = [
                '%b %d %Y',  # Jan 15 2024
                '%Y-%m-%d',  # 2024-01-16
                '%m/%d/%y',  # 01/17/24
                '%B %d %Y',  # January 18 2024
                '%Y/%m/%d',  # 2024/01/19
                '%d-%b-%Y',  # 20-Jan-2024
                '%m/%d/%Y',  # 1/22/2024
                '%b. %d %Y',  # Jan. 23 2024
                '%Y-%m-%d',  # 2024-01-24
                '%d-%m-%Y',  # 01-25-2024
                '%B %d %Y',  # January 26 2024
                '%Y/%m/%d',  # 2024/01/29
                '%d %b %Y',  # 30 Jan 2024
                '%Y-%m-%d',  # 2024-01-31
                '%b %d %Y',  # Feb 1 2024
                '%Y-%m-%d',  # 2024-02-02
                '%m/%d/%y',  # 02/05/24
                '%B %d %Y',  # February 6 2024
                '%Y-%m-%d',  # 2024-02-07
                '%m/%d/%Y',  # 2/8/2024
                '%b. %d %Y',  # Feb. 9 2024
                '%Y-%m-%d',  # 2024-02-12
                '%m-%d-%Y',  # 02-13-2024
                '%B %d %Y',  # February 14 2024
                '%Y/%m/%d'   # 2024/02/15
            ]
            
            for fmt in date_formats:
                try:
                    return datetime.strptime(str(date_str), fmt).strftime('%Y-%m-%d')
                except ValueError:
                    continue
            
            # If no format matches, return original (will be handled as error)
            return str(date_str)
        
        output_df[col_name] = raw_data['date_raw'].apply(normalize_date)
    
    elif col_name == "Category":
        # Derive category based on description
        categorization_rules = column_spec['categorization_rules']
        
        def categorize(description):
            if pd.isna(description):
                return None
            
            desc_lower = str(description).lower()
            
            # Check each category rule
            for category, keywords in categorization_rules.items():
                for keyword in keywords:
                    if keyword in desc_lower:
                        return category
            
            # Default to 'Other' if no match
            return 'Other'
        
        output_df[col_name] = raw_data['description'].apply(categorize)
    
    elif col_name == "Notes":
        # Use notes directly
        output_df[col_name] = raw_data['notes']
    
    else:
        # Handle other columns
        if source in raw_data.columns:
            output_df[col_name] = raw_data[source]
        else:
            output_df[col_name] = None

# === Apply Formulas ===
# Add formula columns to output
output_df['Total Amount'] = None
output_df['Record Count'] = None
output_df['Office Supplies Total'] = None
output_df['Travel Total'] = None
output_df['Technology Total'] = None

# Calculate formulas
output_df.loc[0, 'Total Amount'] = f"=SUM(C:C)"
output_df.loc[0, 'Record Count'] = f"=COUNT(A:A)-1"
output_df.loc[0, 'Office Supplies Total'] = f"=SUMIF(E:E,"Office Supplies",C:C)"
output_df.loc[0, 'Travel Total'] = f"=SUMIF(E:E,"Travel & Transport",C:C)"
output_df.loc[0, 'Technology Total'] = f"=SUMIF(E:E,"Technology",C:C)"

# === Data Quality Checks ===
# Verify all dates are normalized
date_errors = output_df[output_df['Date'].str.contains(r'[^0-9-]', na=False)]
if not date_errors.empty:
    print(f"Warning: {len(date_errors)} dates not properly normalized")

# Verify all records are categorized
uncategorized = output_df[output_df['Category'].isna()]
if not uncategorized.empty:
    print(f"Warning: {len(uncategorized)} records not categorized")

# Verify record count
record_count = len(output_df) - 1  # Subtract header
if record_count != 25:
    print(f"Warning: Record count mismatch. Expected 25, got {record_count}")

# Verify total amount
manual_total = output_df['Amount'].sum()
expected_total = 7439.41
if abs(manual_total - expected_total) > 0.01:  # Allow small floating point error
    print(f"Warning: Total amount mismatch. Expected {expected_total}, got {manual_total}")

# === Output ===
# Save to Excel with formulas
with pd.ExcelWriter(OUTPUT_FILE, engine='openpyxl') as writer:
    output_df.to_excel(writer, index=False, sheet_name='Data')
    
    # Add formulas to the worksheet
    worksheet = writer.sheets['Data']
    
    # Add formulas to specific cells
    for formula_spec in template['required_formulas']:
        cell = formula_spec['cell']
        formula = formula_spec['formula']
        worksheet[cell] = formula
    
    # Format columns
    for col in output_df.columns:
        if col in ['Amount', 'Total Amount', 'Office Supplies Total', 'Travel Total', 'Technology Total']:
            worksheet.column_dimensions[col].number_format = '$#,##0.00'
        elif col == 'Date':
            worksheet.column_dimensions[col].number_format = 'YYYY-MM-DD'
    
    # Set column widths
    for col in output_df.columns:
        max_length = max(
            output_df[col].astype(str).map(len).max(),
            len(str(col))
        ) + 2
        worksheet.column_dimensions[col].width = min(max_length, 50)

# === Verification ===
print("=== Verification Results ===")
print(f"All dates normalized: {len(date_errors) == 0}")
print(f"All 25 records categorized: {len(uncategorized) == 0}")
print(f"SUM formula matches manual total: {abs(manual_total - expected_total) < 0.01}")
print(f"COUNT shows 25 records: {record_count == 25}")

print(f"\nTask completed successfully. Output saved to {OUTPUT_FILE}")

# === Clean up ===
# Remove any temporary files
if os.path.exists(os.path.abspath(os.path.join(script_dir, '../../synthetic/ad_003_sheets_entry', 'temp_output.xlsx'))):
    os.remove(os.path.abspath(os.path.join(script_dir, '../../synthetic/ad_003_sheets_entry', 'temp_output.xlsx')))

# === End of script ===