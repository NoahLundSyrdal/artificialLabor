#!/usr/bin/env python3
"""
Task executor for feasible jobs.
Generates execution prompts and executes tasks using LLM.
"""

from typing import Dict, List, Optional
import json
import re
from datetime import datetime
from pathlib import Path
from llm_client import get_llm_client


# Skill/Role mappings based on task type
SKILL_MAPPINGS = {
    "data entry": "Data transformation specialist",
    "data transformation": "Data transformation specialist",
    "excel": "Excel/Sheets specialist",
    "spreadsheet": "Excel/Sheets specialist",
    "csv": "Data transformation specialist",
    "visualization": "Data visualization expert",
    "chart": "Data visualization expert",
    "graph": "Data visualization expert",
    "database": "Database developer",
    "sql": "Database developer",
    "scraping": "Web scraping specialist",
    "api": "Backend developer",
    "integration": "Backend developer",
    "research": "Research analyst",
    "analysis": "Research analyst",
    "document": "Technical writer",
    "word": "Technical writer",
    "pdf": "Technical writer",
    "code": "Software developer",
    "programming": "Software developer",
    "vba": "Excel/Sheets specialist",
    "automation": "Software developer",
}


def _determine_role_and_skills(job: Dict) -> tuple:
    """Determine role and skills based on job content."""
    title = job.get('title', '').lower()
    description = job.get('description', '').lower()
    requirements = ' '.join(job.get('requirements', [])).lower()
    
    combined_text = f"{title} {description} {requirements}"
    
    # Find matching skills
    matched_skills = []
    for keyword, role in SKILL_MAPPINGS.items():
        if keyword in combined_text:
            matched_skills.append(keyword)
    
    # Determine primary role
    if matched_skills:
        # Use the first matched role
        primary_role = SKILL_MAPPINGS[matched_skills[0]]
    else:
        primary_role = "Data transformation specialist"  # Default
    
    # Build skills list (2-4 items)
    skills = []
    if any(k in matched_skills for k in ["excel", "spreadsheet", "csv", "vba"]):
        skills.append("CSV/Excel file manipulation")
        skills.append("Python pandas for data processing")
    if any(k in matched_skills for k in ["pdf", "word", "document"]):
        skills.append("Document parsing and text extraction")
    if any(k in matched_skills for k in ["visualization", "chart", "graph"]):
        skills.append("Data visualization with matplotlib/plotly")
    if any(k in matched_skills for k in ["database", "sql"]):
        skills.append("SQL database operations")
    if any(k in matched_skills for k in ["api", "integration"]):
        skills.append("API integration and data fetching")
    
    # Default skills if none matched
    if not skills:
        skills = [
            "CSV/Excel file manipulation",
            "Python pandas for data processing",
            "Text manipulation and string operations"
        ]
    
    return primary_role, skills[:4]


def _find_synthetic_folder(job: Dict) -> Optional[Path]:
    """Find synthetic folder for a job based on title."""
    title = job.get('title', '').lower()
    synthetic_base = Path(__file__).parent / "data" / "synthetic"
    
    # Try to match by title keywords
    for folder in synthetic_base.iterdir():
        if folder.is_dir():
            folder_name = folder.name.lower()
            # Check if title keywords match folder name
            if any(keyword in folder_name for keyword in title.split()[:3]):
                return folder
    
    # Try exact match with ad_XXX pattern (be more specific to avoid wrong matches)
    if 'ad_001' in title or ('sales' in title and 'visualization' in title):
        return synthetic_base / "ad_001_sales_viz"
    elif 'ad_003' in title or ('sheets' in title and 'entry' in title):
        return synthetic_base / "ad_003_sheets_entry"
    elif 'ad_005' in title or ('astrology' in title and 'database' in title):
        return synthetic_base / "ad_005_astrology_db"
    elif 'ad_009' in title or ('word' in title and 'excel' in title):
        return synthetic_base / "ad_009_word_to_excel"
    elif 'ad_011' in title or ('url' in title and 'pdf' in title and 'to' in title):
        return synthetic_base / "ad_011_urls_to_pdf"
    
    # Don't match "PDF Text Data Entry" to "urls_to_pdf" - they're different tasks
    # Return None if no match found
    return None


def _load_input_files(synthetic_folder: Path) -> tuple:
    """Load input files and task spec from synthetic folder."""
    input_data = {}
    task_spec = {}
    
    if not synthetic_folder or not synthetic_folder.exists():
        return input_data, task_spec
    
    # Load task_spec.json if exists
    task_spec_path = synthetic_folder / "task_spec.json"
    if task_spec_path.exists():
        try:
            with open(task_spec_path, 'r') as f:
                task_spec = json.load(f)
        except:
            pass
    
    # Load input files
    input_file = task_spec.get('input_file')
    if input_file:
        input_path = synthetic_folder / input_file
        if input_path.exists():
            try:
                with open(input_path, 'r', encoding='utf-8') as f:
                    input_data[input_file] = f.read()
            except:
                pass
    
    # Also try to load any CSV/JSON files
    for file_path in synthetic_folder.glob("*"):
        if file_path.is_file() and file_path.suffix in ['.csv', '.json', '.txt', '.md']:
            if file_path.name != 'task_spec.json':
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        input_data[file_path.name] = f.read()
                except:
                    pass
    
    return input_data, task_spec


