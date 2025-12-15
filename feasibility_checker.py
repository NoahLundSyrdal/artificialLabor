#!/usr/bin/env python3
"""
Feasibility checker using local LLM (LM Studio).
This is step 2 of the pipeline - identifying feasible work.
"""

from typing import Dict, List
import os
import json
from datetime import datetime
from pathlib import Path
from llm_client import get_llm_client

# Load environment variables if dotenv is available
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # dotenv not required


def _call_local_llm(prompt: str, max_tokens: int = 350) -> str:
    """
    Call local LLM (LM Studio) using the LLM client.
    
    Args:
        prompt: The prompt to send to the LLM
        max_tokens: Maximum tokens to generate (default 350 for shorter responses)
        
    Returns:
        Response text from the LLM
    """
    llm = get_llm_client()
    messages = [{"role": "user", "content": prompt}]
    return llm.chat(messages, temperature=0.2, max_tokens=max_tokens)


def check_job_feasibility(job: Dict) -> Dict:
    """
    Check if a single job is feasible using local LLM (LM Studio).
    
    Args:
        job: Job dictionary with title, description, requirements, etc.
        
    Returns:
        Dictionary with feasibility assessment including:
        - is_feasible: boolean
        - confidence: float (0-1)
        - reasoning: string explanation
        - estimated_tokens: int (total tokens for execution)
        - risks: list of potential issues
    """
    try:
        # Normalize job data - check for fields with trailing spaces and merge
        def get_field(job, *keys):
            """Get field value, trying multiple key variations."""
            for key in keys:
                if key in job and job[key]:
                    return job[key]
            return None
        
        title = get_field(job, 'title', 'title ')
        status = get_field(job, 'status', 'status ')
        posted = get_field(job, 'posted_time', 'posted_time ', 'posted')
        ends = get_field(job, 'ends_time', 'ends_time ', 'ends_in')
        budget = get_field(job, 'budget', 'budget ', 'rate')
        payment = get_field(job, 'payment_terms', 'payment_terms ')
        exp_level = get_field(job, 'experience_level', 'experience_level ')
        description = get_field(job, 'description', 'description ')
        requirements = get_field(job, 'requirements', 'requirements ') or []
        deliverables = get_field(job, 'deliverables', 'deliverables ') or []
        
        # Use all structured data from the text_to_json step
        job_details = f"""Title: {title or 'N/A'}
Status: {status or 'N/A'}
Posted: {posted or 'N/A'}
Ends: {ends or 'N/A'}
Budget: {budget or 'N/A'}
Payment Terms: {payment or 'N/A'}
Experience Level: {exp_level or 'N/A'}
Description: {description or 'N/A'}
Requirements: {', '.join(requirements) if requirements else 'N/A'}
Deliverables: {', '.join(deliverables) if deliverables else 'N/A'}"""
        
        prompt = f"""You are a Task Assessor for an automated freelancing system. Evaluate this job posting to determine if it can be profitably completed by an LLM-based agent with access to tools (Python libraries, APIs, file processing, etc.).

{job_details}

Assess:
1. FEASIBILITY: Can an LLM agent complete this task using available tools? Be selective - only mark feasible if:
   - The task is straightforward and well-defined (data entry, file conversion, basic analysis)
   - Tools exist and are reliable (pandas for Excel, pdfplumber for PDFs, openpyxl for spreadsheets)
   - Minimal ambiguity or judgment required
   - NOT feasible if: requires complex human judgment, creative design, iterative client feedback, or unclear requirements
2. CONFIDENCE: Use varied confidence scores (0.5-0.9 range):
   - 0.9+ only for very straightforward, well-defined tasks with clear tools
   - 0.7-0.8 for tasks that are doable but have some complexity/risks
   - 0.5-0.6 for borderline cases that might work but have significant challenges
   - Lower for tasks with ambiguity or high risk
3. COST: ALWAYS estimate total tokens required (even if not feasible). Consider:
   - Reading/parsing input files
   - Processing data
   - Generating outputs (code, documents, visualizations, etc.)
   - Any iterative refinement needed
   If not feasible, estimate tokens for what WOULD be attempted before failure.

Return ONLY valid JSON (no markdown, no code fences, no extra text):
{{
  "is_feasible": true or false,
  "confidence": 0.0-1.0 (use varied scores, not always 0.95),
  "reasoning": "1-2 sentence explanation. No newlines inside this string.",
  "estimated_tokens": number (REQUIRED - always provide, even if not feasible),
  "risks": ["max 3 items"]
}}

CRITICAL: Output ONLY the JSON object. No markdown fences. No newlines inside string values. Escape all special characters. estimated_tokens is REQUIRED. Use VARIED confidence scores.
"""
        
        # Call local LLM (shorter max_tokens to reduce truncation)
        response_text = _call_local_llm(prompt, max_tokens=350)
        
        # Parse JSON response with repair pass (logging happens inside)
        result = _extract_and_parse_json(response_text, prompt)
        
        # Ensure all required fields
        assessment = {
            "is_feasible": bool(result.get("is_feasible", False)),
            "confidence": float(result.get("confidence", 0.5)),
            "reasoning": str(result.get("reasoning", response_text[:500])),
            "estimated_tokens": result.get("estimated_tokens"),  # Token cost for execution
            "risks": result.get("risks", []),
            # Store raw outputs for logging
            "llm_prompt": prompt,
            "llm_response": response_text
        }
        
        return assessment
        
    except Exception as e:
        # Error handling - return basic assessment (default to NOT feasible on error)
        print(f"    [Error]: {e}")
        return {
            "is_feasible": False,  # Default to NOT feasible on error (more conservative)
            "confidence": 0.2,
            "reasoning": f"Error during assessment: {str(e)}",
            "estimated_tokens": None,
            "risks": ["Assessment error occurred"],
            "llm_prompt": "",
            "llm_response": ""
        }


