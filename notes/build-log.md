# Build log

Append-only. Two kinds of entry: assumptions made where the plan was silent, and
a line at each pass boundary. Not a specification, and not authority over
`spec/optica-plan-v1-core.md`.

This file is the reason a mid-build gap does not need a hard stop. If an
assumption is not written here, it was made silently — which is the one outcome
the gap rule exists to prevent.

## Assumption entries

```
### <short name>
**Pass:** N   **Date:** YYYY-MM-DD   **Where:** path/to/file.py:function
**Missing:** what the plan does not say
**Assumed:** what was done instead
**Why:** the reasoning, including any alternative rejected
**Reversible?** what would have to change if this is overruled
```

## Pass boundary entries

```
### Pass N — closed
**Date:** YYYY-MM-DD
**Built:** modules completed
**Milestone:** the pass's "done when" condition, and whether it was met
**Left open:** anything deferred, and to which pass
**Assumptions logged this pass:** count, with names
```

---
