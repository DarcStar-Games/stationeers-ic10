#!/usr/bin/env python3
from pathlib import Path as _ProjectPath
import sys as _project_sys
_PROJECT_ROOT=_ProjectPath(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in _project_sys.path:_project_sys.path.insert(0,str(_PROJECT_ROOT))
from pathlib import Path
import sys
from framework.ic10_harness import IC10,Device,run_round_robin
R=_PROJECT_ROOT;fails=[]
def ck(x,m):
 if not x:fails.append(m)
def src(n):return (R/n).read_text()

printer=Device(501,props={'ReferenceId':501,'PrefabHash':'HASH:StructureAutolathe','Power':1,'On':0,'Activate':0,'Error':0,'Lock':0},slots={1:{'Occupied':0}})
bank=IC10(src('ic10/printer-directory/printer_execution_bank_v2_0.ic10'),{'d0':printer},self_ref=601);bank.run(2)
ck(bank.stack.get(16)==501 and bank.stack.get(24)==4,'execution bank did not publish free capacity')
# Exact-ref reserve and acknowledged release.
bank.stack.update({32:501,40:7});bank.run(1)
ck(bank.stack.get(48)==1 and bank.stack.get(56)==7 and bank.stack.get(64)==501 and bank.stack.get(72)==7,'bank reserve ownership/response mismatch')
ck(printer.props.get('Lock')==1 and (bank.stack.get(24,0)&2)==2,'bank did not hold owned printer lock')
bank.stack.update({32:501,40:-7});bank.run(1)
ck(bank.stack.get(48)==1 and bank.stack.get(56)==-7 and bank.stack.get(64)==0 and bank.stack.get(72)==0 and printer.props.get('Lock')==0,'bank release was not acknowledged/cleared')
# Failed capacity request must never become an owner on the next scan.
printer.slots[1]['Occupied']=1;bank.stack.update({32:501,40:8});bank.run(1)
ck(bank.stack.get(48)==-4 and bank.stack.get(56)==8 and bank.stack.get(72)==0,'occupied output did not fail WAIT_CAPACITY without ownership')
printer.slots[1]['Occupied']=0;bank.run(2)
ck((bank.stack.get(24,0)&2)==0 and bank.stack.get(72)==0,'failed reservation poisoned bank into fake held state')
bank.stack.update({32:501,40:9});bank.run(1)
ck(bank.stack.get(48)==1 and bank.stack.get(72)==9,'printer did not recover after failed capacity request')
bank.stack.update({32:501,40:-9});bank.run(1)

# A fresh/unrecognized bank must not clear a lock it cannot prove it owns.
printer.props['Lock']=1
fresh=IC10(src('ic10/printer-directory/printer_execution_bank_v2_0.ic10'),{'d0':printer},self_ref=610);fresh.run(1)
ck(printer.props.get('Lock')==1,'fresh execution bank cleared an externally owned Lock')
printer.props['Lock']=0

# Execution overlay joins local capacity to Item4 Printer Directory.
raw=Device(700,stack={0:31415981,1:1,2:0,3:11,5:1,7:0,9:'HASH:DirectorySchema.Printer.v2',11:3,12:64,32:501,33:'HASH:Printer.Autolathe',34:257},props={'ReferenceId':700})
bankdev=Device(601,stack=bank.stack,props={'ReferenceId':601})
ad=IC10(src('ic10/printer-directory/printer_execution_directory_adapter_v1_0.ic10'),{'d0':raw,'bank':bankdev},self_ref=602);ad.run(2)
ck(ad.stack.get(3)=='HASH:DirectorySchema.PrinterExecution.v1' and ad.stack.get(12)==1,'execution adapter header/count mismatch')
ck(ad.stack.get(18)==501 and ad.stack.get(19)=='HASH:Printer.Autolathe','execution adapter lost exact printer identity')
spec=ad.stack.get(20,0);ck((spec&16384)==16384 and (spec&8192)==0,'execution ProcessorSpec capacity bits mismatch')

# Dynamic generic selector accepts exact execution directory ref and rejects occupied output.
execdir=Device(710,stack={0:31415981,1:1,2:0,3:5,5:1,7:0,9:'HASH:DirectorySchema.PrinterExecution.v1',11:3,12:64,32:501,33:'HASH:Printer.Autolathe',34:spec},props={'ReferenceId':710})
sel=IC10(src('ic10/manufacturing/manufacturing_candidate_selector_v2_0.ic10'),{'d0':execdir});sel.run(1)
sel.stack.update({17:'HASH:DirectorySchema.PrinterExecution.v1',18:'HASH:Printer.Autolathe',19:1,20:2,21:0,22:1,15:1,16:710});sel.run(1)
ck(sel.stack.get(9)==1 and sel.stack.get(10)==501,'dynamic selector rejected free managed printer')
execdir.stack[34]=spec|8192;execdir.stack[3]=6;sel.stack.update({21:0,22:2});sel.run(1)
ck(sel.stack.get(9)==-2,'selector accepted occupied printer output')
execdir.stack[34]=spec;execdir.stack[3]=7

# Capacity Client reserve/release waits for bank acknowledgement.
clientbank=Device(601,stack=bank.stack,props={'ReferenceId':601})
client=IC10(src('ic10/printer-directory/printer_capacity_client_v2_0.ic10'),{'bank':clientbank},self_ref=603);client.run(1)
client.stack.update({12:501,13:spec,14:1,15:21})
for _ in range(8):run_round_robin([client,bank],1)
ck(client.stack.get(16)==21 and client.stack.get(17)==1 and client.stack.get(8)==501,'capacity client failed exact reserve')
client.stack.update({14:2,15:-21});client.run(1)
ck(client.stack.get(16)==21,'capacity client acknowledged release before bank processed it')
for _ in range(6):run_round_robin([bank,client],1)
ck(client.stack.get(16)==-21 and client.stack.get(17)==1 and bank.stack.get(72)==0,'capacity client failed acknowledged release')

# Swap after client request publication but before Bank processing must fail closed.
replacement=Device(502,props={'ReferenceId':502,'PrefabHash':'HASH:StructureElectronicsPrinter','Power':1,'On':0,'Activate':0,'Error':0,'Lock':0},slots={1:{'Occupied':0}})
bank.screws['d0']=printer;bank.run(1)
client.stack.update({12:501,13:spec,14:1,15:22});client.run(2) # locate/publish request; do not run Bank
bank.screws['d0']=replacement;bank.run(1);client.run(2)
ck(client.stack.get(16)==22 and client.stack.get(17)==-2 and replacement.props.get('Lock')==0,'mid-transaction printer swap did not fail closed')

# Bank reboot before acknowledgement: client reasserts request and eventually succeeds.
bank.screws['d0']=printer;bank.run(1)
client.stack.update({12:501,13:spec,14:1,15:23});client.run(2)
reboot=IC10(src('ic10/printer-directory/printer_execution_bank_v2_0.ic10'),{'d0':printer},self_ref=601);reboot.run(1)
clientbank.stack=reboot.stack
for _ in range(10):run_round_robin([client,reboot],1)
ck(client.stack.get(16)==23 and client.stack.get(17)==1,'capacity request did not survive Bank reboot/reassertion')

if fails:
 print('Printer execution capacity: FAIL');[print(' -',x) for x in fails];sys.exit(1)
print('Printer execution capacity: PASS')
print(' - request/response tokens are separate from persisted exact-printer ownership')
print(' - failed capacity reservations never become fake held reservations')
print(' - fresh banks never clear locks they cannot prove they own')
print(' - reserve/release are acknowledged and requests survive Bank reboot')
print(' - printer swaps between request publication and Bank processing fail closed')
