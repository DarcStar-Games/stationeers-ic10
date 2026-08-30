"""Reusable orchestration for generated catalog families."""
from __future__ import annotations

from dataclasses import dataclass, field
import json
from pathlib import Path
from typing import Callable, Mapping, Sequence

from framework.catalog_schema import (
    COORDINATION_PROGRAM_FILES,
    CatalogItem,
    common_manifest,
    ensure_coordination_programs,
    pack_store_counts,
    split_catalog_items,
    stable_hash_token,
)


@dataclass(frozen=True)
class CatalogPartition:
    """Domain-owned item partition and loader configuration."""

    key_expression: str
    loader_label: str
    items: tuple[CatalogItem, ...]
    metadata: Mapping[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class GeneratedPartition:
    """Outputs and capacity data produced for one domain partition."""

    definition: CatalogPartition
    loaders: tuple[str, ...]
    loader_items: tuple[Mapping[str, int], ...]
    store_item_counts: tuple[int, ...]

    @property
    def item_count(self) -> int:
        return len(self.definition.items)

    @property
    def runtime_min_store_count(self) -> int:
        return len(self.store_item_counts)


@dataclass(frozen=True)
class CatalogGenerationResult:
    """Stable facts shared with domain metadata builders and callers."""

    digest: str
    token: str
    partitions: tuple[GeneratedPartition, ...]
    coordination_programs: tuple[str, ...]
    declared_outputs: tuple[str, ...]

    @property
    def items(self) -> tuple[CatalogItem, ...]:
        return tuple(item for partition in self.partitions for item in partition.definition.items)

    @property
    def loaders(self) -> tuple[str, ...]:
        return tuple(loader for partition in self.partitions for loader in partition.loaders)

    @property
    def total_items(self) -> int:
        return sum(partition.item_count for partition in self.partitions)

    @property
    def runtime_min_store_count(self) -> int:
        return sum(partition.runtime_min_store_count for partition in self.partitions)


@dataclass(frozen=True)
class CatalogFamily:
    """Explicit domain inputs for the shared generation lifecycle."""

    root: Path
    source_file: str
    manifest_file: str
    schema_name: str
    schema_version: int
    instance_name: str
    collection_key: str
    digest_prefix: str
    cleanup_globs: tuple[str, ...]
    rendered_output_files: tuple[str, ...]
    build_partitions: Callable[[dict], Sequence[CatalogPartition]]
    loader_filename: Callable[[CatalogPartition, int], str]
    render_outputs: Callable[[dict], Mapping[str, str]]
    manifest_extensions: Callable[[dict, CatalogGenerationResult], Mapping[str, object]]
    source_extensions: Callable[[dict, CatalogGenerationResult], Mapping[str, object]]
    summary_label: str
    summary_item_name: str


def fixed_output_inventory(family: CatalogFamily) -> tuple[str, ...]:
    """Return every non-loader output owned by a catalog family."""

    return (
        *COORDINATION_PROGRAM_FILES,
        *family.rendered_output_files,
        family.manifest_file,
        family.source_file,
    )


def declared_output_inventory(family: CatalogFamily) -> tuple[str, ...]:
    """Return the fixed and manifest-declared loader outputs for a family."""

    manifest = json.loads((Path(family.root) / family.manifest_file).read_text())
    return (*fixed_output_inventory(family), *manifest.get("loaders", ()))


def _write_text(root: Path, relative: str, text: str) -> None:
    target = root / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text)


def _json_text(value: object) -> str:
    return json.dumps(value, indent=2) + "\n"


def _output_key(root: Path, relative: str) -> Path:
    path = Path(relative)
    if path.is_absolute() or path == Path(".") or ".." in path.parts:
        raise ValueError(f"generated output must be a relative path inside the project: {relative!r}")
    project_root = root.resolve()
    target = (root / path).resolve()
    try:
        target.relative_to(project_root)
    except ValueError:
        raise ValueError(f"generated output escapes the project root: {relative!r}") from None
    return target


def _validate_output_inventory(root: Path, fixed_outputs, loader_outputs) -> None:
    owners = {}
    for kind, outputs in (("fixed output", fixed_outputs), ("loader", loader_outputs)):
        for relative in outputs:
            key = _output_key(root, relative)
            if key in owners:
                raise ValueError(
                    f"generated output path collision: {relative!r} is both {owners[key]} and {kind}"
                )
            owners[key] = kind


