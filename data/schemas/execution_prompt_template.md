# Execution Prompt Template

This template guides the structure of prompts passed to the downstream Task Executor agent. The prompt should be detailed enough that the executor can complete the task without additional context.

---

## Template Structure

```markdown
# Role Assignment

You are a {{primary_skill}} expert freelancer. You have deep expertise in:
- {{Tool/skill 1}}
- {{Tool/skill 2}}
- {{Domain knowledge area}}

Your work is characterized by attention to detail, clean outputs, and adherence to specifications.

# Project Brief

**Client Request**: {{title}}

**Context**: {{description - summarized if long}}

## Requirements

1. {{Requirement 1 - specific and actionable}}
2. {{Requirement 2}}
3. {{Requirement 3}}
...

## Deliverables

1. **{{Deliverable 1}}**: {{format, e.g., "CSV file"}} - {{specific details}}
2. **{{Deliverable 2}}**: {{format}} - {{specific details}}
...

## Constraints

- {{Constraint 1: from not_included or explicit limitations}}
- {{Constraint 2: deadline if mentioned}}
- {{Constraint 3: technical constraints like "no external libraries"}}

## Input Data

{{Description of what data/files the executor will receive}}
- File: {{filename}} - {{description}}
- Format: {{format details}}

## Success Criteria

The task is complete when:
- [ ] {{Criterion 1: specific, verifiable}}
- [ ] {{Criterion 2}}
- [ ] {{Criterion 3}}

## Execution Notes

- **Output format**: {{specific format requirements}}
- **Naming convention**: {{file naming if relevant}}
- **Quality bar**: {{what "good" looks like}}
- **Edge cases**: {{how to handle ambiguity}}
- **If blocked**: {{what to do if stuck}}

## Artifacts (REQUIRED)

You MUST save all artifacts that document how deliverables were produced:

1. **execute.py**: A standalone Python script that:
   - Reproduces all deliverables when run
   - Contains all transformation logic
   - Includes inline comments explaining key steps
   - Verifies success criteria at the end

2. **All intermediate data**: Raw data fetched from APIs, intermediate processing results

3. **Naming convention**:
   - `execute.py` - main execution script
   - `input.*` - input files
   - `*_cleaned.*`, `*_output.*` - output deliverables
   - `raw_*.json` - raw data from external sources

The client must be able to:
- Re-run `python execute.py` to reproduce results
- Audit exactly how outputs were generated
- Modify parameters and re-execute

## Example Output

{{If helpful, show a small example of expected output format}}
```

---

## Guidelines for Execution Prompts

### Role Assignment
- Be specific about the expertise area
- List 2-4 relevant tools/skills
- Set the right mindset for the task

### Requirements
- Number them for easy reference
- Make each one atomic and actionable
- Use imperative voice ("Add X", "Remove Y", not "X should be added")

### Deliverables
- Specify exact file formats
- Include naming conventions if relevant
- Be explicit about what "done" looks like

### Constraints
- Include everything from "out of scope"
- Add inferred constraints (budget implies no gold-plating)
- Mention deadline/time expectations

### Success Criteria
- Make them checkable (yes/no)
- Cover all deliverables
- Include quality dimensions (accuracy, formatting)

### Artifacts
- ALWAYS require execute.py that reproduces deliverables
- Preserve all input data
- Save intermediate data from external APIs
- Client must be able to audit and re-run

---

## Example Execution Prompt

```markdown
# Role Assignment

You are a data transformation specialist with deep expertise in:
- CSV/Excel file manipulation
- Python pandas for data processing
- Text manipulation and string operations

Your work is characterized by clean, error-free outputs and careful attention to data integrity.

# Project Brief

**Client Request**: Excel Sheet Modification

**Context**: Client has a CSV with Column A plus 3-5 additional columns. They need Column A values prefixed with @, duplicates removed, and the entire sheet sorted by Column A text length.

## Requirements

1. Add "@" prefix to every value in Column A
2. Remove duplicate rows (check after adding prefix)
3. Sort all rows by Column A text length, shortest first
4. Preserve alignment of all columns with their rows during sort
5. Preserve special characters in all columns

## Deliverables

1. **Cleaned CSV**: Same structure as input, with transformations applied
   - Format: CSV
   - Naming: `[original_name]_cleaned.csv`

## Constraints

- Do not modify any columns other than adding @ to Column A
- Do not change the order of columns
- Preserve all special characters exactly as they appear
- Fast turnaround expected (client mentioned "less than a day")

## Input Data

- File: Client-provided CSV
- Format: CSV with Column A + 3-5 additional columns
- Note: File not yet attached by client at time of proposal

## Success Criteria

The task is complete when:
- [ ] All Column A values start with "@"
- [ ] No duplicate rows exist in the output
- [ ] Rows are sorted by Column A length (ascending)
- [ ] All original columns present and aligned
- [ ] Special characters preserved unchanged
- [ ] Output is valid CSV

## Execution Notes

- **Output format**: CSV (UTF-8 encoding to preserve special chars)
- **Duplicate detection**: Based on entire row, not just Column A
- **Sort stability**: If two rows have same Column A length, preserve original order
- **Quality bar**: Zero data loss, zero misalignment
- **If blocked**: If file has unexpected structure, document assumptions made

## Artifacts (REQUIRED)

Save these files in the output directory:

1. **execute.py**: Standalone script that reproduces the transformation
   - Load input.csv
   - Apply all transformations
   - Verify success criteria
   - Export cleaned output

2. **input.csv**: Original input file (preserved)

3. **input_cleaned.csv**: Final deliverable
```

---

## Skill/Role Mappings

| Task Category | Role Assignment |
|--------------|-----------------|
| Data entry/transformation | Data transformation specialist |
| Spreadsheet work | Excel/Sheets specialist |
| Data visualization | Data visualization expert |
| Database work | Database developer |
| Web scraping | Web scraping specialist |
| API integration | Backend developer |
| Research/analysis | Research analyst |
| Document creation | Technical writer |
| Code generation | Software developer |
| Full-stack | Full-stack developer |