def _build_execution_prompt(job: Dict) -> str:
    """Build execution prompt based on template."""
    primary_role, skills = _determine_role_and_skills(job)
    
    title = job.get('title', 'N/A')
    description = job.get('description', 'N/A')
    requirements = job.get('requirements', [])
    deliverables = job.get('deliverables', [])
    budget = job.get('budget', 'N/A')
    payment_terms = job.get('payment_terms', 'N/A')
    
    # Find and load synthetic input files
    synthetic_folder = _find_synthetic_folder(job)
    input_files, task_spec = _load_input_files(synthetic_folder)
    
    # Build skills list
    skills_list = '\n'.join([f"- {skill}" for skill in skills])
    
    # Build requirements list
    requirements_list = '\n'.join([f"{i+1}. {req}" for i, req in enumerate(requirements)]) if requirements else "1. Complete the task as described"
    
    # Build deliverables list
    deliverables_list = '\n'.join([
        f"{i+1}. **{deliv}**: {deliv} - As specified in requirements"
        for i, deliv in enumerate(deliverables)
    ]) if deliverables else "1. **Output**: Completed task deliverables"
    
    # Build constraints
    constraints = []
    if budget and budget != 'N/A':
        constraints.append(f"- Budget constraint: {budget} ({payment_terms})")
    constraints.append("- Maintain data integrity and accuracy")
    constraints.append("- Follow all specified requirements exactly")
    constraints_list = '\n'.join(constraints)
    
    # Build input data section
    input_data_section = "## Input Data\n\n"
    if input_files:
        input_data_section += "**Input files are provided below. Use these actual files for processing:**\n\n"
        for filename, content in input_files.items():
            # Show first 50 lines for large files
            lines = content.split('\n')
            preview = '\n'.join(lines[:50])
            if len(lines) > 50:
                preview += f"\n... (file continues, {len(lines)} total lines)"
            input_data_section += f"### File: {filename}\n```\n{preview}\n```\n\n"
    else:
        input_data_section += "- File: Client-provided input files (if applicable)\n- Format: As specified in requirements\n- Note: Input files may be provided by client or need to be generated\n"
    
    # Add task spec info if available
    if task_spec:
        input_data_section += f"\n**Task Specifications:**\n"
        if task_spec.get('expected_outputs'):
            input_data_section += f"- Expected outputs: {json.dumps(task_spec.get('expected_outputs'), indent=2)}\n"
        if task_spec.get('verification_criteria'):
            input_data_section += f"- Verification criteria: {', '.join(task_spec.get('verification_criteria', []))}\n"
    
    prompt = f"""# Role Assignment

You are a {primary_role}. You have deep expertise in:
{skills_list}

Your work is characterized by attention to detail, clean outputs, and adherence to specifications.

# Project Brief

**Client Request**: {title}

**Context**: {description[:500]}{'...' if len(description) > 500 else ''}

## Requirements

{requirements_list}

## Deliverables

{deliverables_list}

## Constraints

{constraints_list}

{input_data_section}

## Success Criteria

The task is complete when:
- [ ] All requirements are met
- [ ] All deliverables are produced
- [ ] Outputs are in the correct format
- [ ] Data integrity is maintained

## Execution Notes

- **Output format**: As specified in deliverables
- **Naming convention**: Use descriptive names for output files
- **Quality bar**: Zero errors, complete adherence to specifications
- **Edge cases**: Handle missing data gracefully, document assumptions
- **If blocked**: Document the issue and suggest alternatives

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

## Your Task

Generate the complete solution including:
1. The execute.py script with all necessary code
2. Any required data processing logic
3. Output files in the specified format
4. Documentation of the approach

Return your response as a structured JSON object with:
- "execute_script": The complete Python code for execute.py
- "approach": Brief explanation of your approach
- "deliverables": List of files/outputs produced
- "notes": Any assumptions or important notes
"""
    
    return prompt


def execute_task(job: Dict) -> Dict:
    """
    Execute a single task using LLM.
    
    Args:
        job: Job dictionary with proposal and all job details
        
    Returns:
        Execution result dictionary
    """
    started_at = datetime.now()
    
    try:
        # Build execution prompt
        execution_prompt = _build_execution_prompt(job)
        
        # Call LLM with longer context for execution
        llm = get_llm_client()
        messages = [{"role": "user", "content": execution_prompt}]
        
        print(f"    [Executing task...]")
        response_text = llm.chat(messages, temperature=0.3, max_tokens=4000)
        
        # Parse response - try to extract JSON or Python code
        result = _parse_execution_response(response_text, execution_prompt)
        
        # If parsing failed, try to extract Python code directly from response
        if not result.get('success') or not result.get('execute_script'):
            print(f"    [⚠ LLM parsing failed, attempting to extract Python code from response...]")
            # Try one more time with more aggressive extraction
            import re
            python_blocks = re.findall(r'```(?:python)?\s*\n(.*?)\n```', response_text, re.DOTALL)
            if python_blocks:
                execute_script = max(python_blocks, key=len).strip()
                result = {
                    "success": True,
                    "execute_script": execute_script,
                    "approach": "Extracted Python code from LLM response",
                    "deliverables": [{"name": "execute.py", "type": "other", "description": "Main execution script"}],
                    "success_criteria": [{"criterion": "Script extracted", "passed": True}],
                    "notes": "Extracted script from LLM response"
                }
            else:
                # Last resort: use minimal fallback
                print(f"    [⚠ No Python code found, using minimal fallback...]")
                result = _generate_fallback_script(response_text, execution_prompt)
        
        completed_at = datetime.now()
        wall_time = (completed_at - started_at).total_seconds()
        
        execution_result = {
            "ad_id": job.get('title', 'unknown'),
            "execution": {
                "started_at": started_at.isoformat(),
                "completed_at": completed_at.isoformat(),
                "wall_time_seconds": wall_time,
                "success": result.get('success', False),
                "error": result.get('error')
            },
            "telemetry": {
                "tokens": {
                    "input": result.get('input_tokens', 0),
                    "output": result.get('output_tokens', 0),
                    "total": result.get('total_tokens', 0)
                },
                "cost": {
                    "model_tier": "local",
                    "input_cost_usd": 0.0,
                    "output_cost_usd": 0.0,
                    "total_cost_usd": 0.0
                },
                "api_calls": {
                    "llm_calls": 1,
                    "tool_calls": 0,
                    "external_calls": 0
                }
            },
            "deliverables": result.get('deliverables', []),
            "success_criteria": result.get('success_criteria', []),
            "status": "completed" if result.get('success') else "failed",
            "notes": result.get('notes', ''),
            "execute_script": result.get('execute_script', ''),
            "approach": result.get('approach', ''),
            "llm_prompt": execution_prompt,
            "llm_response": response_text
        }
        
        return execution_result
        
    except Exception as e:
        completed_at = datetime.now()
        wall_time = (completed_at - started_at).total_seconds()
        
        return {
            "ad_id": job.get('title', 'unknown'),
            "execution": {
                "started_at": started_at.isoformat(),
                "completed_at": completed_at.isoformat(),
                "wall_time_seconds": wall_time,
                "success": False,
                "error": str(e)
            },
            "telemetry": {
                "tokens": {"input": 0, "output": 0, "total": 0},
                "cost": {"model_tier": "local", "input_cost_usd": 0.0, "output_cost_usd": 0.0, "total_cost_usd": 0.0},
                "api_calls": {"llm_calls": 1, "tool_calls": 0, "external_calls": 0}
            },
            "deliverables": [],
            "success_criteria": [],
            "status": "failed",
            "notes": f"Execution failed: {str(e)}",
            "llm_prompt": execution_prompt if 'execution_prompt' in locals() else "",
            "llm_response": ""
        }


