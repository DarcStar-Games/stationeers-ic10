"""Command-line entrypoints. Nothing here is shipped to a device.

Run them from the repository root: `python3 tools/run_validation.py`. Each puts
the repository root on sys.path and resolves every path against it, so the
working directory does not change what they read or write.

Import a module from here by its package name -- `import tools.build_release`,
never `import build_release`. Running any entry point also leaves its own
directory on sys.path, so the bare name resolves to the same file under a second
module name, and two names mean two module objects with two copies of every
module-level constant. Nothing keeps those copies equal.
`validation/validators/validate_script_headers.py` rejects the bare form here
and equally under `tools/generate/`, `tests/` and `validation/validators/`,
which have no package marker in which to say so.

Importing one is also safe: everything here does its work in `main()` behind
`if __name__ == "__main__"`, so an import defines and never acts. That is
enforced too, and it is why the rule above can be followed without side effects.
"""
