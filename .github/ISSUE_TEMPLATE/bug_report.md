---
name: Bug report
about: Something is broken or produces wrong results
title: ""
labels: bug
assignees: ""
---

## Description

A clear, concise description of the bug. If this is a *scientific
correctness* issue (wrong NDVI values, masking errors, selection surprises),
say so explicitly and link the relevant section of
`docs/scientific-methodology.md`.

## Steps to reproduce

1.
2.
3.

For analysis issues, include the AOI bbox, date range, cloud threshold, and
scene limit — or attach the provenance document
(`GET /api/v1/analyses/{id}/provenance`), which contains all of them.

## Expected behavior

What you expected to happen.

## Actual behavior

What actually happened. For API errors, paste the full
`application/problem+json` body (it is sanitized by design and safe to
share); include the correlation id for 500s.

## Logs / output

```
Paste relevant logs, tracebacks, or CLI output here.
```

## Environment

- Where: local (`make dev`) / Azure dev deployment / notebook
- OS:
- Commit SHA (`git rev-parse HEAD`):
- For notebook issues: Python version and `uv.lock` state (clean checkout?)