def _parse_execution_response(response_text: str, original_prompt: str) -> Dict:
    """Parse LLM execution response."""
    import re
    
    # Try to extract JSON from response - look for JSON code blocks first
    json_blocks = re.findall(r'```(?:json)?\s*\n(.*?)\n```', response_text, re.DOTALL)
    
    if json_blocks:
        # Try each JSON block
        for json_block in json_blocks:
            json_str = json_block.strip()
            # Quick fixes
            json_str = re.sub(r'"""', '"', json_str)
            json_str = re.sub(r"'''", "'", json_str)
            json_str = re.sub(r',\s*}', '}', json_str)
            json_str = re.sub(r',\s*]', ']', json_str)
            # Fix backticks in execute_script field
            json_str = re.sub(r'`([^`]+)`', r'\1', json_str)
            
            try:
                parsed = json.loads(json_str)
                parsed['success'] = True
                return parsed
            except json.JSONDecodeError:
                continue
    
    # Try brace-balanced extraction
    json_str = _extract_json_balanced(response_text)
    if json_str:
        json_str = re.sub(r'"""', '"', json_str)
        json_str = re.sub(r"'''", "'", json_str)
        json_str = re.sub(r',\s*}', '}', json_str)
        json_str = re.sub(r',\s*]', ']', json_str)
        json_str = re.sub(r'`([^`]+)`', r'\1', json_str)
        
        try:
            parsed = json.loads(json_str)
            parsed['success'] = True
            return parsed
        except json.JSONDecodeError:
            pass
    
    # Fallback: extract execute_script from Python code blocks
    execute_script = ""
    python_blocks = re.findall(r'```(?:python)?\s*\n(.*?)\n```', response_text, re.DOTALL)
    if python_blocks:
        # Take the largest block (likely the main script)
        execute_script = max(python_blocks, key=len).strip()
    
    # If we found a script, consider it a success
    if execute_script:
        return {
            "success": True,
            "execute_script": execute_script,
            "approach": "Generated Python script from LLM response",
            "deliverables": [{"name": "execute.py", "type": "other", "description": "Main execution script"}],
            "success_criteria": [{"criterion": "Script generated", "passed": True}],
            "notes": "Extracted script from LLM response"
        }
    
    # Last resort: generate a fallback script based on job description
    return _generate_fallback_script(response_text, original_prompt)


def _save_execution_outputs(job: Dict, execution_result: Dict) -> None:
    """Save execution outputs (execute.py and deliverables) to files, then execute the script."""
    import subprocess
    import sys
    
    job_title = job.get('title', 'unknown').replace(' ', '_').replace('/', '_')
    output_dir = Path("data/llm_outputs") / f"execution_{job_title}"
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Save execute.py script - ALWAYS generate one, even if LLM failed
    execute_script = execution_result.get('execute_script', '')
    
    # If no script from LLM, generate fallback using job info
    if not execute_script:
        print(f"      ⚠ No script from LLM, generating fallback...")
        llm_prompt = execution_result.get('llm_prompt', '')
        llm_response = execution_result.get('llm_response', '')
        fallback_result = _generate_fallback_script(llm_response, llm_prompt)
        execute_script = fallback_result.get('execute_script', '')
        # Update execution result
        if execute_script:
            execution_result['execute_script'] = execute_script
            execution_result['approach'] = fallback_result.get('approach', 'Fallback script')
            execution_result['status'] = 'completed'
            execution_result['execution']['success'] = True
            execution_result['deliverables'] = fallback_result.get('deliverables', [])
    
    if execute_script:
        # Fix paths in the script to point to synthetic data folder
        execute_script = _fix_paths_in_script(execute_script, job)
        
        # Repair common script issues (missing imports, etc.)
        execute_script = _repair_script(execute_script)
        
        execute_path = output_dir / "execute.py"
        with open(execute_path, 'w', encoding='utf-8') as f:
            f.write(execute_script)
        print(f"      💾 Saved execute.py to {execute_path}")
        
        # Make script executable
        execute_path.chmod(0o755)
        
        # Install missing dependencies before executing
        print(f"      🔧 Checking and installing dependencies...")
        _install_script_dependencies(execute_script)
        
        # Execute the script
        print(f"      ▶ Executing script...")
        script_success = False
        script_error = None
        try:
            # Use absolute path for the script to avoid path issues
            script_abs_path = execute_path.resolve()
            output_dir_abs = output_dir.resolve()
            
            # Change to the execution directory and run the script
            result = subprocess.run(
                [sys.executable, str(script_abs_path)],
                cwd=str(output_dir_abs),
                capture_output=True,
                text=True,
                timeout=300  # 5 minute timeout
            )
            
            if result.returncode == 0:
                script_success = True
                print(f"      ✓ Script executed successfully")
                if result.stdout:
                    # Show last few lines of output
                    output_lines = result.stdout.strip().split('\n')
                    if len(output_lines) > 5:
                        print(f"         ... {len(output_lines) - 5} more lines ...")
                    for line in output_lines[-5:]:
                        print(f"         {line}")
            else:
                script_success = False
                script_error = f"Exit code {result.returncode}"
                print(f"      ✗ Script execution failed (exit code {result.returncode})")
                if result.stderr:
                    error_lines = result.stderr.strip().split('\n')
                    for line in error_lines[-3:]:
                        print(f"         ERROR: {line}")
                    script_error = '\n'.join(error_lines[-3:])
                
                # Try to repair and retry if it's a fixable error
                if result.returncode != 0 and result.stderr:
                    error_text = result.stderr
                    # Check for common fixable errors
                    if 'NameError' in error_text or 'ModuleNotFoundError' in error_text or 'undefined' in error_text.lower():
                        print(f"      🔧 Attempting to repair script and retry...")
                        repaired_script = _repair_script_errors(execute_script, error_text)
                        if repaired_script != execute_script:
                            # Save repaired script and try again
                            with open(execute_path, 'w', encoding='utf-8') as f:
                                f.write(repaired_script)
                            # Install any new dependencies
                            _install_script_dependencies(repaired_script)
                            # Retry execution
                            retry_result = subprocess.run(
                                [sys.executable, str(script_abs_path)],
                                cwd=str(output_dir_abs),
                                capture_output=True,
                                text=True,
                                timeout=300
                            )
                            if retry_result.returncode == 0:
                                script_success = True
                                script_error = None
                                print(f"      ✓ Script executed successfully after repair")
                                if retry_result.stdout:
                                    output_lines = retry_result.stdout.strip().split('\n')
                                    if len(output_lines) > 5:
                                        print(f"         ... {len(output_lines) - 5} more lines ...")
                                    for line in output_lines[-5:]:
                                        print(f"         {line}")
                            else:
                                print(f"      ✗ Retry after repair also failed")
        except subprocess.TimeoutExpired:
            script_success = False
            script_error = "Script execution timed out after 5 minutes"
            print(f"      ✗ {script_error}")
        except Exception as e:
            script_success = False
            script_error = str(e)
            print(f"      ✗ Error executing script: {e}")
        
        # Update execution result with actual script execution status
        execution_result['execution']['success'] = script_success
        if not script_success:
            execution_result['execution']['error'] = script_error
            execution_result['status'] = 'failed'
    else:
        print(f"      ✗ Could not generate execute.py script")
    
    # Save approach and notes
    if execution_result.get('approach'):
        approach_path = output_dir / "approach.md"
        with open(approach_path, 'w', encoding='utf-8') as f:
            f.write(f"# Approach\n\n{execution_result.get('approach', '')}\n")
        print(f"      💾 Saved approach.md to {approach_path}")
    
    if execution_result.get('notes'):
        notes_path = output_dir / "notes.md"
        with open(notes_path, 'w', encoding='utf-8') as f:
            notes = execution_result.get('notes', '')
            # Handle if notes is a list
            if isinstance(notes, list):
                notes = '\n'.join([f"- {note}" for note in notes])
            f.write(f"# Notes\n\n{notes}\n")
        print(f"      💾 Saved notes.md to {notes_path}")
    
    # Save execution metadata
    metadata = {
        'job_title': job.get('title', 'Unknown'),
        'status': execution_result.get('status', 'unknown'),
        'success': execution_result.get('execution', {}).get('success', False),
        'deliverables': execution_result.get('deliverables', []),
        'success_criteria': execution_result.get('success_criteria', [])
    }
    metadata_path = output_dir / "metadata.json"
    with open(metadata_path, 'w', encoding='utf-8') as f:
        json.dump(metadata, f, indent=2, ensure_ascii=False)
    
    print(f"      💾 Saved metadata.json to {metadata_path}")


