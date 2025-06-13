# Prompt Engineering Log - Event Retrieval System

## Quick Reference

- **Last Updated:** 2025-01-09
- **Total Issues:** 6
- **Resolved:** 0
- **In Progress:** 6
- **Critical:** 3

---

## Issue Categories

### 🔤 TYPO_HANDLING

**Description:** System fails to handle common typos and misspellings

#### Issue #TH-001: Flight typo not recognized

- **Date Created:** 2025-01-09
- **Status:** 🔴 Open
- **Priority:** High
- **Iteration:** 1

**User Input:**

```
"when is my lfight to sf"
```

**Current Response:**

```
I don't see any events related to 'lfight' on June 11 to June 18, 2025. Your schedule appears to be clear for this search.
```

**Expected Response:**

```
Sure thing! Here are the events for June 12, 2025:
- Flight to San Francisco, CA (F9 4593) from 06:08 PM to 07:43 PM. Let me know if you need more details or assistance with anything else!
```

**Root Cause:** No fuzzy matching or typo correction in search logic

**Proposed Solutions:**

- [ ] Add Levenshtein distance checking for common words
- [ ] Implement phonetic matching (soundex/metaphone)
- [ ] Create common typo dictionary

---

### 🚫 UNSUPPORTED_INTENTS

**Description:** System doesn't handle certain user intent types

#### Issue #UI-001: Availability check not supported

- **Date Created:** 2025-01-09
- **Status:** 🔴 Open
- **Priority:** Critical
- **Iteration:** 1

**User Input:**

```
"am i free on june 29?"
```

**Current Response:**

```
Error: I'm not sure how to handle that request. Intent 'availability_check' is not supported.
```

**Expected Response:**

```
Yes, you're free on June 29, 2025. No events scheduled for that day.
```

**Root Cause:** Missing availability_check intent handler

**Proposed Solutions:**

- [ ] Implement availability_check intent
- [ ] Add free/busy time analysis
- [ ] Handle date range availability queries

---

### 🔍 SEARCH_MATCHING

**Description:** Search logic fails to match related terms

#### Issue #SM-001: GRE study search mismatch

- **Date Created:** 2025-01-09
- **Status:** 🔴 Open
- **Priority:** Medium
- **Iteration:** 1

**User Input:**

```
"when does my gre study starts?"
```

**Current Response:**

```
I don't see any events related to 'gre study starts, study, starts' on June 11 to June 18, 2025. Your schedule appears to be clear for this search.
```

**Expected Response:**

```
Sure thing! Here are the events for June 12, 2025:
- Grad prep + essay/tasks from 01:45 PM to 03:45 PM. Let me know if you need more details or assistance with anything else!
```

**Root Cause:** "Grad prep" not matching "gre study" - insufficient semantic matching

**Proposed Solutions:**

- [ ] Add synonym mapping (GRE ↔ Grad prep)
- [ ] Implement semantic similarity scoring
- [ ] Create domain-specific keyword expansion

---

### ⏰ TIME_PARSING

**Description:** System fails to parse informal time formats

#### Issue #TP-001: Informal time format rejection

- **Date Created:** 2025-01-09
- **Status:** 🔴 Open
- **Priority:** High
- **Iteration:** 1

**User Input:**

```
"i need you to change that event to 2pm"
```

**Current Response:**

```
Error: Failed to create event: Invalid isoformat string: '2:00 PM'
```

**Expected Response:**

```
Event updated successfully. The event is now scheduled for 2:00 PM.
```

**Root Cause:** Time parser doesn't handle informal formats like "2pm"

**Proposed Solutions:**

- [ ] Add dateutil.parser for flexible time parsing
- [ ] Create time format normalization layer
- [ ] Handle common informal time expressions

---

### ✏️ EVENT_MODIFICATION

**Description:** Event creation and modification failures

#### Issue #EM-001: Birthday event timing failure

- **Date Created:** 2025-01-09
- **Status:** 🔴 Open
- **Priority:** Medium
- **Iteration:** 1

**User Input:**

```
"time the birthday block at 1pm"
```

**Current Response:**

```
Error: Failed to create event:
```

**Expected Response:**

```
Event updated successfully. "MY BD" is now scheduled for 1:00 PM on December 17, 2025.
```

**Root Cause:** Event modification logic broken for existing events

**Proposed Solutions:**

- [ ] Fix event update/modification endpoint
- [ ] Add better error handling and messages
- [ ] Implement event search before modification

---

### 🎯 CONTEXT_UNDERSTANDING

**Description:** System loses context or fails to understand references

#### Issue #CU-001: Event reference context loss

- **Date Created:** 2025-01-09
- **Status:** 🔴 Open
- **Priority:** Medium
- **Iteration:** 1

**User Input:**

```
"i cant see the block you made on dec 17" (after creating "MY BD" event)
```

**Current Response:**

```
On Wednesday, December 17, 2025, you have the following events:
- Shadi Bitaraf's birthday (Time not specified)  // ← This should be "MY BD"
- 3-4 Leet Q from 09:00 AM to 12:00 PM
- job app from 12:00 PM to 01:15 PM. Enjoy your day!
```

**Expected Response:**

```
On Wednesday, December 17, 2025, you have the following events:
- MY BD (Time not specified)
- 3-4 Leet Q from 09:00 AM to 12:00 PM
- job app from 12:00 PM to 01:15 PM. Enjoy your day!
```

**Root Cause:** Event title got changed/overridden during creation

**Proposed Solutions:**

- [ ] Preserve exact user-specified event titles
- [ ] Add event creation confirmation
- [ ] Fix title sanitization logic

---

## Iteration Tracking Template

When working on an issue, add iteration details:

```markdown
### Iteration 2 - [Date]

**Changes Made:**

- Specific changes to prompt/logic

**Test Results:**

- Input: "test case"
- Output: "actual result"
- Success: ✅/❌

**Notes:**

- What worked/didn't work
- Next steps
```

---

## Prompt Versions

### Current Base Prompt v1.0

```
[Your current event retrieval prompt here]
```

### Proposed Changes

- [ ] Add typo tolerance instructions
- [ ] Include availability check handling
- [ ] Add semantic matching guidelines
- [ ] Specify flexible time parsing requirements

---

## Testing Checklist

### Typo Handling

- [ ] "lfight" → "flight"
- [ ] "meting" → "meeting"
- [ ] "apointment" → "appointment"

### Time Formats

- [ ] "2pm" → "2:00 PM"
- [ ] "quarter past 3" → "3:15 PM"
- [ ] "noon" → "12:00 PM"

### Availability Queries

- [ ] "am i free on [date]"
- [ ] "do i have anything on [date]"
- [ ] "what's my schedule like on [date]"

### Semantic Matching

- [ ] "GRE study" → "Grad prep"
- [ ] "workout" → "gym"
- [ ] "lunch meeting" → "lunch"

---

## Progress Metrics

| Week | Issues Opened | Issues Resolved | Success Rate |
| ---- | ------------- | --------------- | ------------ |
| W1   | 6             | 0               | 0%           |
| W2   |               |                 |              |
| W3   |               |                 |              |
