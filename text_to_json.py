#!/usr/bin/env python3
"""
Convert text/markdown job postings to JSON format.
This is the first step of the pipeline for identifying feasible work.
"""

import json
import re
from pathlib import Path
from typing import List, Dict, Optional
from llm_client import get_llm_client


def extract_job_with_llm(text: str) -> Optional[Dict]:
    """
    Extract job posting data using LLM with JSON schema.
    Simple extraction - direct copy or keyword spotting, no reasoning.
    
    Args:
        text: Raw text of job posting
        
    Returns:
        Parsed job dictionary or None
    """
    # Load JSON schema
    schema_path = Path(__file__).parent / "schemas" / "job_extraction_schema.json"
    try:
        with open(schema_path, 'r') as f:
            job_schema = json.load(f)
    except FileNotFoundError:
        print(f"    [Warning]: Schema file not found, using fallback parser")
        return parse_job_posting(text)
    
    llm = get_llm_client()
    
    # Simple prompt - just ask for extraction using the schema
    prompt = f"""Extract structured information from this job posting using simple extraction (direct copy or keyword spotting, no reasoning):

{text}

Return JSON matching the schema. Include raw_text field with the original text.
"""
    
    messages = [{"role": "user", "content": prompt}]
    
    # Try with json_schema format first
    response_format = {
        "type": "json_schema",
        "json_schema": {
            "name": "job_extraction",
            "schema": job_schema,
            "strict": True
        }
    }
    
    try:
        response = llm.chat(messages, temperature=0.1, max_tokens=2000, response_format=response_format)
    except Exception as schema_error:
        # If json_schema format fails, try with text format (plain JSON)
        error_msg = str(schema_error)
        if "400" in error_msg or "json_schema" in error_msg.lower() or "response_format" in error_msg.lower():
            print(f"    [json_schema not supported, using text format]")
            response_format = {"type": "text"}
            try:
                response = llm.chat(messages, temperature=0.1, max_tokens=2000, response_format=response_format)
            except Exception as text_error:
                print(f"    [LLM Extraction Error]: {text_error}")
                return parse_job_posting(text)
        else:
            print(f"    [LLM Extraction Error]: {schema_error}")
            return parse_job_posting(text)
    
    # Parse JSON response
    try:
        response_cleaned = response.strip()
        # Remove markdown code blocks if present
        if response_cleaned.startswith('```'):
            response_cleaned = re.sub(r'^```(?:json)?\s*\n?', '', response_cleaned, flags=re.MULTILINE)
            response_cleaned = re.sub(r'\n?\s*```\s*$', '', response_cleaned, flags=re.MULTILINE)
        
        result = json.loads(response_cleaned.strip())
        
        # Ensure raw_text is included
        if "raw_text" not in result:
            result["raw_text"] = text.strip()
        
        # Ensure all expected fields exist (set to empty string/array if missing)
        expected_fields = {
            "title": "",
            "status": "",
            "posted_time": "",
            "ends_time": "",
            "budget": "",
            "payment_terms": "",
            "experience_level": "",
            "description": "",
            "requirements": [],
            "deliverables": []
        }
        
        for field, default_value in expected_fields.items():
            if field not in result:
                result[field] = default_value
        
        # Store LLM interaction for logging
        result["llm_prompt"] = prompt
        result["llm_response"] = response
        
        # Validate required fields
        if not result.get("title"):
            print(f"    [Warning]: No title extracted, using fallback parser")
            return parse_job_posting(text)
        
        return result
        
    except json.JSONDecodeError as e:
        print(f"    [JSON Parse Error]: {e}")
        print(f"    [Falling back to rule-based parser]")
        return parse_job_posting(text)
    except Exception as e:
        print(f"    [LLM Extraction Error]: {e}")
        return parse_job_posting(text)