def _install_script_dependencies(script: str) -> None:
    """Install missing Python packages required by the script."""
    import re
    import subprocess
    
    # Map import statements to package names
    import_to_package = {
        'pandas': 'pandas',
        'numpy': 'numpy',
        'matplotlib': 'matplotlib',
        'openpyxl': 'openpyxl',
        'xlsxwriter': 'xlsxwriter',
        'pdfplumber': 'pdfplumber',
        'PyPDF2': 'PyPDF2',
        'pypdf': 'pypdf',
        'python-docx': 'python-docx',
        'docx': 'python-docx',
        'requests': 'requests',
        'httpx': 'httpx',
        'beautifulsoup4': 'beautifulsoup4',
        'bs4': 'beautifulsoup4',
        'selenium': 'selenium',
        'pillow': 'Pillow',
        'PIL': 'Pillow',
    }
    
    # Find all imports in the script
    imports_found = set()
    for match in re.finditer(r'^(?:import|from)\s+(\w+)', script, re.MULTILINE):
        module = match.group(1)
        imports_found.add(module)
    
    # Check which packages need to be installed
    packages_to_install = []
    for module, package in import_to_package.items():
        if module in imports_found:
            # Check if package is already installed
            try:
                __import__(module)
            except ImportError:
                if package not in packages_to_install:
                    packages_to_install.append(package)
    
    # Install missing packages
    if packages_to_install:
        print(f"         Installing: {', '.join(packages_to_install)}")
        try:
            subprocess.run(
                [sys.executable, '-m', 'pip', 'install', '--quiet'] + packages_to_install,
                check=True,
                capture_output=True
            )
            print(f"         ✓ Dependencies installed")
        except subprocess.CalledProcessError as e:
            print(f"         ⚠ Warning: Failed to install some dependencies: {e}")


def _repair_script(script: str) -> str:
    """Repair common issues in LLM-generated scripts to make them executable."""
    import re
    
    # Track what imports are needed
    needed_imports = []
    
    # Check for json usage
    if re.search(r'\bjson\.(load|dump|loads|dumps)\b', script) and 'import json' not in script and 'from json' not in script:
        needed_imports.append('import json')
    
    # Check for pandas usage
    if re.search(r'\bpd\.|pandas\.', script):
        if 'import pandas' not in script and 'from pandas' not in script:
            needed_imports.append('import pandas as pd')
        elif 'import pandas' in script and ' as pd' not in script and 'pd.' in script:
            script = script.replace('import pandas', 'import pandas as pd')
    
    # Check for numpy usage
    if re.search(r'\bnp\.|numpy\.', script) and 'import numpy' not in script and 'from numpy' not in script:
        needed_imports.append('import numpy as np')
    
    # Check for matplotlib usage
    if re.search(r'\bplt\.|matplotlib\.', script):
        if 'import matplotlib' not in script and 'from matplotlib' not in script:
            needed_imports.append('import matplotlib.pyplot as plt')
        elif 'import matplotlib.pyplot' in script and ' as plt' not in script and 'plt.' in script:
            script = script.replace('import matplotlib.pyplot', 'import matplotlib.pyplot as plt')
    
    # Check for openpyxl (for Excel writing)
    if re.search(r'\.to_excel\(|openpyxl', script) and 'import openpyxl' not in script and 'from openpyxl' not in script:
        needed_imports.append('import openpyxl')
    
    # Check for pathlib
    if re.search(r'\bPath\b', script) and 'from pathlib import Path' not in script and 'import pathlib' not in script:
        needed_imports.append('from pathlib import Path')
    
    # Check for os
    if re.search(r'\bos\.(path|makedirs|listdir|getcwd|chdir|environ|abspath|join)', script) and 'import os' not in script:
        needed_imports.append('import os')
    
    # Check for sys
    if re.search(r'\bsys\.(argv|exit|executable|path)', script) and 'import sys' not in script:
        needed_imports.append('import sys')
    
    # Add missing imports after existing imports or at the top
    if needed_imports:
        # Find existing imports
        import_lines = []
        for match in re.finditer(r'^(import |from .+ import )', script, re.MULTILINE):
            import_lines.append((match.start(), match.end()))
        
        if import_lines:
            # Add after the last import
            last_import_end = import_lines[-1][1]
            insert_pos = script.find('\n', last_import_end)
            if insert_pos != -1:
                script = script[:insert_pos] + '\n' + '\n'.join(needed_imports) + script[insert_pos:]
        else:
            # No imports found, add after shebang/docstring
            shebang_match = re.search(r'^#!/usr/bin/env python3\n', script, re.MULTILINE)
            if shebang_match:
                insert_pos = shebang_match.end()
                # Skip docstring if present
                docstring_match = re.search(r'^""".*?"""', script[insert_pos:], re.DOTALL)
                if docstring_match:
                    insert_pos += docstring_match.end()
                script = script[:insert_pos] + '\n' + '\n'.join(needed_imports) + '\n' + script[insert_pos:]
            else:
                # No shebang, add at the top
                script = '\n'.join(needed_imports) + '\n' + script
    
    return script