def _extract_json_balanced(text: str) -> str:
    """
    Extract JSON object using brace-balanced parsing (more robust than regex).
    Finds the first { and scans until braces balance to 0.
    """
    text = text.strip()
    
    # Remove markdown code fences
    import re
    if text.startswith('```'):
        text = re.sub(r'^```(?:json)?\s*\n?', '', text, flags=re.MULTILINE)
        text = re.sub(r'\n?\s*```\s*$', '', text, flags=re.MULTILINE)
        text = text.strip()
    
    # Find first {
    start_idx = text.find('{')
    if start_idx == -1:
        return ""
    
    # Balance braces
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
    
    # If we get here, braces never balanced - return what we have
    return text[start_idx:]


def _extract_and_parse_json(response_text: str, original_prompt: str) -> Dict:
    """
    Extract and parse JSON from LLM response with repair pass if needed.
    """
    import re
    
    # Log preview
    response_preview = response_text[:200] + "..." if len(response_text) > 200 else response_text
    print(f"    [LLM Response]: {response_preview}")
    
    # Extract JSON using brace-balanced method
    json_str = _extract_json_balanced(response_text)
    
    if not json_str:
        print(f"    [No JSON found, using text parser]")
        return _parse_text_response(response_text)
    
    # Quick fixes
    json_str = re.sub(r'"""', '"', json_str)
    json_str = re.sub(r"'''", "'", json_str)
    json_str = re.sub(r',\s*}', '}', json_str)  # trailing commas
    json_str = re.sub(r',\s*]', ']', json_str)
    
    # Try parsing
    try:
        result = json.loads(json_str)
        print(f"    [✓ Parsed JSON successfully]")
        return result
    except json.JSONDecodeError as e:
        print(f"    [JSON parse failed, attempting repair...]")
        
        # Repair pass: ask LLM to fix the JSON
        repair_prompt = f"""The following JSON is invalid. Fix it to be valid JSON only. Return ONLY the corrected JSON object, no markdown, no explanation:

{json_str}

Original error: {str(e)[:100]}

Return ONLY valid JSON matching this structure:
{{
  "is_feasible": true or false,
  "confidence": 0.0-1.0,
  "reasoning": "1-2 sentences, no newlines",
  "estimated_tokens": number (REQUIRED - always provide, even if not feasible),
  "risks": ["max 3 items"]
}}"""
        
        try:
            repaired_response = _call_local_llm(repair_prompt, max_tokens=200)
            repaired_json = _extract_json_balanced(repaired_response)
            
            if repaired_json:
                try:
                    result = json.loads(repaired_json)
                    print(f"    [✓ Repaired and parsed JSON]")
                    return result
                except json.JSONDecodeError:
                    pass
        except Exception as repair_error:
            print(f"    [Repair failed: {repair_error}]")
        
        # Final fallback: text parser
        print(f"    [Using text parser fallback]")
        return _parse_text_response(response_text)


