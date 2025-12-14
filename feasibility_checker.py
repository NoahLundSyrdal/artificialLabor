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


def _call_local_llm(prompt: str) -> str:
    """
    Call local LLM (LM Studio) using the LLM client.
    
    Args:
        prompt: The prompt to send to the LLM
        
    Returns:
        Response text from the LLM
    """
    llm = get_llm_client()
    messages = [{"role": "user", "content": prompt}]
    return llm.chat(messages, temperature=0.7, max_tokens=1000)


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
        - estimated_hours: int (if feasible)
        - risks: list of potential issues
    """
    try:
        # Build open-ended prompt for AI feasibility assessment
        job_details = f"""Title: {job.get('title', 'N/A')}
Status: {job.get('status', 'N/A')}
Budget: {job.get('budget', 'N/A')}
Description: {job.get('description', 'N/A')}
Requirements: {', '.join(job.get('requirements', [])) if job.get('requirements') else 'N/A'}
Deliverables: {', '.join(job.get('deliverables', [])) if job.get('deliverables') else 'N/A'}"""
        
        prompt = f"""Look at this job posting and critically assess whether it's feasible to complete using AI. Be realistic and conservative - many jobs require human judgment, creativity, or physical presence that AI cannot provide.

{job_details}

Think carefully about:
- What specific tasks need to be done?
- Can AI actually perform these tasks autonomously?
- Are there human elements required (judgment, creativity, communication, physical presence)?
- What are the real limitations and barriers?
- Would this require human oversight or intervention?

Be critical: if the job requires human judgment, creativity, communication skills, physical presence, or domain expertise that AI lacks, mark it as NOT feasible.

Provide your assessment as JSON:
{{
  "is_feasible": true or false,
  "confidence": 0.0-1.0,
  "reasoning": "detailed explanation of why it is or isn't feasible with AI",
  "estimated_hours": number or null,
  "risks": ["list", "of", "challenges"]
}}

IMPORTANT: Your response must be valid JSON only. Rules:
- All string values must be in double quotes
- No newlines or control characters inside string values (use \\n for newlines)
- No markdown code blocks
- No text before or after the JSON

