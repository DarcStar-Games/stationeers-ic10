#!/usr/bin/env python3
from pathlib import Path as _ProjectPath
import sys as _project_sys
_PROJECT_ROOT=_ProjectPath(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in _project_sys.path:_project_sys.path.insert(0,str(_PROJECT_ROOT))
from framework.ic10_line_budget import HARD_LIMIT_LINES
from framework.validation import Validation
from pathlib import Path
import json,sys
R=_PROJECT_ROOT;result=Validation(R)
P=json.loads((R/'data/resource_profiles.json').read_text())['profiles']
# The prepared fuels are the game's six gas fuel:oxidiser reactions (docs/SOURCES.md, combustion table):
# fuel LogicType, oxidiser LogicType, fuel mole fraction, and the auto-ignition point the mixture must stay
# under (573.15 K for Methane and Hydrogen, lowered 250 K by Nitrous Oxide and 150 K by Ozone). A kind-5
# profile outside this table is an unreviewed fuel.
REACTIONS={'Fuel.H2O2':('RatioHydrogen','RatioOxygen',2/3,573.15),'Fuel.CH4O2':('RatioMethane','RatioOxygen',2/3,573.15),
 'Fuel.H2N2O':('RatioHydrogen','RatioNitrousOxide',1/2,323.15),'Fuel.CH4N2O':('RatioMethane','RatioNitrousOxide',1/2,323.15),
 'Fuel.H2O3':('RatioHydrogen','RatioOzone',3/4,423.15),'Fuel.CH4O3':('RatioMethane','RatioOzone',3/5,423.15)}
kind5={p['resource_type'] for p in P if p.get('profile_kind')==5}
if kind5!=set(REACTIONS):result.fail('prepared-mixture profiles are not exactly the six reviewed reactions',detail=', '.join(sorted(kind5^set(REACTIONS))))
for fuel,(component,oxidiser,fraction,ignition) in REACTIONS.items():
 f=[p for p in P if p.get('resource_type')==fuel]
 if len(f)!=1:result.fail(f'expected exactly one {fuel} Resource Profile');continue
 p=f[0]
 if (p['resource_class'],p['unit'],p['profile_kind'],p['profile_schema'])!=(1,1,5,1):result.fail(f'{fuel} profile identity/schema mismatch')
 if abs(float(p['params'][1])+float(p['params'][3])-1)>1e-9:result.fail(f'{fuel} fractions do not sum to 1')
 if abs(float(p['params'][1])-fraction)>1e-9:result.fail(f'{fuel} is not the fuel:oxidiser reaction the game combusts')
 if p['params'][0]!=component or p['params'][2]!=oxidiser:result.fail(f'{fuel} component LogicTypes wrong')
 if not float(p['params'][6])<ignition:result.fail(f'{fuel} MaxTemperature is not under the mixture auto-ignition point {ignition} K')
checks={
'ic10/process-furnace/furnace_process_condition_request_v1_0.ic10':['poke 0 HASH("ProcessCondition.v1")','get r5 d0 64','get r7 d0 66','poke 11 r0'],
'ic10/process-furnace/process_pressure_domain_runtime_v1_0.ic10':['poke 97 2','poke 99 HASH("ControllerPressureDomain")','poke 103 3','poke 105 3'],
'ic10/process-furnace/embedded_pressure_transfer_runtime_v1_0.ic10':['poke 99 HASH("ControllerPressureTransfer")','bne r0 HASH("PressureInventoryReservation.v1") Fault','bne r0 HASH("PressureTransferGrantGuard.v1") SafeOff','s d2 SettingInput r0','s d2 SettingOutput r0'],
'ic10/process-gas-preparation/gas_mixture_purity_guard_v1_0.ic10':['poke 0 HASH("MediumPurityGuard.v1")','bne r0 5 ProfileBad','bdnvl d0 r2 SensorBad','bdnvl d0 r4 SensorBad'],
'ic10/process-gas-preparation/gas_mixer_utility_controller_v1_0.ic10':['bne r0 HASH("ProcessCondition.v1") Bad','get r14 d5 24','bdnvl d2 Pressure Mix','mul r12 r3 r7','div r12 r12 r11','s d3 Setting r12'],
'ic10/process-gas-preparation/thermal_gas_mixer_controller_v1_0.ic10':['get r3 d4 24','bdnvl d2 Pressure Mix','mul r10 r7 r8','div r10 r10 r6','s d3 Setting r10'],
'ic10/process-gfg/gas_fuel_generator_utility_controller_v1_0.ic10':['bne r0 HASH("PowerDispatchPlanStore.v1") Bad','bne r0 HASH("StructureGasGenerator") Bad','blt r9 20 EnvBad','blt r10 278 EnvBad','bgt r10 328 EnvBad','poke 0 HASH("ProcessCondition.v1")']}
for fn,toks in checks.items():
 if not result.file_exists(fn,rule='process utility source'):continue
 t=result.source(fn)
 # validate_ic10.py owns the ceiling and its reviewed exemptions; only the hard limit is rechecked.
 if len(t.splitlines())>HARD_LIMIT_LINES:result.fail(f'{fn}: exceeds the {HARD_LIMIT_LINES}-line hard limit')
 result.contains(fn,*toks,rule='process utility contract')
# Planning must be compositional: new furnace/GFG services do not mutate Job Store or Power Plan Store.
result.contains('docs/PROCESS_UTILITY_ORCHESTRATION.md','ProcessCondition ABI1','Pressure movement remains authorized by PressureGrid reservations','ic10/material-transform/material_transform_admission_v1_0.ic10','POWER -> Electrolyzer -> Fuel.H2O2 -> GFG -> POWER',rule='orchestration documentation')
for fn in checks:
 t=result.source(fn)
 if '31415999' in t or 'put d0 12' in t and fn.startswith('253_'):result.fail(fn+': leaked Generic Job/PowerPlan mutation authority')
raise SystemExit(result.finish('Process utility contracts',[
 'ProcessCondition ABI is distinct from Resource ownership',
 'furnace chamber and embedded pumps project into existing PressureGrid ABIs',
 'gas composition and thermal mixing remain physical specializations',
 'GFG fuel demand observes PowerPlan shortage without mutating PowerPlan authority']))