def parse_job_posting(text: str) -> Optional[Dict]:
    """
    Parse a single job posting from text format.
    
    Expected format:
    - Title (first line)
    - Status (Open/Awarded)
    - Posted time
    - Ends time (or "Ends in X days")
    - Budget/rate
    - Description (multi-paragraph)
    - Additional metadata (Experience Level, etc.)
    """
    lines = [line.strip() for line in text.strip().split('\n') if line.strip()]
    
    if not lines:
        return None
    
    job = {
        "title": "",
        "status": "",
        "posted_time": "",
        "ends_time": "",
        "budget": "",
        "payment_terms": "",
        "experience_level": "",
        "description": "",
        "requirements": [],
        "deliverables": [],
        "raw_text": text.strip()
    }
    
    # Parse title (first non-empty line)
    if lines:
        job["title"] = lines[0]
    
    # Look for status (can be "Open", "Awarded", or "OPPORTUNITY AWARDED")
    status_idx = None
    for i, line in enumerate(lines):
        line_lower = line.lower()
        if line_lower == "open":
            job["status"] = "Open"
            status_idx = i
            break
        elif "awarded" in line_lower:
            job["status"] = "Awarded"
            status_idx = i
            # For awarded jobs, the posted info might be in the same line
            if "posted" in line_lower:
                job["posted_time"] = line
            break
    
    # Parse posted time (usually after status, or in same line for awarded jobs)
    if status_idx is not None and not job["posted_time"]:
        # Check next few lines for posted info
        for i in range(status_idx + 1, min(status_idx + 3, len(lines))):
            line = lines[i]
            if "posted" in line.lower():
                job["posted_time"] = line
                break
    
    # Parse ends time
    for i, line in enumerate(lines):
        if "ends" in line.lower() and ("day" in line.lower() or "in" in line.lower()):
            job["ends_time"] = line
            break
    
    # Parse budget/rate (look for currency symbols or INR/USD/AUD/GBP)
    budget_pattern = r'[₹$£€]\d+[-\d\s]*(?:INR|USD|AUD|GBP|EUR)?(?:\s*/\s*(?:hour|hr|project))?'
    for line in lines:
        line_lower = line.lower()
        # Skip "FIXED PRICE" lines for budget (they're payment terms)
        if "fixed price" in line_lower:
            continue
        if re.search(budget_pattern, line, re.IGNORECASE):
            job["budget"] = line
            break
    
    # Parse payment terms (including FIXED PRICE)
    for i, line in enumerate(lines):
        line_lower = line.lower()
        if "paid on delivery" in line_lower:
            job["payment_terms"] = line
            break
        elif "fixed price" in line_lower:
            # FIXED PRICE might be on next line, combine if needed
            price_line = line
            if i + 1 < len(lines) and re.search(r'[₹$£€]\d+', lines[i + 1]):
                price_line = f"{line} {lines[i + 1]}"
            job["payment_terms"] = price_line
            # Also set budget from fixed price
            if not job["budget"]:
                budget_match = re.search(r'[₹$£€]\d+[-\d\s]*(?:INR|USD|AUD|GBP|EUR)?', price_line)
                if budget_match:
                    job["budget"] = budget_match.group(0)
            break
    
    # Parse experience level
    for i, line in enumerate(lines):
        if "experience level" in line.lower():
            # Get the value, might be on same line or next
            parts = line.split(":", 1)
            if len(parts) > 1:
                job["experience_level"] = parts[1].strip()
            elif i + 1 < len(lines):
                job["experience_level"] = lines[i + 1].strip()
            break
    
    # Find metadata lines (posted, ends, budget, payment terms)
    metadata_end = 0
    desc_header_idx = None
    for i, line in enumerate(lines):
        line_lower = line.lower().strip()
        # Check for "Description" header (for awarded jobs)
        if line_lower == "description":
            desc_header_idx = i
            metadata_end = i + 1
        if any(keyword in line_lower for keyword in ["posted", "ends in", "ends:", "paid on"]):
            metadata_end = max(metadata_end, i + 1)
        # Also check for budget pattern (but not "FIXED PRICE" as standalone)
        if re.search(r'[₹$£€]\d+', line) and "fixed price" not in line_lower:
            metadata_end = max(metadata_end, i + 1)
    
    # Find where Requirements or Deliverables sections start
    req_idx = None
    deliv_idx = None
    ideal_idx = None
    for i, line in enumerate(lines):
        line_lower = line.lower().strip()
        if line_lower.startswith("requirements"):
            req_idx = i
        if line_lower.startswith("deliverable"):
            deliv_idx = i
        if line_lower.startswith("ideal"):
            ideal_idx = i
    
    # Extract main description (everything after metadata/Description header, before Requirements/Deliverables/Ideal)
    desc_start = max(metadata_end, 1)  # Start after title and metadata
    desc_end = min([idx for idx in [req_idx, deliv_idx, ideal_idx] if idx is not None], default=len(lines))
    
    if desc_end > desc_start:
        desc_lines = lines[desc_start:desc_end]
        # Filter out empty lines at start/end and skip lines that are just "*" or formatting
        desc_lines = [line for line in desc_lines if line.strip() and not line.strip() in ['*', '•']]
        # Filter out lines that are just numbers or single characters
        desc_lines = [line for line in desc_lines if len(line.strip()) > 2 or not line.strip().isdigit()]
        if desc_lines:
            job["description"] = "\n".join(desc_lines).strip()
    
    # Extract requirements (including "Ideal Skills and Experience")
    if req_idx is not None or ideal_idx is not None:
        # Start from Requirements or Ideal section, whichever comes first
        req_start = min([idx for idx in [req_idx, ideal_idx] if idx is not None], default=None)
        if req_start is not None:
            req_end = deliv_idx if deliv_idx is not None else len(lines)
            req_lines = lines[req_start + 1:req_end]
            requirements = []
            for line in req_lines:
                # Skip empty lines and section headers
                if line and not line.lower().startswith("deliverable") and not line.lower().startswith("acceptance"):
                    # Handle bullet points
                    cleaned = re.sub(r'^[-•*]\s*', '', line)
                    if cleaned and len(cleaned) > 3:  # Filter out very short lines
                        requirements.append(cleaned)
            job["requirements"] = requirements
    
    # Extract deliverables
    if deliv_idx is not None:
        deliv_lines = lines[deliv_idx + 1:]
        deliverables = []
        for line in deliv_lines:
            if line and not line.lower().startswith("acceptance"):
                cleaned = re.sub(r'^[-•*]\s*', '', line)
                if cleaned:
                    deliverables.append(cleaned)
        job["deliverables"] = deliverables
    
    return job


