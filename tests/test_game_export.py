#!/usr/bin/env python3
from pathlib import Path as _ProjectPath
import sys as _project_sys
_PROJECT_ROOT=_ProjectPath(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in _project_sys.path:_project_sys.path.insert(0,str(_PROJECT_ROOT))
from pathlib import Path
from tempfile import TemporaryDirectory
import datetime as dt
import json
import sys
import xml.etree.ElementTree as ET
import tools.export_to_game as exporter

fails=[]


def ck(condition,message):
    if not condition:fails.append(message)


production=exporter.discover_programs()
ck(len({program.title for program in production})==len(production),
   "production compact export titles are not unique")
ck(max(len(program.title) for program in production)<=40,
   "production compact export title exceeds 40 characters")
ck(all("__" not in program.title and "_v" not in program.title for program in production),
   "production title leaks source naming syntax")


with TemporaryDirectory() as td:
    root=Path(td)/"repo"
    (root/"ic10/family-a").mkdir(parents=True)
    (root/"ic10/family-b").mkdir(parents=True)
    first=root/"ic10/family-a/alpha_v1_0.ic10"
    second=root/"ic10/family-b/beta_v2_0.ic10"
    first.write_text("move r0 1 # <&>\n",encoding="utf-8")
    second.write_text("yield\n",encoding="utf-8")
    (root/"data").mkdir()
    (root/"data/ic10_instruction_set.json").write_text(json.dumps({
        "provenance":{"target_game_build":"0.2.6428.27798 (test build)"}}),encoding="utf-8")
    programs=exporter.discover_programs(root)
    ck(len(programs)==2,"production program discovery mismatch")
    ck(exporter.Program(first,first.relative_to(root),"family-a",first.stem).title=="Alpha",
       "compact title generation mismatch")
    ck(exporter.Program(first,first.relative_to(root),"family-a",first.stem).revision=="1.0",
       "source revision parsing mismatch")
    pi_path=root/"ic10/family-a/controller_pi_runtime_v1_1.ic10"
    ck(exporter.Program(pi_path,pi_path.relative_to(root),"family-a",pi_path.stem).title=="PI Runtime",
       "operator-facing acronym/title generation mismatch")
    ck(exporter.target_game_version(root)=="0.2.6428.27798","target build parsing mismatch")
    ck([p.stem for p in exporter.select_programs(programs,families=["family-b"])]==["beta_v2_0"],
       "family selection mismatch")
    ck([p.stem for p in exporter.select_programs(programs,names=["alpha_v1_0"])]==["alpha_v1_0"],
       "unique-stem selection mismatch")
    ck([p.stem for p in exporter.select_programs(programs,names=["family-b/beta_v2_0.ic10"])]==["beta_v2_0"],
       "family/path selection mismatch")
    try:exporter.select_programs(programs,families=["missing"]);fails.append("unknown family accepted")
    except exporter.ExportError:pass
    when=dt.datetime(1970,1,1,tzinfo=dt.timezone.utc)
    ck(exporter.windows_filetime(when)==116444736000000000,"Windows FILETIME conversion mismatch")
    output=Path(td)/"game-scripts"
    targets=exporter.export_programs(programs,output,"0.2.6428.27798","tester",timestamp=when)
    ck(len(targets)==2,"export count mismatch")
    xml=ET.parse(output/"family-a__alpha_v1_0/instruction.xml").getroot()
    ck(xml.findtext("DateTime")=="116444736000000000","export DateTime mismatch")
    ck(xml.findtext("GameVersion")=="0.2.6428.27798","export GameVersion mismatch")
    ck(xml.findtext("Title")=="Alpha","compact export title mismatch")
    ck(xml.findtext("Description")==
       "Family: family-a | Revision: 1.0 | Source: ic10/family-a/alpha_v1_0.ic10",
       "export description metadata mismatch")
    ck(xml.findtext("Author")=="tester","export author mismatch")
    ck(xml.findtext("Instructions")=="move r0 1 # <&>","XML escaping changed source")
    raw=targets[0].read_bytes()
    ck(b"\r\n" in raw and b"&lt;&amp;&gt;" in raw,"game XML is not CRLF/escaped")
    try:
        exporter.export_programs(programs,output,"0.2.6428.27798",timestamp=when)
        fails.append("existing export accepted without --overwrite")
    except exporter.ExportError:pass
    second.write_text("sleep 1\n",encoding="utf-8")
    exporter.export_programs([programs[1]],output,"0.2.6428.27798",overwrite=True,timestamp=when)
    replaced=ET.parse(output/"family-b__beta_v2_0/instruction.xml").getroot()
    ck(replaced.findtext("Instructions")=="sleep 1","--overwrite did not replace source")
    dry=exporter.export_programs([programs[0]],Path(td)/"dry","0.2.6428.27798",timestamp=when,dry_run=True)
    ck(len(dry)==1 and not (Path(td)/"dry").exists(),"dry run wrote output")
    blocked=Path(td)/"not-a-directory";blocked.write_text("occupied",encoding="utf-8")
    try:
        exporter.export_programs([programs[0]],blocked,"0.2.6428.27798",timestamp=when)
        fails.append("file accepted as export destination")
    except exporter.ExportError:pass

if fails:
    print("Stationeers game export tests: FAIL")
    [print(" -",failure) for failure in fails]
    sys.exit(1)
print("Stationeers game export tests: PASS")
print(" - family/path/stem selection, compact titles, and target-build parsing")
print(" - game-compatible FILETIME, CRLF XML, metadata, and escaped source round trip")
print(" - collision refusal, explicit overwrite, and write-free dry run")