def run_catalog_generation(family: CatalogFamily) -> CatalogGenerationResult:
    """Run the deterministic lifecycle shared by generated catalog families."""

    root = Path(family.root)
    source = json.loads((root / family.source_file).read_text())
    partitions = tuple(family.build_partitions(source))
    if not partitions or any(not partition.items for partition in partitions):
        raise ValueError("catalog generation requires non-empty partitions")

    catalog_object = {
        "schema": family.schema_name,
        "schema_version": family.schema_version,
        family.collection_key: source[family.collection_key],
    }
    digest, token = stable_hash_token(family.digest_prefix, catalog_object)

    generated_partitions = []
    loader_outputs = []
    for partition in partitions:
        segments = split_catalog_items(
            label=partition.loader_label,
            schema_name=family.schema_name,
            schema_version=family.schema_version,
            instance_name=family.instance_name,
            partition_key_expr=partition.key_expression,
            items=partition.items,
        )
        loader_files = []
        loader_items = []
        for ordinal, (items, text) in enumerate(segments):
            relative = family.loader_filename(partition, ordinal)
            loader_files.append(relative)
            loader_outputs.append((relative, text))
            loader_items.append({"item_count": len(items), "line_count": len(text.splitlines())})
        generated_partitions.append(
            GeneratedPartition(
                definition=partition,
                loaders=tuple(loader_files),
                loader_items=tuple(loader_items),
                store_item_counts=tuple(pack_store_counts([item.cells for item in partition.items])),
            )
        )

    rendered = family.render_outputs(source)
    expected = set(family.rendered_output_files)
    if set(rendered) != expected:
        missing = sorted(expected - set(rendered))
        extra = sorted(set(rendered) - expected)
        raise ValueError(f"rendered output inventory mismatch: missing={missing}, extra={extra}")

    loaders = tuple(loader for partition in generated_partitions for loader in partition.loaders)
    fixed_outputs = fixed_output_inventory(family)
    _validate_output_inventory(root, fixed_outputs, loaders)
    cleanup_targets = []
    for pattern in family.cleanup_globs:
        pattern_path = Path(pattern)
        if pattern_path.is_absolute() or ".." in pattern_path.parts:
            raise ValueError(f"cleanup glob must stay inside the project: {pattern!r}")
        for target in sorted(root.glob(pattern)):
            _output_key(root, target.relative_to(root).as_posix())
            cleanup_targets.append(target)
    declared_outputs = (*fixed_outputs, *loaders)
    coordination_programs = tuple(COORDINATION_PROGRAM_FILES)
    result = CatalogGenerationResult(
        digest=digest,
        token=token,
        partitions=tuple(generated_partitions),
        coordination_programs=coordination_programs,
        declared_outputs=declared_outputs,
    )
    manifest = common_manifest(
        schema_name=family.schema_name,
        schema_version=family.schema_version,
        instance_name=family.instance_name,
        store_count=result.runtime_min_store_count,
        total_items=result.total_items,
        catalog_digest=digest,
    )
    extensions = dict(family.manifest_extensions(source, result))
    protected = sorted(manifest.keys() & extensions.keys())
    if protected:
        raise ValueError(f"manifest extensions override shared fields: {', '.join(protected)}")
    manifest.update(extensions)

    updated_source = dict(source)
    updated_source.update(family.source_extensions(source, result))

    ensure_coordination_programs(root)
    for target in cleanup_targets:
        if target.is_file():
            target.unlink()
    for relative, text in loader_outputs:
        _write_text(root, relative, text)
    for relative in family.rendered_output_files:
        _write_text(root, relative, rendered[relative])
    _write_text(root, family.manifest_file, _json_text(manifest))
    _write_text(root, family.source_file, _json_text(updated_source))
    print(
        f"{family.summary_label} generation: PASS - {result.total_items} "
        f"{family.summary_item_name} / runtime min {result.runtime_min_store_count} stores / "
        f"{len(result.loaders)} relocatable loaders"
    )
    return result
