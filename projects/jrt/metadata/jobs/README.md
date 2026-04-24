# Job Records

This directory stores one JSON job record per autonomous run.

## Requirements

- Every autonomous workflow run **must** emit exactly one job file in this directory.
- Each job file **must** validate against `projects/jrt/metadata/schema/media_job.schema.json` before downstream processing can begin.
- Recommended filename pattern: `<created_at>__<job_id>.json` (UTC ISO-8601 basic timestamp).