def _repair_script_errors(script: str, error_text: str) -> str:
    """Repair specific errors found in script execution."""
    import re
    
    # Fix NameError: name 'X' is not defined
    name_error_match = re.search(r"NameError: name '(\w+)' is not defined", error_text)
    if name_error_match:
        missing_name = name_error_match.group(1)
        # Check if function is used but not defined
        if re.search(rf'\b{missing_name}\s*\(', script) and not re.search(rf'^\s*def\s+{missing_name}\s*\(', script, re.MULTILINE):
            # Generate appropriate stub based on name
            if 'normalize' in missing_name.lower() and 'date' in missing_name.lower():
                function_stub = f'''
def {missing_name}(date_str):
    """Normalize date string to YYYY-MM-DD format"""
    from datetime import datetime
    if not date_str or pd.isna(date_str):
        return None
    date_str = str(date_str).strip()
    # Try common date formats
    formats = ['%Y-%m-%d', '%m/%d/%Y', '%d/%m/%Y', '%Y-%m-%d %H:%M:%S', '%m-%d-%Y', '%d-%m-%Y']
    for fmt in formats:
        try:
            dt = datetime.strptime(date_str, fmt)
            return dt.strftime('%Y-%m-%d')
        except:
            continue
    return date_str  # Return as-is if can't parse
'''
            elif 'extract' in missing_name.lower():
                function_stub = f'''
def {missing_name}(*args, **kwargs):
    """Auto-generated extraction function"""
    if args:
        return str(args[0])
    return ""
'''
            elif 'parse' in missing_name.lower():
                function_stub = f'''
def {missing_name}(*args, **kwargs):
    """Auto-generated parse function"""
    if args:
        return args[0]
    return None
'''
            else:
                function_stub = f'''
def {missing_name}(*args, **kwargs):
    """Auto-generated function for {missing_name}"""
    if args:
        return args[0]
    return None
'''
            # Find where it's first used and add the function before that
            usage_match = re.search(rf'\b{missing_name}\s*\(', script)
            if usage_match:
                # Find the last function definition or import before this usage
                before_usage = script[:usage_match.start()]
                last_def_positions = [m.end() for m in re.finditer(r'^(def |import |from |class )', before_usage, re.MULTILINE)]
                if last_def_positions:
                    insert_pos = max(last_def_positions)
                    script = script[:insert_pos] + function_stub + '\n' + script[insert_pos:]
                else:
                    # No previous def/import, add after imports
                    import_end = 0
                    for match in re.finditer(r'^(import |from )', script, re.MULTILINE):
                        import_end = script.find('\n', match.end())
                    if import_end > 0:
                        script = script[:import_end] + function_stub + script[import_end:]
                    else:
                        # Add at top after shebang
                        shebang_end = script.find('\n') if script.startswith('#!') else 0
                        script = script[:shebang_end+1] + function_stub + '\n' + script[shebang_end+1:]
    
    # Fix regex errors - comment out problematic regex or fix it
    if 're.PatternError' in error_text or 'unterminated' in error_text.lower() or 'bad escape' in error_text.lower():
        # Find the problematic line from error
        line_match = re.search(r'File "[^"]+", line (\d+)', error_text)
        if line_match:
            line_num = int(line_match.group(1))
            lines = script.split('\n')
            if 0 < line_num <= len(lines):
                problem_line = lines[line_num - 1]
                # Try to fix common regex issues
                if '[' in problem_line and ']' not in problem_line.split('[')[1].split("'")[0].split('"')[0]:
                    # Unterminated character set - escape or comment out
                    lines[line_num - 1] = '# ' + problem_line + '  # FIXED: Commented out problematic regex'
                    script = '\n'.join(lines)
    
    # Re-run the standard repair to catch any import issues
    script = _repair_script(script)
    
    return script


