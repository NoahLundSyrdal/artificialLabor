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
from text_to_json import convert_text_to_json
from feasibility_checker import check_all_jobs_feasibility, filter_feasible_jobs


def main():
    """Run the main pipeline."""
    print("=" * 60)
    print("Artificial Labor Pipeline")
    print("=" * 60)
    
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
        print(f"   Title: {first_job['title']}")
        print(f"   Status: {first_job['status']}")
        print(f"   Budget: {first_job['budget']}")
        print(f"   Description preview: {first_job['description'][:100]}..." if len(first_job['description']) > 100 else f"   Description: {first_job['description']}")
    
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
        if feasibility.get('estimated_hours'):
            print(f"   Estimated hours: {feasibility.get('estimated_hours')}")
        if feasibility.get('risks'):
            print(f"   Risks: {', '.join(feasibility.get('risks', [])[:3])}")
    
    # Store data for next pipeline steps
    # TODO: Step 3 - Cost benefit forecasting
    # TODO: Step 4 - Actually doing the work
    
    print("\n" + "=" * 60)
    print("Step 2 complete. Ready for next pipeline steps.")
    print("=" * 60)
    
    return data


if __name__ == "__main__":
    data = main()
