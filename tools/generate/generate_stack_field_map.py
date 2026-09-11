#!/usr/bin/env python3
"""Regenerate docs/STACK_FIELD_MAP.md from the reviewed protocol layouts and the generated contracts."""
from pathlib import Path as _ProjectPath
import sys as _project_sys
_PROJECT_ROOT=_ProjectPath(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in _project_sys.path:_project_sys.path.insert(0,str(_PROJECT_ROOT))
import sys
from framework.stack_field_map import FIELD_MAP_DOC, field_map_document

ROOT = _PROJECT_ROOT
OUTPUT_FILE = FIELD_MAP_DOC
FIXED_OUTPUTS = (OUTPUT_FILE,)


def main() -> None:
    text = field_map_document(ROOT)
    target = ROOT / OUTPUT_FILE
    if "--check" in sys.argv:
        if not target.is_file() or target.read_text() != text:
            raise SystemExit(f"{OUTPUT_FILE} is stale; run tools/generate/generate_stack_field_map.py")
        print(f"{OUTPUT_FILE} is current")
        return
    target.write_text(text)
    print(f"Generated {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