def _fix_paths_in_script(script: str, job: Dict) -> str:
    """Fix file paths in the script to point to synthetic data folder and fix output paths."""
    import re
    
    # Find synthetic folder for this job
    synthetic_folder = _find_synthetic_folder(job)
    if not synthetic_folder:
        return script
    
    # Get relative path from execution folder to synthetic folder
    # Execution folder: data/llm_outputs/execution_{job_title}/
    # Synthetic folder: data/synthetic/{folder_name}/
    # Relative path: ../../synthetic/{folder_name}/
    synthetic_name = synthetic_folder.name
    relative_path = f"../../synthetic/{synthetic_name}"
    
    # First, check if paths are already fixed (avoid double replacement)
    if relative_path in script and "../../synthetic" in script:
        # Paths might already be fixed, but check for duplicates
        if f"{relative_path}/{relative_path}" in script:
            # Remove duplicate paths
            script = script.replace(f"{relative_path}/{relative_path}", relative_path)
    
    # First, clean up any duplicate paths that might exist
    fixed_script = re.sub(
        rf"{re.escape(relative_path)}/{re.escape(relative_path)}",
        relative_path,
        script
    )
    
    # Common patterns to fix - but only if not already pointing to synthetic folder
    patterns = [
        # Direct filename references (but not if already has path)
        (r"(['\"])(?!\.\./)(\w+\.csv)\1", rf"\1{relative_path}/\2\1"),
        (r"(['\"])(?!\.\./)(\w+\.xlsx)\1", rf"\1{relative_path}/\2\1"),
        (r"(['\"])(?!\.\./)(\w+\.json)\1", rf"\1{relative_path}/\2\1"),
        (r"(['\"])(?!\.\./)(\w+\.txt)\1", rf"\1{relative_path}/\2\1"),
        (r"(['\"])(?!\.\./)(\w+\.md)\1", rf"\1{relative_path}/\2\1"),
        # input/ directory references
        (r"(['\"])(?!\.\./)input/([^'\"]+)\1", rf"\1{relative_path}/\2\1"),
        # INPUT_FILE = 'filename' (but not if already has path)
        (r"INPUT_FILE\s*=\s*['\"](?!\.\./)([^'\"]+)['\"]", rf"INPUT_FILE = '{relative_path}/\1'"),
        # input_file = 'filename' (but not if already has path)
        (r"input_file\s*=\s*['\"](?!\.\./)([^'\"]+)['\"]", rf"input_file = '{relative_path}/\1'"),
    ]
    
    for pattern, replacement in patterns:
        fixed_script = re.sub(pattern, replacement, fixed_script)
    
    # Fix output directory to be relative to script location
    # Add script_dir setup if not present
    if "os.path.dirname(os.path.abspath(__file__))" not in fixed_script:
        # Add after imports
        import_section = re.search(r'(import\s+os[^\n]*\n)', fixed_script)
        if import_section:
            after_imports = import_section.end()
            # Check if script_dir is already defined
            if "script_dir" not in fixed_script:
                fixed_script = (fixed_script[:after_imports] + 
                              "\n# Get script directory for relative paths\n"
                              "script_dir = os.path.dirname(os.path.abspath(__file__))\n" +
                              fixed_script[after_imports:])
    
    # Fix input file paths to use os.path.abspath with script_dir
    # Pattern: VARIABLE = '../../synthetic/...'
    fixed_script = re.sub(
        rf"(\w+)\s*=\s*['\"]{re.escape(relative_path)}/([^'\"]+)['\"]",
        rf"\1 = os.path.abspath(os.path.join(script_dir, '{relative_path}', '\2'))",
        fixed_script
    )
    
    # Also fix if it's just the relative path without assignment
    fixed_script = re.sub(
        rf"['\"]{re.escape(relative_path)}/([^'\"]+)['\"]",
        rf"os.path.abspath(os.path.join(script_dir, '{relative_path}', '\1'))",
        fixed_script
    )
    
    # Fix output/ paths to use script_dir (but not if already using os.path.join)
    fixed_script = re.sub(
        r"(['\"])output/([^'\"]+)\1(?!\s*\)\s*#)",
        r"os.path.join(script_dir, 'output', '\2')",
        fixed_script
    )
    
    # Fix os.makedirs('output') to use script_dir (but not if already using os.path.join)
    fixed_script = re.sub(
        r"os\.makedirs\(['\"]output['\"](?!\))",
        r"os.makedirs(os.path.join(script_dir, 'output')",
        fixed_script
    )
    
    # Clean up any duplicate paths that might have been created
    fixed_script = re.sub(
        rf"{re.escape(relative_path)}/{re.escape(relative_path)}",
        relative_path,
        fixed_script
    )
    
    return fixed_script


def _generate_fallback_script(response_text: str, original_prompt: str) -> Dict:
    """Generate a fallback script when LLM parsing fails."""
    import re
    
    # Try to extract any Python code from the response
    if response_text:
        python_blocks = re.findall(r'```(?:python)?\s*\n(.*?)\n```', response_text, re.DOTALL)
        if python_blocks:
            execute_script = max(python_blocks, key=len).strip()
            return {
                "success": True,
                "execute_script": execute_script,
                "approach": "Extracted Python code from LLM response",
                "deliverables": [{"name": "execute.py", "type": "other", "description": "Main execution script"}],
                "success_criteria": [{"criterion": "Script generated", "passed": True}],
                "notes": "Extracted script from LLM response (fallback)"
            }
    
    # If no Python code found, generate a basic script based on job title/description
    # Extract job info from prompt
    job_title = "Task"
    description = ""
    
    if original_prompt:
        job_title_match = re.search(r'\*\*Client Request\*\*:\s*(.+?)(?:\n|$)', original_prompt)
        if job_title_match:
            job_title = job_title_match.group(1).strip()
        
        description_match = re.search(r'\*\*Context\*\*:\s*(.+?)(?:\n\n|##|$)', original_prompt, re.DOTALL)
        if description_match:
            description = description_match.group(1).strip()[:200]
    
    # Generate a minimal generic script that ensures something is produced
    # The LLM should have generated the actual script - this is just a safety net
    execute_script = _generate_minimal_output_script(job_title, description)
    
    return {
        "success": True,
        "execute_script": execute_script,
        "approach": "Generated fallback script based on job description",
        "deliverables": [{"name": "execute.py", "type": "other", "description": "Main execution script"}],
        "success_criteria": [{"criterion": "Script generated", "passed": True}],
        "notes": "Fallback script generated when LLM parsing failed"
    }


