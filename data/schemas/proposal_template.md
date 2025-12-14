# Proposal Template

This template guides the structure of client-facing proposals. The LLM assessor uses this as a reference for generating proposals.

---

## Template Structure

```markdown
# Proposal: {{title}}

## Understanding

{{1-2 sentences demonstrating comprehension of the client's core need. Be specific to their request, not generic. Reference specific details from their posting.}}

## Approach

- {{Step 1: How you'll handle the primary requirement}}
- {{Step 2: How you'll handle secondary requirements}}
- {{Step 3: Quality assurance / verification step}}
- {{Step 4: Delivery format and handoff}}

## Deliverables

- {{Deliverable 1 - match client's stated deliverables exactly}}
- {{Deliverable 2}}
- {{Deliverable 3 if applicable}}

## Timeline

{{Realistic time estimate. Be specific: "Within 24 hours" or "2-3 business days" not vague.}}

## Investment

**{{Amount}} {{Currency}}** {{payment_type}}

{{If fixed price}}: Fixed price for complete delivery as specified above.
{{If hourly}}: Estimated {{X}} hours at {{rate}}/hour.

## Why Choose Me

{{1-2 sentences on specific relevant expertise. Mention specific tools or similar work. Avoid generic claims like "I'm detail-oriented." Be concrete.}}

---
Ready to begin immediately upon acceptance.
```

---

## Guidelines for Proposal Writing

### DO:
- Mirror the client's language and terminology
- Be specific about what you'll deliver
- Show you read their requirements carefully
- Give concrete timelines
- Price within their stated budget (aim for middle-to-high end)
- Keep it concise (under 200 words)

### DON'T:
- Use filler phrases ("I would be happy to...")
- Make generic claims ("I'm a hard worker")
- Overpromise on timeline
- Underbid significantly (signals low quality)
- Write long paragraphs
- Use excessive formatting or emojis

### Tone:
- Professional but not stiff
- Confident but not arrogant
- Concise but not curt
- Specific but not overwhelming

---

## Example Proposal

```markdown
# Proposal: Excel Sheet Modification

## Understanding

You need your CSV cleaned up: adding @ prefixes to Column A, removing duplicates, and sorting by text length while keeping all columns aligned.

## Approach

- Import CSV and add @ prefix to all Column A values
- Identify and remove duplicate rows (post-prefix)
- Sort entire dataset by Column A length (shortest first)
- Verify column alignment and special character preservation
- Export as clean CSV

## Deliverables

- Single CSV file with @ prefixes, duplicates removed, sorted by length
- All original columns preserved and aligned

## Timeline

Within 2 hours of receiving the file.

## Investment

**$15 USD** - Fixed price

## Why Choose Me

Experienced with CSV/Excel transformations and data cleaning. This is a straightforward task I can complete quickly with Python pandas for accuracy.

---
Ready to begin immediately upon acceptance.
```
