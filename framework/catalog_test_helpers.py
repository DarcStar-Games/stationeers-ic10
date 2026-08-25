from pathlib import Path
import json,subprocess,sys
from framework.ic10_harness import IC10,Device
R=Path(__file__).resolve().parents[1]

def generate_recipe_fixture(output):
    """Generate the small deterministic Recipe Catalog fixture into a caller-owned temporary directory."""
    output=Path(output)
    subprocess.run([sys.executable,str(R/'tools'/'generate'/'generate_recipe_catalog.py'),'--game-data',str(R/'tests'/'fixtures'/'recipe_game_data'),'--output',str(output),'--clean'],check=True,stdout=subprocess.DEVNULL)
    return json.loads((output/'recipe_catalog_manifest.json').read_text())

def _loader_device(src,ref):
    vm=IC10(src,self_ref=ref);vm.run(1)
    return Device(ref,vm.stack,{'ReferenceId':ref}),vm

def _generic_sources(root=R):
    return tuple((root/n).read_text() for n in (
        'ic10/catalog-control-plane/generic_catalog_store_v3_0.ic10','ic10/catalog-control-plane/catalog_coordinator_core_v3_0.ic10','ic10/catalog-control-plane/catalog_loader_router_v3_0.ic10',
        'ic10/directory-core/generic_registry_directory_host_v2_0.ic10','ic10/catalog-control-plane/catalog_coordinator_directory_adapter_v2_0.ic10',
        'ic10/catalog-control-plane/catalog_coordinator_directory_telemetry_v2_0.ic10','ic10/catalog-control-plane/catalog_coordinator_recovery_v2_0.ic10',
        'ic10/catalog-control-plane/catalog_item_migration_planner_v2_0.ic10','ic10/catalog-control-plane/catalog_item_migration_worker_v1_0.ic10',
        'ic10/catalog-control-plane/catalog_store_retirement_manager_v2_0.ic10'))

def _drive(stores,vms,loaders,services,max_rounds=60000):
    expected=sum(int(d.stack.get(8,0)) for g in loaders for d in g)
    adapter,dirvm,telemetry,coordvm,routervm,recovery,migration,worker,retirement=services
    for _ in range(max_rounds):
        adapter.run(1,max_steps=50000);dirvm.run(1,max_steps=50000);telemetry.run(1,max_steps=50000)
        coordvm.run(1,max_steps=50000);routervm.run(1,max_steps=50000)
        for vm in vms:vm.run(1,max_steps=50000)
        recovery.run(1,max_steps=50000);migration.run(1,max_steps=50000);worker.run(1,max_steps=50000);retirement.run(1,max_steps=50000)
        imported=sum(int(d.stack.get(15,0)) for g in loaders for d in g)
        if imported>=expected:return
    raise RuntimeError(f'catalog coordination imported {sum(int(d.stack.get(15,0)) for g in loaders for d in g)}/{expected} items')

def load_catalog_chain(store_sources,loader_source_groups,*,store_ref_base=8000,loader_ref_base=10000,coordinator_ref=None,router_ref=None,coordinator_epoch=1,coordinator_source=None,router_source=None):
    """Bring up unclaimed Generic Stores and Coordinator ABI3, then place relocatable Loader items."""
    if not store_sources:return [],[],[]
    generic,core_src,router_src,dir_src,adapter_src,tel_src,rec_src,mig_src,worker_src,ret_src=_generic_sources()
    coordinator_ref=coordinator_ref or store_ref_base-20;router_ref=router_ref or store_ref_base-19
    directory_ref=store_ref_base-18;adapter_ref=store_ref_base-17;telemetry_ref=store_ref_base-16
    recovery_ref=store_ref_base-15;migration_ref=store_ref_base-14;worker_ref=store_ref_base-13;retirement_ref=store_ref_base-12
    stores=[];vms=[]
    for i,src in enumerate(store_sources):
        vm=IC10(src,self_ref=store_ref_base+i);vm.stack[18]=i+1;vm.run(2)
        stores.append(Device(store_ref_base+i,vm.stack,{'ReferenceId':store_ref_base+i}));vms.append(vm)
    loader_groups=[];next_ref=loader_ref_base
    for group in loader_source_groups:
        ds=[]
        for src in group:
            d,lvm=_loader_device(src,next_ref);ds.append(d);next_ref+=1
        loader_groups.append(ds);next_ref+=4
    all_loaders=[d for g in loader_groups for d in g]
    adapter=IC10(adapter_src,self_ref=adapter_ref);adapterdev=Device(adapter_ref,adapter.stack,{'ReferenceId':adapter_ref});adapter.run(1)
    dirvm=IC10(dir_src,{'d0':adapterdev},self_ref=directory_ref);dirdev=Device(directory_ref,dirvm.stack,{'ReferenceId':directory_ref});dirvm.run(2)
    coordvm=IC10(coordinator_source or core_src,{'d0':dirdev},self_ref=coordinator_ref);coordvm.stack[2]=1;coordvm.stack[3]=coordinator_epoch
    coord=Device(coordinator_ref,coordvm.stack,{'ReferenceId':coordinator_ref});coord.vm=coordvm
    telemetry=IC10(tel_src,{'d0':dirdev},self_ref=telemetry_ref)
    routervm=IC10(router_source or router_src,{'d0':coord},self_ref=router_ref);router=Device(router_ref,routervm.stack,{'ReferenceId':router_ref});router.vm=routervm
    recovery=IC10(rec_src,{'d0':coord,'d1':dirdev},self_ref=recovery_ref)
    migration=IC10(mig_src,{'d0':coord,'d1':dirdev},self_ref=migration_ref)
    worker=IC10(worker_src,{'d0':coord},self_ref=worker_ref)
    retirement=IC10(ret_src,{'d0':coord,'d1':dirdev},self_ref=retirement_ref)
    for i,s in enumerate(stores):
        adapter.screws[f's{i}']=s;coordvm.screws[f's{i}']=s;routervm.screws[f's{i}']=s;recovery.screws[f's{i}']=s;migration.screws[f's{i}']=s;worker.screws[f's{i}']=s;retirement.screws[f's{i}']=s
    for i,d in enumerate(all_loaders):routervm.screws[f'l{i}']=d
    for vm in vms:
        for i,d in enumerate(all_loaders):vm.screws[f'l{i}']=d
    _drive(stores,vms,loader_groups,(adapter,dirvm,telemetry,coordvm,routervm,recovery,migration,worker,retirement))
    for vm in vms:
        vm.screws['coord']=coord;vm.screws['router']=router;vm.screws['directory']=dirdev
    if vms:
        vms[0].coord=coord;vms[0].directory=dirdev;vms[0].scanner=adapter;vms[0].dirvm=dirvm;vms[0].telemetry=telemetry
        vms[0].recovery=recovery;vms[0].migration=migration;vms[0].migration_worker=worker;vms[0].retirement=retirement;vms[0].router=router
    return stores,vms,loader_groups

def load_catalog_store(store_source,loader_sources,*,store_ref,primary=None,previous=None,loader_ref_base=10000):
    stores,vms,groups=load_catalog_chain([store_source],[loader_sources],store_ref_base=store_ref,loader_ref_base=loader_ref_base)
    return stores[0],vms[0],groups[0]