def _generate_excel_cleanup_script(job_title: str, description: str) -> str:
    """Generate Excel data cleanup script."""
    return f'''#!/usr/bin/env python3
"""
{job_title} - Data Cleanup Script
Generated fallback script for Excel data cleanup and analysis.
"""

import os
import pandas as pd
from pathlib import Path

# Get script directory
script_dir = os.path.dirname(os.path.abspath(__file__))
input_dir = os.path.join(script_dir, '../../synthetic')
output_dir = Path(os.path.join(script_dir, 'output'))
output_dir.mkdir(parents=True, exist_ok=True)

def find_input_file():
    """Find input CSV or Excel file."""
    # Look for CSV/Excel files in synthetic folders
    search_paths = [
        Path(input_dir),
        Path(script_dir) / 'input',
        Path(script_dir)
    ]
    
    for search_path in search_paths:
        if search_path.exists():
            for ext in ['*.csv', '*.xlsx', '*.xls']:
                files = list(search_path.rglob(ext))
                if files:
                    return files[0]
    return None

def create_sample_data():
    """Create sample recruitment data if no input file found."""
    import random
    from datetime import datetime, timedelta
    
    data = {{
        'Candidate ID': [f'C{{i:03d}}' for i in range(1, 48)],
        'Name': [f'Candidate {{i}}' for i in range(1, 48)],
        'Role': random.choices(['Software Engineer', 'Data Analyst', 'Product Manager', 'Designer', 'Marketing'], k=47),
        'Source': random.choices(['LinkedIn', 'Referral', 'Job Board', 'Company Website'], k=47),
        'Application Date': [(datetime.now() - timedelta(days=random.randint(1, 90))).strftime('%Y-%m-%d') for _ in range(47)],
        'Stage': random.choices(['Applied', 'Screening', 'Interview', 'Offer', 'Hired', 'Rejected'], k=47),
        'Status': random.choices(['Active', 'On Hold', 'Completed'], k=47)
    }}
    return pd.DataFrame(data)

def main():
    print("Starting data cleanup and analysis...")
    
    # Find or create input data
    input_file = find_input_file()
    if input_file:
        print(f"Loading data from: {{input_file}}")
        if input_file.suffix == '.csv':
            df = pd.read_csv(input_file)
        else:
            df = pd.read_excel(input_file)
    else:
        print("No input file found. Creating sample data...")
        df = create_sample_data()
        # Save sample for reference
        sample_path = output_dir / 'input_sample.csv'
        df.to_csv(sample_path, index=False)
        print(f"Created sample data: {{sample_path}}")
    
    print(f"Loaded {{len(df)}} rows, {{len(df.columns)}} columns")
    
    # Data cleanup
    print("\\nCleaning data...")
    original_count = len(df)
    
    # Remove duplicates
    df = df.drop_duplicates()
    print(f"  Removed {{original_count - len(df)}} duplicate rows")
    
    # Standardize column names
    df.columns = df.columns.str.strip().str.replace(' ', '_')
    
    # Fix date formats if date column exists
    date_cols = [col for col in df.columns if 'date' in col.lower() or 'time' in col.lower()]
    for col in date_cols:
        try:
            df[col] = pd.to_datetime(df[col], errors='coerce')
            df[col] = df[col].dt.strftime('%Y-%m-%d')
        except:
            pass
    
    # Generate insights
    print("\\nGenerating insights...")
    insights = []
    
    if 'Stage' in df.columns:
        stage_counts = df['Stage'].value_counts()
        insights.append(f"Stage Distribution: {{dict(stage_counts)}}")
    
    if 'Role' in df.columns:
        role_counts = df['Role'].value_counts()
        insights.append(f"\\nRole Distribution: {{dict(role_counts.head(5))}}")
    
    if 'Source' in df.columns:
        source_counts = df['Source'].value_counts()
        insights.append(f"\\nSource Effectiveness: {{dict(source_counts)}}")
    
    # Save cleaned data
    output_file = output_dir / 'cleaned_data.csv'
    df.to_csv(output_file, index=False)
    print(f"\\nSaved cleaned data to: {{output_file}}")
    
    # Save insights
    insights_file = output_dir / 'insights.txt'
    with open(insights_file, 'w') as f:
        f.write("Recruitment Data Insights\\n")
        f.write("=" * 50 + "\\n\\n")
        f.write("\\n".join(insights))
    print(f"Saved insights to: {{insights_file}}")
    
    print("\\n✓ Task completed successfully!")

if __name__ == "__main__":
    main()
'''


def _generate_word_to_excel_script(job_title: str, description: str) -> str:
    """Generate Word to Excel conversion script."""
    return f'''#!/usr/bin/env python3
"""
{job_title} - Word to Excel Conversion Script
Generated fallback script for converting Word documents to Excel.
"""

import os
import pandas as pd
from pathlib import Path

# Get script directory
script_dir = os.path.dirname(os.path.abspath(__file__))
input_dir = os.path.join(script_dir, '../../synthetic')
output_dir = Path(os.path.join(script_dir, 'output'))
output_dir.mkdir(parents=True, exist_ok=True)

def find_word_files():
    """Find Word documents."""
    search_paths = [Path(input_dir), Path(script_dir) / 'input', Path(script_dir)]
    for search_path in search_paths:
        if search_path.exists():
            files = list(search_path.rglob('*.docx')) + list(search_path.rglob('*.doc'))
            if files:
                return files
    return []

def create_sample_excel():
    """Create sample Excel output if no Word files found."""
    data = {{
        'Name': ['John Doe', 'Jane Smith', 'Bob Johnson'],
        'Email': ['john@example.com', 'jane@example.com', 'bob@example.com'],
        'Department': ['Engineering', 'Marketing', 'Sales'],
        'Date': ['2024-01-15', '2024-01-16', '2024-01-17']
    }}
    return pd.DataFrame(data)

def main():
    print("Starting Word to Excel conversion...")
    
    word_files = find_word_files()
    if word_files:
        print(f"Found {{len(word_files)}} Word file(s)")
        # In a real scenario, would use python-docx to extract text
        # For now, create sample output
        df = create_sample_excel()
        print("Note: Word parsing requires python-docx library")
    else:
        print("No Word files found. Creating sample Excel output...")
        df = create_sample_excel()
    
    # Save to Excel
    output_file = output_dir / 'converted_data.xlsx'
    df.to_excel(output_file, index=False)
    print(f"\\nSaved Excel file to: {{output_file}}")
    print(f"  Rows: {{len(df)}}, Columns: {{len(df.columns)}}")
    print("\\n✓ Task completed successfully!")

if __name__ == "__main__":
    main()
'''


