# Framework Test Controller

ControllerTest is a test-only controller family used to exercise the generic framework independently of PI control semantics. It is especially useful for validating configuration transport, input resolution, persistence, and error handling before connecting a real actuator/process.

## Components

- `ic10/controller-config/generic_persistent_config_host_v1_1.ic10` — unchanged Generic Host.
- `tests/ic10/framework_test_config_policy_v1_0.ic10` — test schema/defaults/validation + fault injection.
- `tests/ic10/framework_test_controller_v1_0.ic10` — runtime/telemetry loopback.
- `tests/ic10/framework_test_input_profile_fixture_v1_0.ic10` — standalone test-only Profile surface exercising every current generic input kind; ControllerTest is intentionally absent from the production Input Profile Catalog.

The important architectural fact is that ControllerTest and PI use the **same** Generic Persistent Config Host script.

## Schema

Test Policy geometry is one block with mask `63` (`0b00111111`), giving six active fields in physical slots 0..5.

The Input Profile deliberately covers the generic resolver behaviors:

1. Memory
2. Linear Dial
3. Integer Dial
4. Boolean Switch (`0/1`)
5. Two-state Switch (`-1/+1`)
6. Enum Dial (table values `10, 20, 30, 40`)

The test runtime publishes effective config fields through telemetry so a human can verify that the value that survived Host/Policy persistence is the value being consumed by a runtime.

## Fault injection

Test Policy `d1` is optional:

- approximately `1`: reject the next candidate with `-90` and clear input when writable;
- approximately `2`: hold by not publishing Policy response.

These modes let you test that generic components behave correctly when validation fails or does not complete.

## Suggested manual test sequence

1. Establish defaults and verify all six fields load into Editor.
2. Exercise each physical input kind and Save the staged result.
3. Apply and verify Host success, effective generation change, and telemetry loopback.
4. Set `d1 ~= 1`, submit a new candidate, and verify the previous effective config remains in use after rejection.
5. Set `d1 ~= 2`, submit a candidate, and verify the transaction remains pending rather than falsely succeeding.
6. Restore Policy response and verify the framework recovers cleanly.
7. Power-cycle/reflash around commits according to `docs/FRAMEWORK_HARDENING_TESTS.md` and verify A/B recovery.

If these tests fail, debug the framework layer first. If ControllerTest passes but PI does not, the remaining fault surface is much more likely to be PI Policy/Profile/Runtime semantics or physical process wiring.