def split_job_postings(text: str) -> List[str]:
    """
    Split the text into individual job postings.
    Jobs are separated by 3+ consecutive blank lines.
    """
    # Split by 3+ consecutive newlines (job separator)
    # This handles the pattern where jobs are separated by multiple blank lines
    job_separator = re.compile(r'\n{3,}')
    sections = job_separator.split(text)
    
    jobs = []
    for section in sections:
        section = section.strip()
        if not section:
            continue
        
        lines = section.split('\n')
        first_line = lines[0].strip() if lines else ""
        
        # Validate this looks like a job posting
        # Should have a title (first line) and likely status/metadata
        if first_line and len(first_line) < 150:
            # Check if followed by status indicators
            has_status = any(
                line.strip().lower() in ['open', 'awarded'] 
                for line in lines[1:5] if line.strip()
            )
            # Or has budget/rate pattern
            has_budget = any(
                re.search(r'[₹$£€]\d+', line) 
                for line in lines[:10]
            )
            
            if has_status or has_budget:
                jobs.append(section)
    
    return jobs


def convert_text_to_json(input_path: str, save_llm_outputs: bool = True) -> Dict:
    """
    Convert text file containing job postings to JSON format.
    This is the first step of the pipeline.
    
    Args:
        input_path: Path to input text/markdown file
        save_llm_outputs: Whether to save all LLM responses to a file
        
    Returns:
        Dictionary with metadata and jobs list
    """
    input_file = Path(input_path)
    if not input_file.exists():
        raise FileNotFoundError(f"Input file not found: {input_path}")
    
    # Read input file
    with open(input_file, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Split into individual job postings
    job_texts = split_job_postings(content)
    
    # Parse each job posting using LLM
    jobs = []
    llm_outputs = []
    
    for i, job_text in enumerate(job_texts, 1):
        print(f"  Extracting job {i}/{len(job_texts)} with LLM...")
        try:
            job = extract_job_with_llm(job_text)
            if job and job.get("title"):
                jobs.append(job)
                print(f"    [✓ Successfully extracted: {job.get('title', 'Unknown')[:50]}]")
                
                # Store LLM output for logging
                if 'llm_response' in job or 'llm_prompt' in job:
                    llm_outputs.append({
                        'job_title': job.get('title', 'Unknown'),
                        'job_id': i,
                        'prompt': job.get('llm_prompt', ''),
                        'response': job.get('llm_response', ''),
                        'parsed_result': job
                    })
            else:
                print(f"    [Warning]: Failed to extract job {i}, skipping")
        except Exception as e:
            print(f"    [Error extracting job {i}]: {e}")
            # Try fallback parser
            job = parse_job_posting(job_text)
            if job and job.get("title"):
                jobs.append(job)
                print(f"    [✓ Used fallback parser for job {i}]")
    
    # Save all LLM outputs to a file
    if save_llm_outputs and llm_outputs:
        from datetime import datetime
        output_dir = Path("data/llm_outputs")
        output_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_file = output_dir / f"text_to_json_extractions_{timestamp}.json"
        
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump({
                'timestamp': datetime.now().isoformat(),
                'source_file': str(input_path),
                'total_jobs': len(job_texts),
                'successful_extractions': len(jobs),
                'extractions': llm_outputs
            }, f, indent=2, ensure_ascii=False)
        
        print(f"\n  💾 All LLM extraction outputs saved to: {output_file}")
    
    # Create output structure
    output = {
        "metadata": {
            "source_file": str(input_path),
            "total_jobs": len(jobs),
            "conversion_date": None  # Could add timestamp if needed
        },
        "jobs": jobs
    }
    
    return output


def save_json(data: Dict, output_path: str) -> None:
    """
    Save JSON data to a file.
    
    Args:
        data: Dictionary to save as JSON
        output_path: Path to output JSON file
    """
    output_file = Path(output_path)
    output_file.parent.mkdir(parents=True, exist_ok=True)
    
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


if __name__ == "__main__":
    # For testing purposes only
    import sys
    from datetime import datetime
    
    default_input = "data/handpicked_ads.md"
    default_output = "data/handpicked_ads.json"
    
    input_path = sys.argv[1] if len(sys.argv) > 1 else default_input
    output_path = sys.argv[2] if len(sys.argv) > 2 else default_output
    
    try:
        data = convert_text_to_json(input_path)
        data["metadata"]["conversion_date"] = datetime.now().isoformat()
        save_json(data, output_path)
        print(f"✓ Converted {data['metadata']['total_jobs']} job postings from {input_path} to {output_path}")
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