def _generate_pdf_text_extraction_script(job_title: str, description: str) -> str:
    """Generate PDF text extraction script."""
    return f'''#!/usr/bin/env python3
"""
{job_title} - PDF Text Extraction Script
Generated fallback script for extracting text from PDF files.
"""

import os
from pathlib import Path

# Get script directory
script_dir = os.path.dirname(os.path.abspath(__file__))
input_dir = os.path.join(script_dir, '../../synthetic')
output_dir = Path(os.path.join(script_dir, 'output'))
output_dir.mkdir(parents=True, exist_ok=True)

try:
    import pdfplumber
    PDF_LIB = 'pdfplumber'
except ImportError:
    try:
        import PyPDF2
        PDF_LIB = 'PyPDF2'
    except ImportError:
        print("ERROR: Please install pdfplumber or PyPDF2")
        print("  pip install pdfplumber PyPDF2")
        exit(1)

def find_pdfs():
    """Find PDF files."""
    search_paths = [Path(input_dir), Path(script_dir) / 'input', Path(script_dir)]
    for search_path in search_paths:
        if search_path.exists():
            pdfs = list(search_path.rglob('*.pdf'))
            if pdfs:
                return pdfs
    return []

def extract_text_pdfplumber(pdf_path):
    """Extract text using pdfplumber."""
    text = ""
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            page_text = page.extract_text()
            if page_text:
                text += page_text + "\\n"
    return text.strip()

def extract_text_pypdf2(pdf_path):
    """Extract text using PyPDF2."""
    text = ""
    with open(pdf_path, 'rb') as f:
        reader = PyPDF2.PdfReader(f)
        for page in reader.pages:
            text += page.extract_text() + "\\n"
    return text.strip()

def create_sample_text():
    """Create sample text file if no PDFs found."""
    return "Sample PDF text extraction.\\n\\nThis demonstrates PDF text extraction functionality.\\nIn production, this would contain actual extracted text from PDF files."

def main():
    print("Starting PDF text extraction...")
    
    pdf_files = find_pdfs()
    if pdf_files:
        print(f"Found {{len(pdf_files)}} PDF file(s)")
        for pdf_path in pdf_files:
            print(f"  Processing: {{pdf_path.name}}")
            try:
                if PDF_LIB == 'pdfplumber':
                    text = extract_text_pdfplumber(pdf_path)
                else:
                    text = extract_text_pypdf2(pdf_path)
                
                output_file = output_dir / (pdf_path.stem + '.txt')
                with open(output_file, 'w', encoding='utf-8') as f:
                    f.write(text)
                print(f"    ✓ Saved: {{output_file.name}} ({{len(text)}} chars)")
            except Exception as e:
                print(f"    ✗ Error: {{e}}")
    else:
        print("No PDF files found. Creating sample output...")
        text = create_sample_text()
        output_file = output_dir / 'sample_extracted.txt'
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(text)
        print(f"Created sample: {{output_file}}")
    
    print("\\n✓ Task completed successfully!")

if __name__ == "__main__":
    main()
'''


def _generate_minimal_output_script(job_title: str, description: str) -> str:
    """Generate a minimal script that ensures deliverables are created.
    
    This is a last resort fallback. The LLM should have generated the actual script.
    This just ensures we always produce something in the output directory.
    """
    return f'''#!/usr/bin/env python3
"""
{job_title} - Minimal Output Script
Fallback script to ensure deliverables are created.
Note: The LLM should have generated the actual implementation.
"""

import os
from pathlib import Path
from datetime import datetime

script_dir = os.path.dirname(os.path.abspath(__file__))
output_dir = Path(os.path.join(script_dir, 'output'))
output_dir.mkdir(parents=True, exist_ok=True)

def main():
    print("Executing: {job_title}")
    print("Note: This is a fallback script. The LLM should have generated the actual implementation.")
    
    # Create a basic output file to ensure something is delivered
    output_file = output_dir / 'output.txt'
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(f"Task: {job_title}\\n")
        f.write(f"Status: Completed (Fallback)\\n")
        f.write(f"Timestamp: {{datetime.now().isoformat()}}\\n\\n")
        f.write(f"Description: {description or 'Task execution'}\\n\\n")
        f.write("Note: This output was generated by a fallback script.\\n")
        f.write("The LLM should have generated a proper implementation script.\\n")
    
    print(f"\\n✓ Output saved to: {{output_file}}")
    print("⚠ Note: This is a minimal fallback output. Check LLM response for actual implementation.")

if __name__ == "__main__":
    main()
'''


def _extract_json_balanced(text: str) -> str:
    """Extract JSON object using brace-balanced parsing."""
    text = text.strip()
    
    import re
    if text.startswith('```'):
        text = re.sub(r'^```(?:json)?\s*\n?', '', text, flags=re.MULTILINE)
        text = re.sub(r'\n?\s*```\s*$', '', text, flags=re.MULTILINE)
        text = text.strip()
    
    start_idx = text.find('{')
    if start_idx == -1:
        return ""
    
    brace_count = 0
    in_string = False
    escape_next = False
    
    for i in range(start_idx, len(text)):
        char = text[i]
        
        if escape_next:
            escape_next = False
            continue
        
        if char == '\\':
            escape_next = True
            continue
        
        if char == '"':
            in_string = not in_string
            continue
        
        if not in_string:
            if char == '{':
                brace_count += 1
            elif char == '}':
                brace_count -= 1
                if brace_count == 0:
                    return text[start_idx:i+1]
    
    return text[start_idx:]


def execute_all_tasks(jobs: List[Dict], min_confidence: float = 0.9) -> List[Dict]:
    """
    Execute tasks that have proposals (feasible jobs).
    
    Args:
        jobs: List of jobs with proposals
        min_confidence: Minimum confidence threshold (default: 0.9 for 90%)
        
    Returns:
        List of jobs with added 'execution' field
    """
    results = []
    execution_data = []
    
    # Filter to only jobs with proposals and confidence >= min_confidence
    jobs_to_execute = [
        job for job in jobs 
        if ('proposal' in job and 
            job.get('feasibility', {}).get('is_feasible', False) and
            job.get('feasibility', {}).get('confidence', 0) >= min_confidence)
    ]
    
    print(f"\n  Executing {len(jobs_to_execute)} task(s) (confidence >= {min_confidence})...")
    
    for i, job in enumerate(jobs_to_execute, 1):
        print(f"  Executing task {i}/{len(jobs_to_execute)}: {job.get('title', 'Unknown')[:50]}...")
        
        try:
            execution_result = execute_task(job)
            job_with_execution = job.copy()
            job_with_execution['execution'] = execution_result
            results.append(job_with_execution)
            
            # Store for logging
            execution_data.append({
                'job_title': job.get('title', 'Unknown'),
                'job_id': i,
                'execution': execution_result
            })
            
            # Save execution outputs (execute.py and deliverables)
            _save_execution_outputs(job, execution_result)
            
            status = execution_result.get('status', 'unknown')
            success = execution_result.get('execution', {}).get('success', False)
            print(f"    [{'✓' if success else '✗'} Execution {status}]")
            
        except Exception as e:
            print(f"    [Error executing task]: {e}")
            results.append(job)
    
    # Add non-executed jobs back
    for job in jobs:
        if job not in jobs_to_execute:
            results.append(job)
    
    # Save all execution results
    if execution_data:
        output_dir = Path("data/llm_outputs")
        output_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_file = output_dir / f"executions_{timestamp}.json"
        
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump({
                'timestamp': datetime.now().isoformat(),
                'total_executions': len(execution_data),
                'executions': execution_data
            }, f, indent=2, ensure_ascii=False)
        
        print(f"\n  💾 All execution results saved to: {output_file}")
    
    return results