def _parse_text_response(text: str) -> Dict:
    """Parse a text response into structured format when JSON parsing fails.
    Lenient extraction - just get what we can since it's going to another LLM anyway.
    """
    import re
    text_lower = text.lower()
    
    # Extract is_feasible - try multiple patterns
    is_feasible = None
    feasible_match = re.search(r'"is_feasible"\s*:\s*(true|false)', text, re.IGNORECASE)
    if feasible_match:
        is_feasible = feasible_match.group(1).lower() == 'true'
    else:
        # Try without quotes
        feasible_match = re.search(r'is_feasible\s*:\s*(true|false)', text, re.IGNORECASE)
        if feasible_match:
            is_feasible = feasible_match.group(1).lower() == 'true'
        else:
            # Look for explicit true/false near "feasible"
            feasible_true = re.search(r'feasible[^"]*(?:true|yes|1)', text, re.IGNORECASE)
            feasible_false = re.search(r'feasible[^"]*(?:false|no|0)', text, re.IGNORECASE)
            if feasible_false:
                is_feasible = False
            elif feasible_true:
                is_feasible = True
            else:
                # Default to False if unclear (conservative)
                is_feasible = False
    
    # Extract confidence
    confidence = None
    confidence_match = re.search(r'"confidence"\s*:\s*([0-9.]+)', text, re.IGNORECASE)
    if confidence_match:
        confidence = float(confidence_match.group(1))
    else:
        # Try without quotes
        confidence_match = re.search(r'confidence\s*:\s*([0-9.]+)', text, re.IGNORECASE)
        if confidence_match:
            confidence = float(confidence_match.group(1))
        else:
            # Default based on feasibility
            confidence = 0.3 if is_feasible else 0.2
    
    # Extract reasoning - handle multiline, newlines after quote, etc.
    reasoning = None
    # Try pattern that handles newline immediately after opening quote: "reasoning": "\nText..."
    # This matches: "reasoning": " (with optional newline) then captures until closing quote
    reasoning_match = re.search(r'"reasoning"\s*:\s*"\s*\n?\s*([^"]*?)"(?=\s*[,}])', text, re.DOTALL)
    if reasoning_match:
        reasoning = reasoning_match.group(1).strip()
    else:
        # Try standard JSON pattern (no newline after quote)
        reasoning_match = re.search(r'"reasoning"\s*:\s*"([^"]+)"', text, re.DOTALL)
        if reasoning_match:
            reasoning = reasoning_match.group(1)
        else:
            # Try with triple quotes
            reasoning_match = re.search(r'"reasoning"\s*:\s*"""([^"]*?)"""', text, re.DOTALL)
            if reasoning_match:
                reasoning = reasoning_match.group(1).strip()
            else:
                # Try multiline - find "reasoning": and take everything until next field or closing brace
                # This handles unclosed quotes
                reasoning_match = re.search(r'"reasoning"\s*:\s*["\']?\s*\n?\s*([^"]*?)(?=\s*"[a-z_]+\s*:\s*|\s*[},])', text, re.DOTALL | re.IGNORECASE)
                if reasoning_match:
                    reasoning = reasoning_match.group(1).strip()
                    # Clean up common issues
                    reasoning = re.sub(r'^["\']+|["\']+$', '', reasoning)  # Remove surrounding quotes
                else:
                    # Just take a chunk of text that mentions reasoning
                    reasoning_match = re.search(r'reasoning[^:]*:\s*(.{100,500})', text, re.DOTALL | re.IGNORECASE)
                    if reasoning_match:
                        reasoning = reasoning_match.group(1).strip()[:500]
                    else:
                        reasoning = f"Extracted from LLM response: {text[:400]}"
    
    # Clean up reasoning
    reasoning = reasoning.replace('\n', ' ').replace('\r', ' ').replace('\t', ' ')
    reasoning = ' '.join(reasoning.split())  # Normalize whitespace
    
    # Extract estimated_tokens (REQUIRED field)
    estimated_tokens = None
    # Try with quotes first
    tokens_match = re.search(r'"estimated_tokens"\s*:\s*([0-9]+|null)', text, re.IGNORECASE)
    if tokens_match:
        token_val = tokens_match.group(1).lower()
        if token_val != 'null':
            estimated_tokens = int(token_val)
    else:
        # Try without quotes
        tokens_match = re.search(r'estimated_tokens\s*:\s*([0-9]+|null)', text, re.IGNORECASE)
        if tokens_match:
            token_val = tokens_match.group(1).lower()
            if token_val != 'null':
                estimated_tokens = int(token_val)
        else:
            # Try to find any number near "tokens"
            tokens_match = re.search(r'tokens[^:]*:\s*([0-9]+)', text, re.IGNORECASE)
            if tokens_match:
                estimated_tokens = int(tokens_match.group(1))
    
    # Extract risks
    risks = []
    risks_match = re.search(r'"risks"\s*:\s*\[(.*?)\]', text, re.DOTALL)
    if risks_match:
        risks_str = risks_match.group(1)
        risk_items = re.findall(r'"([^"]+)"', risks_str)
        if risk_items:
            risks = risk_items
    if not risks:
        risks = ["Extracted via text parsing"]
    
    return {
        "is_feasible": is_feasible,
        "confidence": confidence,
        "reasoning": reasoning,
        "estimated_tokens": estimated_tokens,
        "risks": risks
    }


