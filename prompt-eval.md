# Orii — Response Evaluation Framework

Scores real Orii outputs against five criteria, root-causes failures, records the fix. Scaffold only — populate once the pipeline runs end-to-end and produces real output.

## Criteria

| Criterion | What it measures |
|---|---|
| Clear | Easy to parse — not vague, not overly dense |
| Relevant | Answers about the right event(s)/date(s)/person |
| Accurate | Details correct, nothing invented |
| Functional | Runs without errors, returns a complete answer |
| Transparent | States plainly when nothing matched, instead of guessing |

## Test entry template

```
### Test [N] — [label]
**Query:** "..."
**Category:** (from orii-query-handling-test-suite.md)
**Ground truth:** correct answer, based on real calendar data
**Available data:** relevant events in the test calendar

**Output:** what Orii returned

**Scores (1-5):**
| Clear | Relevant | Accurate | Functional | Transparent |
|---|---|---|---|---|
| | | | | |

**Root cause (if failed):**
**Fix:** exact prompt/instruction text changed
**Re-test result:**
```

## Fabrication-risk checklist

Run every prompt revision against these:

- **Zero-result:** does it invent an answer when nothing matched, instead of saying so?
- **Partial-fill:** when structuring/tabulating data, does it invent missing fields instead of leaving them blank?
- **Tone-revision drift:** when a response is rephrased, do facts (frequency, counts, times) stay exact?

## Recency/staleness checklist

- When events conflict (e.g. recurring master vs. modified instance), is the more recently modified one favored?
- Is cached data ever presented as current when it's past the TTL defined in the engineering log?