Respond with ONLY the JSON object, nothing else.
"""
        
        # Call local LLM
        response_text = _call_local_llm(prompt)
        
        # Log the raw LLM response (truncated for console)
        response_preview = response_text[:300] + "..." if len(response_text) > 300 else response_text
        print(f"    [LLM Response]: {response_preview}")
        
        # Parse JSON response
        import re
        
        # Remove markdown code blocks if present
        cleaned_response = response_text.strip()
        
        # Remove ```json or ``` at start and end
        if cleaned_response.startswith('```'):
            # Remove opening ```json or ```
            cleaned_response = re.sub(r'^```(?:json)?\s*\n?', '', cleaned_response, flags=re.MULTILINE)
            # Remove closing ```
            cleaned_response = re.sub(r'\n?\s*```\s*$', '', cleaned_response, flags=re.MULTILINE)
        
        cleaned_response = cleaned_response.strip()
        
        # Try to extract JSON from response - look for the JSON object
        # Use a more robust approach: find the first { and try to parse incrementally
        json_match = re.search(r'\{[\s\S]*\}', cleaned_response)
        if json_match:
            json_str = json_match.group()
            try:
                result = json.loads(json_str)
                print(f"    [✓ Parsed JSON successfully]")
            except json.JSONDecodeError as e:
                print(f"    [JSON Parse Error]: {str(e)[:100]}")
                print(f"    [Attempting to fix common issues...]")
                # Try to fix common JSON issues
                
                # Fix 1: Remove trailing commas before } or ]
                json_str = re.sub(r',\s*}', '}', json_str)
                json_str = re.sub(r',\s*]', ']', json_str)
                
                # Fix 2: Fix unquoted string values (common issue: "reasoning": value without quotes)
                # Pattern: "reasoning":\s*([^",}\]]+?)(?=\s*[,}\]])
                def fix_unquoted_reasoning(match):
                    value = match.group(1).strip()
                    # Replace newlines with spaces and escape quotes
                    value = value.replace('\n', ' ').replace('\r', ' ').replace('\t', ' ')
                    value = value.replace('"', '\\"')
                    # Remove multiple spaces
                    value = ' '.join(value.split())
                    return f'"reasoning": "{value}"'
                
                json_str = re.sub(r'"reasoning"\s*:\s*([^",}\]]+?)(?=\s*[,}\]])', 
                                 fix_unquoted_reasoning, 
                                 json_str, flags=re.DOTALL)
                
                # Fix 3: Manually escape control characters in JSON strings
                # This is a simple state machine to find and fix string values
                fixed_json = []
                in_string = False
                escape_next = False
                
                for i, char in enumerate(json_str):
                    if escape_next:
                        fixed_json.append(char)
                        escape_next = False
                        continue
                    
                    if char == '\\':
                        escape_next = True
                        fixed_json.append(char)
                        continue
                    
                    if char == '"':
                        in_string = not in_string
                        fixed_json.append(char)
                        continue
                    
                    if in_string:
                        # Inside a string - escape control characters
                        if ord(char) < 32:  # Control character
                            if char == '\n':
                                fixed_json.append('\\n')
                            elif char == '\r':
                                fixed_json.append('\\r')
                            elif char == '\t':
                                fixed_json.append('\\t')
                            else:
                                fixed_json.append(f'\\u{ord(char):04x}')
                        else:
                            fixed_json.append(char)
                    else:
                        fixed_json.append(char)
                
                json_str = ''.join(fixed_json)
                
                try:
                    result = json.loads(json_str)
                    print(f"    [✓ Fixed control chars and parsed JSON]")
                except json.JSONDecodeError:
                    # Last resort: use fallback parser
                    print(f"    [Using fallback parser]")
                    result = _parse_text_response(response_text)
                
                try:
                    result = json.loads(json_str)
                    print(f"    [✓ Fixed and parsed JSON]")
                except json.JSONDecodeError as e2:
                    # If still fails, try to extract fields manually using improved parser
                    print(f"    [Using improved fallback parser]")
                    result = _parse_text_response(response_text)
        else:
            print(f"    [Warning]: No JSON found in response, using fallback parser")
            result = _parse_text_response(response_text)
        
        # Ensure all required fields
        assessment = {
            "is_feasible": bool(result.get("is_feasible", False)),
            "confidence": float(result.get("confidence", 0.5)),
            "reasoning": str(result.get("reasoning", response_text[:500])),
            "estimated_hours": result.get("estimated_hours"),
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
            "estimated_hours": None,
            "risks": ["Assessment error occurred"],
            "llm_prompt": "",
            "llm_response": ""
        }


def _parse_text_response(text: str) -> Dict:
    """Parse a text response into structured format when JSON parsing fails."""
    import re
    text_lower = text.lower()
    
    # Try to extract key information from text
    # Look for explicit "is_feasible": true/false patterns
    feasible_match = re.search(r'"is_feasible"\s*:\s*(true|false)', text, re.IGNORECASE)
    confidence_match = re.search(r'"confidence"\s*:\s*([0-9.]+)', text, re.IGNORECASE)
    
    if feasible_match:
        is_feasible = feasible_match.group(1).lower() == 'true'
    else:
        # Be more conservative - default to NOT feasible if unclear
        is_feasible = False
        # Only mark feasible if very clear positive indicators
        if (("feasible" in text_lower and "not" not in text_lower[:text_lower.find("feasible")+20] and 
             "unfeasible" not in text_lower) and 
            ("false" not in text_lower[:text_lower.find("feasible")+50])):
            is_feasible = True
    
    if confidence_match:
        confidence = float(confidence_match.group(1))
    else:
        # Lower confidence for fallback parsing
        confidence = 0.3 if is_feasible else 0.2
    
    # Try to extract reasoning
    reasoning_match = re.search(r'"reasoning"\s*:\s*"([^"]+)"', text, re.DOTALL)
    if reasoning_match:
        reasoning = reasoning_match.group(1)
    else:
        reasoning = f"Fallback parsing used. Could not extract structured JSON. Original response preview: {text[:300]}"
    
    # Try to extract risks
    risks_match = re.search(r'"risks"\s*:\s*\[(.*?)\]', text, re.DOTALL)
    risks = ["Could not parse structured response from LLM"]
    if risks_match:
        risks_str = risks_match.group(1)
        # Try to extract individual risk items
        risk_items = re.findall(r'"([^"]+)"', risks_str)
        if risk_items:
            risks = risk_items
    
    return {
        "is_feasible": is_feasible,
        "confidence": confidence,
        "reasoning": reasoning,
        "estimated_hours": None,
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
