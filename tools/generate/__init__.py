"""Code generators. Each emits IC10 source or generated documentation from a
JSON source of truth under data/, and regeneration must be byte-stable.

Running a generator writes those outputs; importing one must not. Keep the whole
body in `main()` -- `ensure_coordination_programs()` and the catalog writers are
reached from there, never from module level.
"""
