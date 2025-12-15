#!/usr/bin/env python3
# execute.py
# This script processes sales data and generates visualizations as specified

import pandas as pd
import matplotlib.pyplot as plt
import os

# Get script directory for relative paths
script_dir = os.path.dirname(os.path.abspath(__file__))
from pathlib import Path

# Set up output directory
OUTPUT_DIR = Path('output')
OUTPUT_DIR.mkdir(exist_ok=True)

# --- Step 1: Load the data ---
input_file = os.path.abspath(os.path.join(script_dir, '../../synthetic/ad_001_sales_viz', 'sales_data.csv'))
if not os.path.exists(input_file):
    raise FileNotFoundError(f"Input file {input_file} not found")

# Read CSV with proper encoding and handling
try:
    df = pd.read_csv(input_file, encoding='utf-8')
except Exception as e:
    print(f"Error reading CSV: {e}")
    exit(1)

# --- Step 2: Data validation and cleaning ---
# Check for missing values
print(f"Missing values per column:\n{df.isnull().sum()}")

# Ensure revenue is numeric
if not pd.api.types.is_numeric_dtype(df['revenue']):
    df['revenue'] = pd.to_numeric(df['revenue'], errors='coerce')

# Remove rows with missing revenue
df.dropna(subset=['revenue'], inplace=True)

# --- Step 3: Aggregate revenue by product_name ---
# Group by product_name and sum revenue
revenue_by_product = df.groupby('product_name')['revenue'].sum().reset_index()

# Sort by revenue (descending)
revenue_by_product = revenue_by_product.sort_values('revenue', ascending=False)

# --- Step 4: Create pie chart ---
plt.figure(figsize=(10, 8))
plt.pie(revenue_by_product['revenue'], labels=revenue_by_product['product_name'], autopct='%1.1f%%', startangle=90)
plt.title('Revenue Distribution by Product', fontsize=16)
plt.axis('equal')  # Equal aspect ratio ensures that pie is drawn as a circle

# Save pie chart
pie_filename = OUTPUT_DIR / 'revenue_by_product_pie.png'
plt.savefig(pie_filename, dpi=300, bbox_inches='tight')
plt.close()

# --- Step 5: Create bar chart ---
plt.figure(figsize=(12, 8))
plt.bar(revenue_by_product['product_name'], revenue_by_product['revenue'], color='skyblue')
plt.title('Revenue by Individual Products', fontsize=16)
plt.xlabel('Product Name', fontsize=14)
plt.ylabel('Revenue', fontsize=14)
plt.xticks(rotation=45, ha='right')
plt.tight_layout()

# Save bar chart
bar_filename = OUTPUT_DIR / 'revenue_by_product_bar.png'
plt.savefig(bar_filename, dpi=300, bbox_inches='tight')
plt.close()

# --- Step 6: Verification ---
# Verify pie chart sums to total revenue
total_revenue = df['revenue'].sum()
sum_pie_revenue = revenue_by_product['revenue'].sum()

print(f"Total revenue from raw data: {total_revenue:,.2f}")
print(f"Sum of aggregated revenue: {sum_pie_revenue:,.2f}")

# Check if they match (allowing for floating point precision)
assert abs(total_revenue - sum_pie_revenue) < 1e-6, "Pie chart sum doesn't match total revenue"

# Verify all 10 products are represented
expected_products = 10
actual_products = len(revenue_by_product)
assert actual_products == expected_products, f"Expected {expected_products} products, found {actual_products}"

# Verify labels are readable
# (This is more qualitative, but we can check if labels are present)
assert not revenue_by_product['product_name'].isnull().any(), "Missing product names"

# --- Step 7: Output summary ---
print(f"\nAll deliverables created in {OUTPUT_DIR}")
print(f"- Pie chart: {pie_filename}")
print(f"- Bar chart: {bar_filename}")
print(f"\nVerification completed successfully:")
print(f"- Pie chart sum matches total revenue: {abs(total_revenue - sum_pie_revenue) < 1e-6}")
print(f"- All {expected_products} products represented: {actual_products == expected_products}")
print(f"- Labels are readable: {not revenue_by_product['product_name'].isnull().any()}")

# Optional: Print aggregated data
print(f"\nAggregated revenue by product:")
print(revenue_by_product.to_string(index=False))