# Approach

1. Load the CSV data using pandas with proper encoding handling
2. Validate data integrity by checking for missing values and ensuring revenue is numeric
3. Aggregate revenue by product_name using groupby and sum operations
4. Create a pie chart showing revenue distribution by product
5. Create a bar chart showing revenue for each individual product
6. Verify that the pie chart sum matches the total revenue, all products are represented, and labels are readable
7. Save both charts in high-resolution PNG format

The approach ensures data integrity by validating the data, handling missing values, and verifying the results against the requirements.
