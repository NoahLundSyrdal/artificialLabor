#!/usr/bin/env python3
"""
Proposal generator for feasible jobs.
Generates client-facing proposals using LLM based on job details and feasibility assessment.
"""

from typing import Dict, List
import json
from datetime import datetime
from pathlib import Path
from llm_client import get_llm_client


def generate_proposal(job: Dict) -> Dict:
    """
    Generate a client-facing proposal for a feasible job.
    
    Args:
        job: Job dictionary with title, description, requirements, deliverables, 
             budget, payment_terms, and feasibility assessment
        
    Returns:
        Dictionary with proposal content
    """
    feasibility = job.get('feasibility', {})
    
    # Build job summary for proposal
    job_summary = f"""Job Title: {job.get('title', 'N/A')}
Description: {job.get('description', 'N/A')}
Requirements: {', '.join(job.get('requirements', [])) if job.get('requirements') else 'N/A'}
Deliverables: {', '.join(job.get('deliverables', [])) if job.get('deliverables') else 'N/A'}
Budget: {job.get('budget', 'N/A')}
Payment Terms: {job.get('payment_terms', 'N/A')}"""
    
    # Load proposal template for reference
    template_path = Path(__file__).parent / "schemas" / "proposal_template.json"
    template_info = ""
    try:
        with open(template_path, 'r') as f:
            template = json.load(f)
            template_info = f"\n\nFollow this proposal structure:\n{json.dumps(template['fields'], indent=2)}"
    except FileNotFoundError:
        pass
    
    prompt = f"""You are generating a professional client-facing proposal for a freelancing job.

{job_summary}{template_info}

Generate a proposal that:
- Shows understanding of the requirements
- Outlines your approach
- Lists deliverables clearly
- Addresses timeline if mentioned
- Matches pricing to client's budget/payment terms
- Is professional and concise

Return ONLY valid JSON (no markdown, no code fences, no extra text):
{{
  "greeting": "Professional greeting addressing the client",
  "understanding": "Brief statement showing you understand the project",
  "approach": "1-2 sentences describing your approach",
  "deliverables": ["list", "of", "specific", "deliverables"],
  "timeline": "Estimated completion time or 'To be discussed'",
  "pricing": "Pricing proposal based on budget/payment terms",
  "next_steps": "What happens next (e.g., 'Ready to start immediately')"
}}

CRITICAL: Output ONLY the JSON object. No markdown fences. No newlines inside string values.
"""
    
    llm = get_llm_client()
    messages = [{"role": "user", "content": prompt}]
    
    try:
        response_text = llm.chat(messages, temperature=0.7, max_tokens=500)
        
        # Parse JSON response
        import re
        cleaned_response = response_text.strip()
        
        # Remove markdown code blocks
        if cleaned_response.startswith('```'):
            cleaned_response = re.sub(r'^```(?:json)?\s*\n?', '', cleaned_response, flags=re.MULTILINE)
            cleaned_response = re.sub(r'\n?\s*```\s*$', '', cleaned_response, flags=re.MULTILINE)
        
        cleaned_response = cleaned_response.strip()
        
        # Extract JSON using brace-balanced method (reuse from feasibility_checker)
        json_str = _extract_json_balanced(cleaned_response)
        
        if not json_str:
            # Fallback: create basic proposal
            return {
                "greeting": f"Hello, I'm interested in your {job.get('title', 'project')}.",
                "understanding": f"I understand you need: {job.get('description', 'N/A')}",
                "approach": "I will complete this task using automated tools and deliver high-quality results.",
                "deliverables": job.get('deliverables', []),
                "timeline": "To be discussed",
                "pricing": job.get('payment_terms', job.get('budget', 'To be discussed')),
                "next_steps": "Ready to start immediately"
            }
        
        # Quick fixes
        json_str = re.sub(r'"""', '"', json_str)
        json_str = re.sub(r"'''", "'", json_str)
        json_str = re.sub(r',\s*}', '}', json_str)
        json_str = re.sub(r',\s*]', ']', json_str)
        
        try:
            proposal = json.loads(json_str)
        except json.JSONDecodeError:
            # Fallback
            proposal = {
                "greeting": f"Hello, I'm interested in your {job.get('title', 'project')}.",
                "understanding": f"I understand you need: {job.get('description', 'N/A')}",
                "approach": "I will complete this task using automated tools.",
                "deliverables": job.get('deliverables', []),
                "timeline": "To be discussed",
                "pricing": job.get('payment_terms', job.get('budget', 'N/A')),
                "next_steps": "Ready to start immediately"
            }
        
        # Ensure all fields
        proposal.setdefault("greeting", f"Hello, I'm interested in your {job.get('title', 'project')}.")
        proposal.setdefault("understanding", f"I understand you need: {job.get('description', 'N/A')}")
        proposal.setdefault("approach", "I will complete this task efficiently.")
        proposal.setdefault("deliverables", job.get('deliverables', []))
        proposal.setdefault("timeline", "To be discussed")
        proposal.setdefault("pricing", job.get('payment_terms', job.get('budget', 'N/A')))
        proposal.setdefault("next_steps", "Ready to start immediately")
        
        # Store raw outputs
        proposal['llm_prompt'] = prompt
        proposal['llm_response'] = response_text
        
        return proposal
        
    except Exception as e:
        # Fallback proposal on error
        return {
            "greeting": f"Hello, I'm interested in your {job.get('title', 'project')}.",
            "understanding": f"I understand you need: {job.get('description', 'N/A')}",
            "approach": "I will complete this task using automated tools.",
            "deliverables": job.get('deliverables', []),
            "timeline": "To be discussed",
            "pricing": job.get('payment_terms', job.get('budget', 'N/A')),
            "next_steps": "Ready to start immediately",
            "error": str(e)
        }


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


def generate_proposals_for_feasible_jobs(jobs: List[Dict], min_confidence: float = 0.5) -> List[Dict]:
    """
    Generate proposals for all feasible jobs.
    
    Args:
        jobs: List of jobs with feasibility assessments
        min_confidence: Minimum confidence threshold for feasibility
        
    Returns:
        List of jobs with added 'proposal' field
    """
    results = []
    proposals_data = []
    
    for i, job in enumerate(jobs, 1):
        feasibility = job.get('feasibility', {})
        
        # Only generate proposals for feasible jobs
        if (feasibility.get('is_feasible', False) and 
            feasibility.get('confidence', 0) >= min_confidence):
            
            print(f"  Generating proposal {i}/{len(jobs)}: {job.get('title', 'Unknown')[:50]}...")
            
            try:
                proposal = generate_proposal(job)
                job_with_proposal = job.copy()
                job_with_proposal['proposal'] = proposal
                results.append(job_with_proposal)
                
                # Store for logging
                proposals_data.append({
                    'job_title': job.get('title', 'Unknown'),
                    'job_id': i,
                    'proposal': proposal
                })
                
                print(f"    [✓ Proposal generated]")
            except Exception as e:
                print(f"    [Error generating proposal]: {e}")
                results.append(job)
        else:
            # Keep non-feasible jobs without proposals
            results.append(job)
    
    # Save all proposals to a file
    if proposals_data:
        output_dir = Path("data/llm_outputs")
        output_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_file = output_dir / f"proposals_{timestamp}.json"
        
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump({
                'timestamp': datetime.now().isoformat(),
                'total_proposals': len(proposals_data),
                'proposals': proposals_data
            }, f, indent=2, ensure_ascii=False)
        
        print(f"\n  💾 All proposals saved to: {output_file}")
    
    return results
