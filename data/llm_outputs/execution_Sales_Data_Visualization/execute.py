#!/usr/bin/env python3
# execute.py
# This script processes sales data and generates visualizations as specified

import pandas as pd
import matplotlib.pyplot as plt
import os

# Get script directory for relative paths
script_dir = os.path.dirname(os.path.abspath(__file__))
from matplotlib.ticker import FuncFormatter

# Ensure output directory exists
os.makedirs(os.path.join(script_dir, 'output'), exist_ok=True)

# ====================
# Step 1: Load Data
# ====================
input_file = os.path.abspath(os.path.join(script_dir, '../../synthetic/ad_001_sales_viz', 'sales_data.csv'))

try:
    df = pd.read_csv(input_file)
    print(f"Successfully loaded {len(df)} rows from {input_file}")
except Exception as e:
    raise Exception(f"Failed to load data: {e}")

# ====================
# Step 2: Data Validation
# ====================
# Check for missing values
missing_values = df.isnull().sum()
if missing_values.any():
    print(f"Warning: Missing values detected:\n{missing_values[missing_values > 0]}")
    # Fill missing revenue with 0 (assuming no revenue = no sales)
    df['revenue'] = df['revenue'].fillna(0)

# Ensure revenue is numeric
df['revenue'] = pd.to_numeric(df['revenue'], errors='coerce')

# ====================
# Step 3: Aggregate Data by Product
# ====================
# Sum revenue by product_name
revenue_by_product = df.groupby('product_name')['revenue'].sum().sort_values(ascending=False)

# Verify all products are represented
expected_products = ['Wireless Mouse', 'USB-C Hub', 'Desk Lamp', 'Ergonomic Keyboard', 'Monitor Stand', 'Webcam HD', 'Cable Organizer', 'Laptop Stand', 'Wireless Charger']
actual_products = revenue_by_product.index.tolist()

# Check if all expected products are present
missing_products = set(expected_products) - set(actual_products)
if missing_products:
    print(f"Warning: The following products are missing from the data: {missing_products}")

# ====================
# Step 4: Create Pie Chart
# ====================
plt.figure(figsize=(10, 8))
plt.pie(revenue_by_product, labels=revenue_by_product.index, autopct='%1.1f%%', startangle=90)
plt.title('Revenue Distribution by Product', fontsize=16, pad=20)
plt.axis('equal')  # Equal aspect ratio ensures that pie is drawn as a circle
plt.tight_layout()

# Save pie chart
pie_output_file = os.path.join(script_dir, 'output', 'revenue_by_product_pie.png')
plt.savefig(pie_output_file, dpi=300, bbox_inches='tight')
plt.close()

# Verify pie chart sums to total revenue
total_revenue = df['revenue'].sum()
pie_sum = revenue_by_product.sum()
if abs(total_revenue - pie_sum) > 1e-6:  # Allow small floating point differences
    print(f"Warning: Pie chart sum ({pie_sum:.2f}) does not match total revenue ({total_revenue:.2f})")
else:
    print(f"Pie chart sum matches total revenue: {pie_sum:.2f}")

# ====================
# Step 5: Create Bar Chart
# ====================
plt.figure(figsize=(12, 8))
ax = revenue_by_product.plot(kind='bar', color='skyblue', edgecolor='black')
plt.title('Revenue by Individual Products', fontsize=16, pad=20)
plt.xlabel('Product', fontsize=14)
plt.ylabel('Revenue ($)', fontsize=14)

# Format y-axis to show dollar signs
ax.yaxis.set_major_formatter(FuncFormatter(lambda x, p: f'${x:,.0f}'))

# Add value labels on top of bars
for i, v in enumerate(revenue_by_product):
    ax.text(i, v + 100, f'${v:,.0f}', ha='center', va='bottom', fontsize=10)

plt.xticks(rotation=45, ha='right')
plt.tight_layout()

# Save bar chart
bar_output_file = os.path.join(script_dir, 'output', 'revenue_by_product_bar.png')
plt.savefig(bar_output_file, dpi=300, bbox_inches='tight')
plt.close()

# Verify bar chart values match aggregations
bar_sum = revenue_by_product.sum()
if abs(total_revenue - bar_sum) > 1e-6:  # Allow small floating point differences
    print(f"Warning: Bar chart sum ({bar_sum:.2f}) does not match total revenue ({total_revenue:.2f})")
else:
    print(f"Bar chart sum matches total revenue: {bar_sum:.2f}")

# ====================
# Step 6: Final Verification
# ====================
print(f"\n=== Final Verification ===")
print(f"Total revenue from raw data: ${total_revenue:,.2f}")
print(f"Revenue sum from product aggregation: ${revenue_by_product.sum():,.2f}")
print(f"Number of products in visualization: {len(revenue_by_product)}")
print(f"All products represented: {len(revenue_by_product) == len(expected_products)}")
print(f"\nAll deliverables created successfully:")
print(f"- Pie chart: {pie_output_file}")
print(f"- Bar chart: {bar_output_file}")

# Optional: Save aggregated data for audit
revenue_by_product.to_csv(os.path.join(script_dir, 'output', 'revenue_by_product_summary.csv'))
print(f"Aggregated data saved to output/revenue_by_product_summary.csv")