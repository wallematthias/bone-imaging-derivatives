# Changelog

## 0.1.7 - 2026-10-02

- Archive completed rename manifests after undo, restore original sidecar paths, and preflight collisions so rename/undo/rename is repeatable without losing the audit trail.
- Use AIM patient-header identifiers for subject grouping of native Scanco D-number scan filenames, while retaining explicit anonymized/path/sidecar identifiers. This header heuristic still needs confirmation on collaborator exports.
