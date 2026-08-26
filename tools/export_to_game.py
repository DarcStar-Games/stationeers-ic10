#!/usr/bin/env python3
"""Export production IC10 programs into Stationeers' saved-script XML format."""
from __future__ import annotations
from pathlib import Path as _ProjectPath
import sys as _project_sys
_PROJECT_ROOT=_ProjectPath(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in _project_sys.path:_project_sys.path.insert(0,str(_PROJECT_ROOT))
from pathlib import Path
import argparse
import datetime as dt
import json
import re
import sys
import xml.etree.ElementTree as ET
from dataclasses import dataclass

ROOT=_PROJECT_ROOT
XSD_NAMESPACE="http://www.w3.org/2001/XMLSchema"
XSI_NAMESPACE="http://www.w3.org/2001/XMLSchema-instance"
WINDOWS_EPOCH_YEAR=1601
TICKS_PER_SECOND=10_000_000


class ExportError(ValueError):
    pass


@dataclass(frozen=True)
class Program:
    path: Path
    relative: Path
    family: str
    stem: str

    @property
    def title(self):
        return f"{self.family}__{self.stem}"


def discover_programs(root=ROOT):
    source_root=Path(root)/"ic10"
    if not source_root.is_dir():
        raise ExportError(f"IC10 source directory not found: {source_root}")
    programs=[]
    for path in sorted(source_root.rglob("*.ic10")):
        relative=path.relative_to(root)
        if len(relative.parts)!=3:
            raise ExportError(f"production program is not directly inside one family: {relative.as_posix()}")
        programs.append(Program(path,relative,relative.parts[1],path.stem))
    if not programs:
        raise ExportError(f"no production IC10 programs found under {source_root}")
    titles=[program.title for program in programs]
    if len(titles)!=len(set(titles)):
        raise ExportError("family/program titles are not unique")
    return programs


def target_game_version(root=ROOT):
    path=Path(root)/"data/ic10_instruction_set.json"
    try:
        data=json.loads(path.read_text(encoding="utf-8"))
        recorded=data["provenance"]["target_game_build"]
    except (OSError,KeyError,json.JSONDecodeError,TypeError) as exc:
        raise ExportError(f"cannot read target game build from {path}: {exc}") from exc
    match=re.match(r"^(\d+\.\d+\.\d+\.\d+)(?:\s|$)",recorded)
    if not match:
        raise ExportError(f"invalid target game build in {path}: {recorded!r}")
    return match.group(1)


def windows_filetime(when=None):
    value=when or dt.datetime.now(dt.timezone.utc)
    if value.tzinfo is None:
        raise ExportError("export timestamp must be timezone-aware")
    value=value.astimezone(dt.timezone.utc)
    epoch=dt.datetime(WINDOWS_EPOCH_YEAR,1,1,tzinfo=dt.timezone.utc)
    delta=value-epoch
    if delta.days<0:
        raise ExportError("export timestamp predates the Windows FILETIME epoch")
    return ((delta.days*86400+delta.seconds)*TICKS_PER_SECOND+delta.microseconds*10)


def select_programs(programs,all_programs=False,families=(),names=()):
    if all_programs:
        return list(programs)
    if families:
        known={program.family for program in programs}
        unknown=sorted(set(families)-known)
        if unknown:
            raise ExportError(f"unknown deployment family: {', '.join(unknown)}")
        wanted=set(families)
        return [program for program in programs if program.family in wanted]
    if names:
        aliases={}
        for program in programs:
            rel=program.relative.as_posix()
            keys={rel,rel.removeprefix("ic10/"),program.stem,
                  f"{program.family}/{program.stem}",f"{program.family}/{program.stem}.ic10"}
            for key in keys:
                aliases.setdefault(key,[]).append(program)
        selected=[]
        for name in names:
            matches=aliases.get(name,[])
            if not matches:
                raise ExportError(f"unknown IC10 program: {name}")
            if len(matches)>1:
                raise ExportError(f"ambiguous IC10 program name: {name}")
            if matches[0] not in selected:
                selected.append(matches[0])
        return sorted(selected,key=lambda program:program.relative.as_posix())
    raise ExportError("select programs with --all, --family, or --program")


def render_instruction_xml(program,game_version,author,timestamp):
    source=program.path.read_text(encoding="utf-8").rstrip("\r\n")
    root=ET.Element("InstructionData",{
        "xmlns:xsd":XSD_NAMESPACE,
        "xmlns:xsi":XSI_NAMESPACE,
    })
    fields=(
        ("DateTime",str(windows_filetime(timestamp))),
        ("GameVersion",game_version),
        ("Title",program.title),
        ("Description",f"Source: {program.relative.as_posix()}"),
        ("Author",author),
        ("WorkshopFileHandle","0"),
        ("Instructions",source),
    )
    for name,value in fields:
        ET.SubElement(root,name).text=value
    ET.indent(root,space="  ")
    data=ET.tostring(root,encoding="utf-8",xml_declaration=True,short_empty_elements=False)
    data=data.replace(b"\n",b"\r\n")+b"\r\n"
    parsed=ET.fromstring(data)
    if parsed.findtext("Instructions")!=source:
        raise ExportError(f"XML round trip changed IC10 source: {program.relative.as_posix()}")
    return data


def export_programs(programs,output,game_version,author="stationeers-ic10",overwrite=False,
                    timestamp=None,dry_run=False):
    output=Path(output)
    if output.exists() and not output.is_dir():
        raise ExportError(f"export destination is not a directory: {output}")
    when=timestamp or dt.datetime.now(dt.timezone.utc)
    rendered=[]
    for program in programs:
        directory=output/program.title
        target=directory/"instruction.xml"
        if directory.exists():
            if not directory.is_dir():
                raise ExportError(f"export target is not a directory: {directory}")
            contents=list(directory.iterdir())
            unexpected=[path for path in contents if path.name!="instruction.xml"]
            if unexpected:
                raise ExportError(f"refusing directory with unrelated content: {directory}")
            if contents and not overwrite:
                raise ExportError(f"export target already exists (use --overwrite): {target}")
        rendered.append((directory,target,render_instruction_xml(program,game_version,author,when)))
    if dry_run:
        return [target for _,target,_ in rendered]
    for directory,target,data in rendered:
        directory.mkdir(parents=True,exist_ok=True)
        temporary=directory/"instruction.xml.tmp"
        temporary.write_bytes(data)
        temporary.replace(target)
    return [target for _,target,_ in rendered]


def parser():
    ap=argparse.ArgumentParser(
        description="Export repository IC10 programs as Stationeers instruction.xml saves.")
    ap.add_argument("--output",required=True,type=Path,
                    help="Stationeers scripts directory or a staging directory")
    scope=ap.add_mutually_exclusive_group(required=True)
    scope.add_argument("--all",action="store_true",help="export every production program")
    scope.add_argument("--family",action="append",default=[],metavar="NAME",
                       help="export one deployment family; repeat for more")
    scope.add_argument("--program",action="append",default=[],metavar="NAME",
                       help="export one program path or unique stem; repeat for more")
    ap.add_argument("--author",default="stationeers-ic10",help="saved-script Author value")
    ap.add_argument("--overwrite",action="store_true",
                    help="replace instruction.xml in exporter-owned title directories")
    ap.add_argument("--dry-run",action="store_true",help="print targets without writing files")
    return ap


def main(argv=None):
    args=parser().parse_args(argv)
    try:
        programs=discover_programs()
        selected=select_programs(programs,args.all,args.family,args.program)
        targets=export_programs(selected,args.output,target_game_version(),args.author,
                                args.overwrite,dry_run=args.dry_run)
    except (ExportError,OSError) as exc:
        print(f"export failed: {exc}",file=sys.stderr)
        return 2
    action="Would export" if args.dry_run else "Exported"
    print(f"{action} {len(targets)} program(s) to {args.output}")
    if args.dry_run:
        for target in targets:
            print(target)
    return 0


if __name__=="__main__": raise SystemExit(main())
