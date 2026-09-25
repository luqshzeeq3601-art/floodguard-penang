"""Raw ingestion: preserve source payloads immutably and emit source-faithful raw records.

Design: docs/RAW_INGESTION_DESIGN.md. This layer never cleans, imputes, converts units or
timezones, or deduplicates; it only preserves, parses structure, maps identity and records
provenance. Import submodules directly (this package init stays import-free).
"""