def _simple_feasibility_check(job: Dict) -> Dict:
    """
    Simple heuristic-based feasibility check (fallback when LLM unavailable).
    """
    title = job.get('title', '').lower()
    description = job.get('description', '').lower()
    budget = job.get('budget', '')
    status = job.get('status', '')
    
    # Basic heuristics
    is_feasible = True
    risks = []
    confidence = 0.5
    
    # Check if already awarded
    if status.lower() == 'awarded':
        is_feasible = False
        risks.append("Job already awarded to someone else")
        confidence = 1.0
    
    # Check for clear requirements
    if not description and not job.get('requirements'):
        risks.append("Unclear requirements")
        confidence = 0.3
    
    # Check budget presence
    if not budget:
        risks.append("No budget information")
        confidence = 0.4
    
    reasoning = "Basic heuristic check performed. Install tzafon for LLM-based assessment."
    if risks:
        reasoning += f" Risks identified: {', '.join(risks)}"
    
    return {
        "is_feasible": is_feasible,
        "confidence": confidence,
        "reasoning": reasoning,
        "estimated_hours": None,
        "risks": risks
    }


def check_all_jobs_feasibility(jobs: List[Dict], save_llm_outputs: bool = True) -> List[Dict]:
    """
    Check feasibility for all jobs.
    
    Args:
        jobs: List of job dictionaries
        save_llm_outputs: Whether to save all LLM responses to a file
        
    Returns:
        List of jobs with added 'feasibility' field
    """
    results = []
    llm_outputs = []
    
    for i, job in enumerate(jobs, 1):
        print(f"  Checking job {i}/{len(jobs)}: {job.get('title', 'Unknown')[:50]}...")
        feasibility = check_job_feasibility(job)
        job_with_feasibility = job.copy()
        job_with_feasibility['feasibility'] = feasibility
        results.append(job_with_feasibility)
        
        # Store LLM output for logging
        if 'llm_response' in feasibility:
            llm_outputs.append({
                'job_title': job.get('title', 'Unknown'),
                'job_id': i,
                'prompt': feasibility.get('llm_prompt', ''),
                'response': feasibility.get('llm_response', ''),
                'parsed_result': feasibility
            })
    
    # Save all LLM outputs to a file
    if save_llm_outputs and llm_outputs:
        output_dir = Path("data/llm_outputs")
        output_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_file = output_dir / f"feasibility_assessments_{timestamp}.json"
        
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump({
                'timestamp': datetime.now().isoformat(),
                'total_jobs': len(jobs),
                'assessments': llm_outputs
            }, f, indent=2, ensure_ascii=False)
        
        print(f"\n  💾 All LLM outputs saved to: {output_file}")
    
    return results


def filter_feasible_jobs(jobs_with_feasibility: List[Dict], min_confidence: float = 0.5) -> List[Dict]:
    """
    Filter jobs to only include feasible ones.
    
    Args:
        jobs_with_feasibility: List of jobs with feasibility assessments
        min_confidence: Minimum confidence threshold
        
    Returns:
        List of feasible jobs
    """
    feasible = []
    for job in jobs_with_feasibility:
        feasibility = job.get('feasibility', {})
        if (feasibility.get('is_feasible', False) and 
            feasibility.get('confidence', 0) >= min_confidence):
            feasible.append(job)
    
    return feasible
