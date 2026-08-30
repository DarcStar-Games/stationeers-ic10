#!/usr/bin/env python3
"""Validate that every S0 service identity is derived, exact, and checked as one value.

The rule this enforces (issue #46): at the common header base, a service's
identity value *is* its contract, ABI included -- ``HASH("<Contract>.v<ABI>")``.
Because the ABI is folded into the hashed name, one S0 equality check is
necessary and sufficient to prove the exact contract: a service that bumps its
ABI changes its name, so its S0 value changes, and every consumer still
comparing the old identity fails closed instead of silently accepting a
contract it was never written against.

That guarantee only holds while identity stays derived, so this validator
refuses the three ways it could rot:

  * a published or checked S0 written as a precomputed numeral rather than the
    HASH literal, which would let the name and the value drift apart;
  * two distinct contracts whose names collide under CRC32, which would make
    one identity name two services;
  * an S1 ABI check that disagrees with the ABI folded into the name it is
    checked beside.

Block headers away from S0 (the Generic Telemetry block at S96) are deliberately
excluded: their consumers accept a version *range*, so they keep a hand-assigned
magic and a separately checked version cell.
"""
from pathlib import Path as _ProjectPath
import sys as _project_sys
_PROJECT_ROOT=_ProjectPath(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in _project_sys.path:_project_sys.path.insert(0,str(_PROJECT_ROOT))

import re
import sys

from framework.ic10_source import game_hash, parse_ic10
from framework.protocol_headers import CONTRACT_NAME_RE, header_name, header_token, load_headers
from framework.script_contracts.parsing import collect_aliases, parse_rows, resolve_integer

ROOT = _PROJECT_ROOT
BASE = 0
HASH_LITERAL = re.compile(r'^HASH\("([^"\n]+)"\)$')
fails: list[str] = []

scripts, consumers = load_headers(ROOT)

# 1. Every base-0 header names a contract, and the name is well formed.
identities: dict[int, str] = {}
for path, headers in sorted(scripts.items()):
    for header in headers:
        if header["base"] != BASE:
            continue
        contract = header.get("contract")
        if not contract:
            fails.append(f"{path}: S0 header declares a bare magic; base-0 identity must name a contract")
            continue
        if not re.fullmatch(CONTRACT_NAME_RE, contract):
            fails.append(f"{path}: contract {contract!r} is not an UpperCamelCase identity name")
            continue
        name = header_name(contract, header["abi"])
        value = game_hash(name)
        if identities.setdefault(value, name) != name:
            fails.append(
                f"{path}: identity {name} collides under CRC32 with {identities[value]};"
                " one value would name two contracts"
            )

# 2. Every publish and every check spells the identity as the HASH literal, so
#    the published value cannot drift from the name that defines it.
expected_tokens: dict[str, set[str]] = {}
for path, headers in scripts.items():
    for header in headers:
        if header["base"] == BASE and header.get("contract"):
            expected_tokens.setdefault(path, set()).add(header_token(header["contract"], header["abi"]))

for source in sorted(ROOT.glob("ic10/*/*.ic10")):
    rel = source.relative_to(ROOT).as_posix()
    text = source.read_text()
    rows = parse_rows(text)
    aliases = collect_aliases(rows)[1]
    published = expected_tokens.get(rel, set())
    for row in rows:
        if row[0] == "poke" and len(row) >= 3 and resolve_integer(row[1], aliases) == BASE:
            if row[2] not in published:
                fails.append(
                    f"{rel}: publishes S{BASE} as {row[2]}, not the declared identity"
                    f" {' or '.join(sorted(published)) or '(none declared)'}"
                )

# 3. Every consumer's declared acceptance is a contract identity, and any ABI
#    cell it also checks agrees with the ABI folded into that identity.
for path, requirements in sorted(consumers.items()):
    text = (ROOT / path).read_text()
    rows = parse_rows(text)
    aliases = collect_aliases(rows)[1]
    for requirement in requirements:
        for accepted in requirement.get("accepted", []):
            if accepted["header_base"] != BASE:
                continue
            contract = accepted.get("contract")
            if not contract:
                fails.append(
                    f"{path} {requirement['port']}: accepts a bare S0 magic;"
                    " a base-0 acceptance must name the contract it requires"
                )
                continue
            token = header_token(contract, accepted["abi"])
            if token not in text:
                fails.append(f"{path} {requirement['port']}: accepts {contract} but never checks {token}")

# 4. An S1 ABI check beside a contract identity must agree with the folded ABI.
for source in sorted(ROOT.glob("ic10/*/*.ic10")):
    rel = source.relative_to(ROOT).as_posix()
    program = parse_ic10(source.read_text())
    rows = [list(row.tokens) for row in program.rows]
    aliases = collect_aliases(rows)[1]
    checked: dict[str, set[str]] = {}
    for index, row in enumerate(rows):
        if row[0] not in {"get", "getd"} or len(row) < 4:
            continue
        port, address = row[2], resolve_integer(row[3], aliases)
        if address not in (BASE, BASE + 1):
            continue
        for later in rows[index + 1:index + 5]:
            if later[0] in {"bne", "beq"} and len(later) >= 3 and later[1] == row[1]:
                checked.setdefault(f"{port}:{address}", set()).add(later[2])
                break
    for key, values in sorted(checked.items()):
        port, _, address = key.partition(":")
        if address != str(BASE):
            continue
        abis = checked.get(f"{port}:{BASE + 1}", set())
        for value in values:
            match = HASH_LITERAL.fullmatch(value)
            if not match:
                if re.fullmatch(r"-?\d+", value):
                    fails.append(
                        f"{rel} {port}: compares S{BASE} against the bare numeral {value};"
                        ' an identity check must name its contract as HASH("<Contract>.v<ABI>")'
                    )
                continue
            _, _, folded = match.group(1).rpartition(".v")
            if not folded.isdigit():
                continue
            disagreeing = sorted(abi for abi in abis if abi.isdigit() and abi != folded)
            if disagreeing:
                fails.append(
                    f"{rel} {port}: checks {value} but also requires S{BASE + 1}"
                    f" in {disagreeing}, disagreeing with the folded ABI {folded}"
                )

if fails:
    print("Service identity validation: FAIL")
    for failure in fails:
        print(" -", failure)
    sys.exit(1)
print("Service identity validation: PASS")
print(f" - {len(identities)} base-0 identities, each derived as HASH(\"<Contract>.v<ABI>\") with no CRC32 collision")
print(" - every S0 publish and every S0 check spells the identity as its HASH literal, never a numeral")
print(" - folding the ABI into the identity makes one S0 equality check exact: an ABI bump changes the value")
print(" - block headers away from S0 keep hand-assigned magics; their consumers accept a version range")
