# Contract-Aware Wiring Commissioning

Generated script contracts can prove that two program sources have compatible stack access, but they cannot see which housing or device a player connected to `d0..d5`. `tools/commission_wiring.py` validates an explicit local wiring map, reports static incompatibilities, and derives the remaining in-game observations from the selected contracts.

This workflow complements the suite-level evidence in `docs/LIVE_COMMISSIONING.md`. It uses the same framework fingerprint and session file rather than creating a second evidence authority.

## 1. Create a local wiring map

Keep player-specific maps outside generated `contracts/`. The following map commissions the PI Config Policy connection to its persistent Config Host:

```json
{
  "$schema": "https://github.com/DarcStar-Games/stationeers-ic10/schemas/commissioning_wiring.schema.json",
  "format": "IC10_COMMISSIONING_WIRING_V1",
  "label": "Base A PI policy",
  "consumer": "ic10.script.pi.config.policy",
  "ports": {
    "d0": {
      "kind": "script",
      "provider": "ic10.script.generic.persistent.config.host",
      "reference": "config host housing",
      "capabilities": {
        "properties_readable": [],
        "properties_writable": [],
        "slot_properties_readable": [],
        "slot_properties_writable": [],
        "property_bindings": []
      }
    }
  }
}
```

`consumer` and script `provider` accept a source path, generated contract path, or service ID. `reference` is the player's stable description of the physical housing or device; it is evidence context, not automatic discovery.

Capabilities state what the selected game object is expected to support. They are intentionally explicit. A physical-device declaration is never treated as proof that the connected object really has those LogicTypes or slots.

When source selects a LogicType through a register, bind that register to its deployed concrete property and declare the concrete capability. For example, a PI process input configured for pressure uses `"property_bindings": [{"operand": "r12", "property": "Pressure"}]` together with `"properties_readable": ["Pressure"]`. Missing or duplicate bindings and bindings to undeclared capabilities fail closed; generated observations name `Pressure`, never the internal `r12` operand.

The declaration is not proof of the live value. Generated contracts carry source-fingerprinted provenance for every dynamic LogicType operand. The plan therefore also observes the exact Config Host, Profile View, or local configuration cell that populated the operand. When the source exposes a generation, the Snapshot Probe reads the LogicType with that generation as its before/after fence. Unfenced local configuration uses the Stack Cell Monitor. Shared operands must resolve to one property across every target port.

## 2. Validate before wiring

```text
python3 tools/commission_wiring.py validate --map ../field_evidence/pi_wiring.json
```

The report has three states:

- `PASS` means the declared contracts or capabilities are statically compatible;
- `FAIL` means the map is incomplete or incompatible and must not be commissioned as declared;
- `UNRESOLVED` means the declaration is compatible but still needs an in-game observation.

Missing required ports, a script/device kind mismatch, incompatible stack read/write ranges, conflicting equality constants, wrong literal protocols, and missing LogicType or slot capabilities fail closed. Optional unused ports may be omitted. A map entry for a port the consumer does not use is an error.

The plan ID covers the complete map, consumer source fingerprint, provider source fingerprints, and protocol/interface IDs. This is the integration point for future automatic provider identification: explicit `provider` selection can later be replaced by a discovery result without changing compatibility rules.

## 3. Perform the generated observations

The report prints only observations that source analysis cannot prove.

For a literal-header provider it lists the exact cells and values for the Snapshot Probe. In the PI example, connect the Probe screw matching Policy `d0` to the declared Config Host and capture:

```text
S0 expected GenericPersistentConfigHost.v1
S1 expected 1
```

Record `d0.provider-observed` as PASS only if both values match on the mapped housing. Repeated equality checks for one cell are emitted as separate value-bound obligations so observations from different operating states cannot overwrite each other. An unfenced value uses the Stack Cell Monitor. A fenced value uses the Snapshot Probe and prints the exact `FenceStackCell`, rule kind, and rule description. If no applicable fence is declared, the report says so rather than inventing one.

For an access-only interface, there is no identifying header. The report therefore requires a manual screw-to-housing check and recorded `ReferenceId`; it does not present the selected script as automatically observed. For a physical device, exercise the listed LogicType and slot assumptions against the connected object. Dynamic LogicType bindings are separate runtime obligations: confirm both the source configuration cell and the target device capability before recording PASS.

See `docs/STACK_CELL_MONITOR_GETTING_STARTED.md` and `docs/LIVE_COMMISSIONING.md` for tool setup and Snapshot Probe descriptors.

## 4. Record bound evidence

Create the ordinary live commissioning session:

```text
python3 tools/live_commission.py init \
  --session ../field_evidence/base_a.json \
  --label "Base A commissioning"
```

Record each runtime obligation printed by the wiring report:

```text
python3 tools/commission_wiring.py record \
  --map ../field_evidence/pi_wiring.json \
  --session ../field_evidence/base_a.json \
  --obligation d0.provider-observed \
  --status PASS \
  --observed "S0=GenericPersistentConfigHost.v1 and S1=1 on config host housing" \
  --refs "config-host:12345"
```

Use `FAIL` when the observation contradicts the declaration and `BLOCKED` when the check cannot be completed. Runs are append-only, and the latest run is current.

Revalidate with the session to apply recorded evidence:

```text
python3 tools/commission_wiring.py validate \
  --map ../field_evidence/pi_wiring.json \
  --session ../field_evidence/base_a.json
python3 tools/live_commission.py report \
  --session ../field_evidence/base_a.json \
  --output ../field_evidence/base_a.md
```

The wiring result becomes `PASS` only after every static check and runtime obligation passes. Framework input changes make the entire session stale. Map, contract fingerprint, protocol ID, or access-interface ID changes produce a different plan binding, so old observations cannot close the new plan.
