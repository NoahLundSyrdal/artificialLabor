#!/usr/bin/env python3
"""
Main pipeline for artificial labor project.

Pipeline steps:
1. Convert text data to JSON
2. Identify feasible work
3. Cost benefit forecasting
4. Actually doing the work
"""

import json
import shutil
from pathlib import Path
from text_to_json import convert_text_to_json
from feasibility_checker import check_all_jobs_feasibility, filter_feasible_jobs
from proposal_generator import generate_proposals_for_feasible_jobs
from task_executor import execute_all_tasks


def main():
    """Run the main pipeline."""
    print("=" * 60)
    print("Artificial Labor Pipeline")
    print("=" * 60)
    
    # Clear llm_outputs folder at start
    llm_outputs_dir = Path("data/llm_outputs")
    if llm_outputs_dir.exists():
        print("\n[Initialization] Clearing llm_outputs folder...")
        for item in llm_outputs_dir.iterdir():
            if item.is_file():
                item.unlink()
            elif item.is_dir():
                shutil.rmtree(item)
        print("  ✓ Cleared llm_outputs folder")
    
    # Step 1: Convert text to JSON
    print("\n[Step 1] Converting text data to JSON...")
    print("-" * 60)
    
    input_file = "data/handpicked_ads.md"
    data = convert_text_to_json(input_file)
    
    # Display results
    print(f"✓ Source file: {data['metadata']['source_file']}")
    print(f"✓ Total jobs found: {data['metadata']['total_jobs']}")
    
    # Show sample of first job
    if data['jobs']:
        print(f"\n📋 Sample job (first of {len(data['jobs'])}):")
        first_job = data['jobs'][0]
        print(f"   Title: {first_job.get('title', 'N/A')}")
        print(f"   Status: {first_job.get('status', 'N/A')}")
        print(f"   Budget: {first_job.get('budget', 'N/A')}")
        description = first_job.get('description', '')
        if description:
            print(f"   Description preview: {description[:100]}..." if len(description) > 100 else f"   Description: {description}")
        else:
            print(f"   Description: N/A")
    
    # Display full JSON structure (formatted)
    print(f"\n📊 Full JSON structure:")
    print(json.dumps(data, indent=2, ensure_ascii=False)[:2000])  # First 2000 chars
    if len(json.dumps(data, indent=2, ensure_ascii=False)) > 2000:
        print("\n... (truncated, full data available in memory)")
    
    # Step 2: Identify feasible work
    print("\n[Step 2] Checking job feasibility using local LLM (LM Studio)...")
    print("-" * 60)
    
    jobs_with_feasibility = check_all_jobs_feasibility(data['jobs'])
    
    # Update data with feasibility assessments
    data['jobs'] = jobs_with_feasibility
    
    # Filter and display results
    feasible_jobs = filter_feasible_jobs(jobs_with_feasibility, min_confidence=0.5)
    
    print(f"\n✓ Feasibility assessment complete")
    print(f"  Total jobs analyzed: {len(jobs_with_feasibility)}")
    print(f"  Feasible jobs: {len(feasible_jobs)}")
    print(f"  Not feasible: {len(jobs_with_feasibility) - len(feasible_jobs)}")
    
    # Show sample feasibility results
    if jobs_with_feasibility:
        print(f"\n📋 Sample feasibility assessment:")
        sample = jobs_with_feasibility[0]
        feasibility = sample.get('feasibility', {})
        print(f"   Job: {sample.get('title', 'Unknown')}")
        print(f"   Feasible: {feasibility.get('is_feasible', 'N/A')}")
        print(f"   Confidence: {feasibility.get('confidence', 0):.2f}")
        print(f"   Reasoning: {feasibility.get('reasoning', 'N/A')[:150]}...")
        if feasibility.get('estimated_tokens'):
            print(f"   Estimated tokens: {feasibility.get('estimated_tokens')}")
        if feasibility.get('risks'):
            print(f"   Risks: {', '.join(feasibility.get('risks', [])[:3])}")
    
    # Step 3: Generate proposals for feasible jobs
    print("\n[Step 3] Generating proposals for feasible jobs...")
    print("-" * 60)
    
    jobs_with_proposals = generate_proposals_for_feasible_jobs(jobs_with_feasibility, min_confidence=0.5)
    data['jobs'] = jobs_with_proposals
    
    # Count proposals generated
    proposals_count = sum(1 for job in jobs_with_proposals if 'proposal' in job)
    print(f"\n✓ Proposal generation complete")
    print(f"  Proposals generated: {proposals_count}")
    
    # Show sample proposal
    if proposals_count > 0:
        sample_job = next((job for job in jobs_with_proposals if 'proposal' in job), None)
        if sample_job:
            print(f"\n📋 Sample proposal:")
            proposal = sample_job.get('proposal', {})
            print(f"   Job: {sample_job.get('title', 'Unknown')}")
            greeting = str(proposal.get('greeting', 'N/A') or 'N/A')
            approach = str(proposal.get('approach', 'N/A') or 'N/A')
            print(f"   Greeting: {greeting[:80]}..." if len(greeting) > 80 else f"   Greeting: {greeting}")
            print(f"   Approach: {approach[:80]}..." if len(approach) > 80 else f"   Approach: {approach}")
            print(f"   Deliverables: {len(proposal.get('deliverables', []))} items")
    
    # Step 4: Execute feasible tasks
    print("\n[Step 4] Executing feasible tasks...")
    print("-" * 60)
    
    jobs_with_execution = execute_all_tasks(jobs_with_proposals, min_confidence=0.5)
    data['jobs'] = jobs_with_execution
    
    # Count successful executions
    executions_count = sum(1 for job in jobs_with_execution if 'execution' in job)
    successful_count = 0
    for job in jobs_with_execution:
        if 'execution' in job:
            exec_result = job.get('execution', {})
            # Check both possible structures
            exec_info = exec_result.get('execution', {})
            if exec_info.get('success') is True:
                successful_count += 1
    
    print(f"\n✓ Execution complete")
    print(f"  Tasks executed: {executions_count}")
    print(f"  Successful: {successful_count}")
    print(f"  Failed: {executions_count - successful_count}")
    
    # Show sample execution result
    if executions_count > 0:
        sample_job = next((job for job in jobs_with_execution if 'execution' in job), None)
        if sample_job:
            print(f"\n📋 Sample execution result:")
            execution_result = sample_job.get('execution', {})
            exec_info = execution_result.get('execution', {})
            print(f"   Job: {sample_job.get('title', 'Unknown')}")
            print(f"   Status: {execution_result.get('status', 'N/A')}")
            print(f"   Success: {exec_info.get('success', 'N/A')}")
            if exec_info.get('wall_time_seconds'):
                print(f"   Time: {exec_info.get('wall_time_seconds', 0):.1f}s")
            print(f"   Deliverables: {len(execution_result.get('deliverables', []))} items")
    
    print("\n" + "=" * 60)
    print("Pipeline complete! All steps finished.")
    print("=" * 60)
    
    return data


if __name__ == "__main__":
    data = main()
