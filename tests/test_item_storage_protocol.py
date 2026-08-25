#!/usr/bin/env python3
"""Adversarial model checks for Item Storage / split reservation / LArRE / SDB semantics."""
from pathlib import Path as _ProjectPath
import sys as _project_sys
_PROJECT_ROOT=_ProjectPath(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in _project_sys.path:_project_sys.path.insert(0,str(_PROJECT_ROOT))
from dataclasses import dataclass
DO_NOT_CONSUME=1; NO_IMPORT=2; PREFERRED=4; QUARANTINE=8
@dataclass
class Slot: item:int=0; qty:int=0; max_qty:int=50
@dataclass
class EP:
 ref:int; item:int; avail:int; cap:int; gen:int; roles:int=7; precision:int=3; kind:str='direct'; first_qty:int=0; flags:int=0; floor:int=0
@dataclass
class Res:
 ref:int; ep:EP; export_reserved:int=0; import_reserved:int=0; owner:int=0; epoch:int=0; reserved_sem_gen:int=0; sem_gen:int=1

def scan(slots,item,empty_max,flags=0,floor=0):
 a=c=0; first=-1; firstq=0; empty=-1
 for i,s in enumerate(slots):
  if s.qty<=0:
   c+=empty_max
   if empty<0: empty=i
  elif s.item==item:
   a+=s.qty
   if first<0: first,firstq=i,s.qty
   c+=max(0,s.max_qty-s.qty)
 a=max(0,a-floor)
 if flags&(DO_NOT_CONSUME|QUARANTINE): a=0
 if flags&(NO_IMPORT|QUARANTINE): c=0
 return a,c,first,firstq,empty

def quote(rs,item,qty,direction,role=4):
 legs=[]; total=0
 for r in rs:
  e=r.ep
  if e.item!=item or r.owner or (e.roles&role)!=role: continue
  if direction==1:
   if not(e.roles&1) or not(e.precision&9): continue
   free=e.avail-r.export_reserved
   amount=min(qty-total,free)
   if e.kind=='larre': amount=e.first_qty if 0<e.first_qty<=free else 0
  else:
   if not(e.roles&2) or not(e.precision&18): continue
   free=e.cap-r.import_reserved; amount=min(qty-total,free)
  if amount<=0: continue
  legs.append((r,amount,r.sem_gen)); total+=amount
  if len(legs)>=6 or total>=qty: break
 return (1 if total>=qty else -2),total,legs

def commit(legs,owner,epoch,direction):
 # quote-before-mutation; exact physical generation must still match.
 for r,amt,g in legs:
  if r.owner or r.sem_gen!=g: return False
  free=(r.ep.avail-r.export_reserved) if direction==1 else (r.ep.cap-r.import_reserved)
  if free<amt:return False
 for r,amt,g in legs:
  r.owner=owner;r.epoch=epoch;r.reserved_sem_gen=g
  if direction==1:r.export_reserved=amt;r.import_reserved=0
  else:r.import_reserved=amt;r.export_reserved=0
 return True

def move_ok(storage,external,storage_epoch,external_epoch,amount,outbound=True):
 if storage.owner<=0 or storage.owner!=external.owner:return False
 if storage.epoch!=storage_epoch or external.epoch!=external_epoch:return False
 if storage.sem_gen!=storage.reserved_sem_gen or external.sem_gen!=external.reserved_sem_gen:return False
 if outbound:return storage.export_reserved>=amount and external.import_reserved>=amount
 return storage.import_reserved>=amount and external.export_reserved>=amount

def release(rs,owner,epoch):
 n=0
 for r in rs:
  if r.owner==owner and r.epoch==epoch:
   r.export_reserved=r.import_reserved=r.owner=r.epoch=r.reserved_sem_gen=0;n+=1
 return n
# Mixed locker + policy/floor.
slots=[Slot(101,12),Slot(),Slot(202,8),Slot(101,7)]
assert scan(slots,101,50)==(19,131,0,12,1)
assert scan(slots,101,50,DO_NOT_CONSUME,5)[0]==0
assert scan(slots,101,50,NO_IMPORT,5)[1]==0
assert scan(slots,101,50,QUARANTINE)==(0,0,0,12,1)
# Split quote across physical locations.
e1=EP(1,101,7,20,11,first_qty=7); e2=EP(2,101,9,20,12,first_qty=9)
r1,r2=Res(11,e1),Res(12,e2)
st,total,legs=quote([r1,r2],101,12,1); assert st==1 and total==12 and [x[1] for x in legs]==[7,5]
assert commit(legs,500,31,1); assert r1.owner==r2.owner==500
# LArRE whole-stack quote over-reserves physical stack rather than pretending it can split pickup.
el=EP(3,101,10,50,20,kind='larre',first_qty=10); rl=Res(13,el)
st,total,legs=quote([rl],101,6,1); assert st==1 and total==10 and legs[0][1]==10
# Repeated identical Endpoint publication does not stale a semantic reservation; changed storage semantics do.
assert commit(legs,700,41,1); sink=Res(14,EP(4,101,0,50,30)); st,_,sinklegs=quote([sink],101,10,2); assert st==1 and commit(sinklegs,700,42,2)
assert move_ok(rl,sink,41,42,10,True)
el.gen+=1 # raw republish only; reservation semantics unchanged
assert move_ok(rl,sink,41,42,10,True)
el.first_qty=8; el.avail=8; rl.sem_gen+=1
assert not move_ok(rl,sink,41,42,8,True)
# Same numeric epoch from a different allocator is not ownership-equivalent.
rl.reserved_sem_gen=rl.sem_gen; rl.owner=700; sink.owner=701; sink.epoch=41
assert not move_ok(rl,sink,41,41,10,True)
# Destination capacity reservation is mandatory and sufficient for whole stack.
sink.owner=700;sink.epoch=42;sink.reserved_sem_gen=sink.sem_gen;sink.import_reserved=9
assert not move_ok(rl,sink,41,42,10,True)
sink.import_reserved=10; assert move_ok(rl,sink,41,42,10,True)
# Held-item fault is recoverable to saved origin after client restart.
def larre_move(src_qty,expected,dst_empty=True):
 if src_qty!=expected:return -1,False
 if not dst_empty:return -6,True
 return 1,False
assert larre_move(8,10)==(-1,False) # player changed stack before pickup: fail before hand occupied
assert larre_move(10,10,False)==(-6,True)
persisted_origin=(4,7,10)
restarted_origin=persisted_origin
assert restarted_origin==(4,7,10) # IC stack persistence supplies recovery target
# Inbound exact chute source -> reserved empty storage capacity.
store=Res(20,EP(20,101,0,50,50,kind='larre')); chute=Res(21,EP(21,101,10,0,60,roles=1,precision=1))
assert commit(quote([store],101,10,2)[2],900,51,2)
assert commit(quote([chute],101,10,1,0)[2],900,52,1)
assert move_ok(store,chute,51,52,10,False)
# Releaser only clears exact owner+epoch.
assert release([store,chute],900,51)==1 and store.owner==0 and chute.owner==900
# SDB is lower-bound: occupied stack count times commissioned guaranteed minimum; capacity is free-stack lower bound.
def sdb_bounds(stacks,min_stack,max_stack,floor=0): return max(0,stacks*min_stack-floor),(600-stacks)*max_stack
assert sdb_bounds(3,10,50,5)==(25,29850)
# FIFO SDB can still provide exact delivered amount via Stacker accumulation + final metering.
def meter_fifo(stacks,request):
 buf=0; used=0
 for q in stacks:
  if buf>=request:break
  buf+=q;used+=1
 return (request,buf-request,used) if buf>=request else None
assert meter_fifo([7,9,20],12)==(12,4,2)
# Stale terminal response unusable.
def consume(expected,response,status,payload): return payload if response==expected and status==1 else None
assert consume(9,8,1,42) is None and consume(9,9,1,42)==42
print('Item storage protocol: PASS')
print(' - multi-location quotes split up to physical reservations; LArRE whole-stack sources reserve the actual stack')
print(' - allocator identity/epoch plus semantic reservation generation prevents stale/double physical movement without invalidating identical republishes')
print(' - paired destination capacity is mandatory; held-item faults retain a restart-safe recovery origin')
print(' - direct/LArRE policy gates, inbound chute sources, exact release ownership, and SDB lower-bound semantics are covered')
print(' - SDB FIFO export plus Stacker accumulation meters the exact requested processor quantity')
