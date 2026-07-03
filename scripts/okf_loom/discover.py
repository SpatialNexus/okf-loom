"""Discovery: find gaps in a bundle and emit agent-readable suggestions.

Discovery NEVER silently edits files. It produces a ``DiscoveryReport`` of
``Suggestion`` objects that a human or agent reviews and turns into an
``UpdatePlan`` (see ``okf_loom.update``). This preserves the SPEC §9
permissiveness contract (research.md §C.5: "suggestions ... are never applied
automatically to hand-authored files").

Rules implemented (each a function ``Bundle -> list[Suggestion]``):
    - ``unlinked_mentions``     (core capability ``okf.cap.discovery_mentions``)
    - ``missing_indexes``
    - ``missing_descriptions``
    - ``broken_links``          (re-surfaces validate's broken-link findings)
    - ``missing_relations_hint``(heuristic, conservative)
    - ``orphan_concepts``
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from .model import Bundle
from .parse import _INLINE_CODE_RE, _LINK_RE, _strip_code_blocks
from .paths import (
    ConceptId,
    ConceptIdError,
    concept_id_from_str,
    concept_id_to_str,
)
from .validate import CheckSpec, validate_bundle


# ---------------------------------------------------------------------------
# Data shapes
# ---------------------------------------------------------------------------


@dataclass
class Suggestion:
    """One agent-readable discovery suggestion.

    Attributes:
        rule: the discovery rule that produced this (e.g. ``unlinked_mentions``).
        severity: ``"info"`` or ``"warning"``.
        message: human-readable description.
        concept_id: the concept the suggestion applies to (the *source* for
            relation/link suggestions). None for directory-scoped rules.
        target_concept_id: for relation/link suggestions, the proposed target.
        action: short verb phrase, e.g. ``"add link"``.
        detail: machine-readable fields (rule-specific).
    """

    rule: str
    severity: str
    message: str
    concept_id: ConceptId | None
    target_concept_id: ConceptId | None
    action: str
    detail: dict = field(default_factory=dict)

    def as_dict(self) -> dict:
        return {
            "rule": self.rule,
            "severity": self.severity,
            "message": self.message,
            "concept_id": (
                concept_id_to_str(self.concept_id) if self.concept_id else None
            ),
            "target_concept_id": (
                concept_id_to_str(self.target_concept_id)
                if self.target_concept_id
                else None
            ),
            "action": self.action,
            "detail": dict(self.detail),
        }


@dataclass
class DiscoveryReport:
    """Aggregate result of running one or more discovery rules."""

    bundle_root: Path
    suggestions: list[Suggestion] = field(default_factory=list)

    def by_rule(self) -> dict[str, list[Suggestion]]:
        out: dict[str, list[Suggestion]] = {}
        for s in self.suggestions:
            out.setdefault(s.rule, []).append(s)
        return out

    def as_dict(self) -> dict:
        by_rule = self.by_rule()
        return {
            "bundle_root": str(self.bundle_root),
            "total": len(self.suggestions),
            "counts": {rule: len(items) for rule, items in by_rule.items()},
            "suggestions": [s.as_dict() for s in self.suggestions],
        }


# ---------------------------------------------------------------------------
# Public entrypoint
# ---------------------------------------------------------------------------


def discover_suggestions(
    bundle: Bundle,
    *,
    rules: list[str] | None = None,
    scope: list[str] | set[str] | None = None,
) -> DiscoveryReport:
    """Run discovery rules against a loaded bundle.

    Args:
        bundle: a loaded ``Bundle``.
        rules: subset of rule names to run, or None for all rules.
        scope: optional set/list of concept-id strings (slash form, e.g.
            ``"tables/orders"``). When given (current spec §7 scoped enrichment),
            the report keeps ONLY suggestions whose *subject* concept is in
            scope. Targets remain bundle-wide — a scoped concept may still be
            advised to link to any concept. Directory-level rules
            (``missing_indexes``) are dropped when scope is active because they
            carry no subject concept. ``scope=None`` keeps the full report
            (unchanged behaviour).

    Returns:
        A ``DiscoveryReport`` whose suggestions are grouped by rule.
    """
    selected = list(rules) if rules is not None else list(_ALL_RULES)
    unknown = [r for r in selected if r not in _ALL_RULES]
    if unknown:
        raise ValueError(f"Unknown discovery rules: {sorted(unknown)}")
    suggestions: list[Suggestion] = []
    for name in selected:
        suggestions.extend(_ALL_RULES[name](bundle))
    # Current spec §7: scoped enrichment. When a scope set is given, keep only
    # suggestions whose subject concept_id is in scope. The neighbour
    # expansion (§11 ``--neighbors``) happens in plan.build_plan before this
    # call, so discover just filters to whatever set it receives. scope=None
    # leaves the report untouched (preserves all existing behaviour).
    if scope is not None:
        scope_ids: set[ConceptId] = set()
        for s in scope:
            s = s.strip()
            if not s:
                continue
            try:
                scope_ids.add(concept_id_from_str(s))
            except (ConceptIdError, ValueError):
                continue  # ignore an unparseable scope id; never crash.
        suggestions = [
            s for s in suggestions
            if s.concept_id is not None and s.concept_id in scope_ids
        ]
    return DiscoveryReport(bundle_root=bundle.root, suggestions=suggestions)


# ---------------------------------------------------------------------------
# Rule registry
# ---------------------------------------------------------------------------

_ALL_RULES: dict[str, Callable[[Bundle], list[Suggestion]]] = {}


def _rule(name: str) -> Callable:
    def deco(fn: Callable[[Bundle], list[Suggestion]]) -> Callable:
        _ALL_RULES[name] = fn
        return fn

    return deco


# ---------------------------------------------------------------------------
# unlinked_mentions  (okf.cap.discovery_mentions)
# ---------------------------------------------------------------------------


def _scannable_body(body: str) -> str:
    """Return a copy of ``body`` safe for mention scanning.

    Fenced code blocks, inline code spans, and existing markdown links are
    blanked out while preserving line counts so line numbers stay accurate.
    """
    cleaned = _strip_code_blocks(body)  # fences -> blank lines (line-safe)
    # Blank inline-code *content* but keep a backtick marker (line-safe).
    cleaned = _INLINE_CODE_RE.sub(
        lambda m: "`" + "\n" * m.group(0).count("\n"), cleaned
    )
    # Blank existing markdown link spans (line-safe).
    cleaned = _LINK_RE.sub(lambda m: "\n" * m.group(0).count("\n"), cleaned)
    return cleaned


def _build_title_index(bundle: Bundle) -> dict[str, ConceptId]:
    """Map a lowercased mention phrase to a single concept id.

    Only phrases that uniquely identify ONE concept are kept; ambiguous phrases
    (shared by multiple concepts) are dropped to avoid bad suggestions. Short
    (< 3 chars) or non-alphanumeric phrases are dropped as too noisy.
    """
    phrase_to_cids: dict[str, set[ConceptId]] = {}
    for c in bundle.concepts.values():
        phrases = set()
        title = (c.title or "").strip().lower()
        if title:
            phrases.add(title)
        last_seg = (c.id[-1] if c.id else "").strip().lower()
        if last_seg:
            phrases.add(last_seg)
        for p in phrases:
            if len(p) < 3 or not re.search(r"[a-z0-9]", p):
                continue
            phrase_to_cids.setdefault(p, set()).add(c.id)
    return {
        p: next(iter(s)) for p, s in phrase_to_cids.items() if len(s) == 1
    }


@_rule("unlinked_mentions")
def _rule_unlinked_mentions(bundle: Bundle) -> list[Suggestion]:
    out: list[Suggestion] = []
    title_index = _build_title_index(bundle)
    if not title_index:
        return out
    compiled = {
        p: re.compile(rf"\b{re.escape(p)}\b", re.IGNORECASE)
        for p in title_index
    }
    for src in sorted(bundle.concepts.values(), key=lambda c: c.id):
        scannable = _scannable_body(src.body)
        if not scannable.strip():
            continue
        already_linked = {
            link.target
            for link in src.links(bundle_root=bundle.root)
            if link.target is not None
        }
        for phrase, target_cid in title_index.items():
            if target_cid == src.id:
                continue  # skip self-mentions
            if target_cid in already_linked:
                continue  # source already links to target
            pat = compiled[phrase]
            occurrences = [
                scannable.count("\n", 0, m.start()) + 1
                for m in pat.finditer(scannable)
            ]
            if not occurrences:
                continue
            target = bundle.concepts.get(target_cid)
            target_title = target.title if target else phrase
            out.append(
                Suggestion(
                    rule="unlinked_mentions",
                    severity="info",
                    message=(
                        f"{src.title!r} mentions {target_title!r} "
                        f"({len(occurrences)}x) but does not link to it."
                    ),
                    concept_id=src.id,
                    target_concept_id=target_cid,
                    action="add link",
                    detail={
                        "label": target_title,
                        "suggested_target_concept_id": concept_id_to_str(
                            target_cid
                        ),
                        "occurrences": occurrences,
                    },
                )
            )
    return out


# ---------------------------------------------------------------------------
# missing_indexes
# ---------------------------------------------------------------------------


@_rule("missing_indexes")
def _rule_missing_indexes(bundle: Bundle) -> list[Suggestion]:
    out: list[Suggestion] = []
    dir_has_index = {
        idx.rel_path.parent for idx in bundle.indexes.values()
    }
    concept_dirs = {c.rel_path.parent for c in bundle.concepts.values()}
    for d in sorted(concept_dirs):
        if d in dir_has_index:
            continue
        out.append(
            Suggestion(
                rule="missing_indexes",
                severity="warning",
                message=(
                    f"Directory {d}/ contains concepts but has no index.md "
                    "for progressive disclosure (SPEC §6)."
                ),
                concept_id=None,
                target_concept_id=None,
                action="create index.md",
                detail={"directory": str(d)},
            )
        )
    return out


# ---------------------------------------------------------------------------
# missing_descriptions
# ---------------------------------------------------------------------------


@_rule("missing_descriptions")
def _rule_missing_descriptions(bundle: Bundle) -> list[Suggestion]:
    out: list[Suggestion] = []
    for c in sorted(bundle.concepts.values(), key=lambda c: c.id):
        if c.description and c.description.strip():
            continue
        out.append(
            Suggestion(
                rule="missing_descriptions",
                severity="warning",
                message=(
                    f"Concept {c.title!r} has no description frontmatter."
                ),
                concept_id=c.id,
                target_concept_id=None,
                action="add description",
                detail={},
            )
        )
    return out


# ---------------------------------------------------------------------------
# broken_links  (re-surfaces validate findings)
# ---------------------------------------------------------------------------


@_rule("broken_links")
def _rule_broken_links(bundle: Bundle) -> list[Suggestion]:
    out: list[Suggestion] = []
    report = validate_bundle(bundle, checks=CheckSpec.only("link_integrity"))
    for f in report.findings:
        if f.code != "link.broken":
            continue
        detail = dict(f.detail or {})
        out.append(
            Suggestion(
                rule="broken_links",
                severity="warning",
                message=f.message,
                concept_id=f.concept_id,
                target_concept_id=None,
                action="fix or remove link",
                detail={
                    "target_raw": detail.get("target_raw"),
                    "form": detail.get("form"),
                    "label": detail.get("label"),
                    "line": f.line,
                },
            )
        )
    return out


# ---------------------------------------------------------------------------
# missing_relations_hint  (heuristic, conservative)
# ---------------------------------------------------------------------------

# Unambiguous FK signals. "references" is required to be followed by something
# table-like to avoid matching the noun "reference" / "See the references".
_FK_PATTERNS = [
    re.compile(r"\bFK\s+to\s+\S", re.IGNORECASE),
    re.compile(r"\bforeign\s+key\b", re.IGNORECASE),
    re.compile(r"\breferenced?\s+(?:to\s+)?[A-Za-z_][\w]*", re.IGNORECASE),
]


@_rule("missing_relations_hint")
def _rule_missing_relations_hint(bundle: Bundle) -> list[Suggestion]:
    out: list[Suggestion] = []
    graph = bundle.graph()
    for c in sorted(bundle.concepts.values(), key=lambda c: c.id):
        schema = c.schema_section
        if not schema:
            continue
        # Conservative: only hint when the concept has NO resolved outgoing
        # internal edges (the FK relationship is entirely unrepresented).
        # Broken links (target=None / not in bundle) do NOT count as a
        # represented relationship.
        resolved_out = [
            l for l in graph.out_edges.get(c.id, []) if l.target in graph.concept_ids
        ]
        if resolved_out:
            continue
        matched: list[str] = []
        for line in schema.splitlines():
            if any(pat.search(line) for pat in _FK_PATTERNS):
                matched.append(line.strip())
        if not matched:
            continue
        out.append(
            Suggestion(
                rule="missing_relations_hint",
                severity="info",
                message=(
                    f"{c.title!r} schema references a foreign-key-like column "
                    f"but the concept has no outgoing relation link."
                ),
                concept_id=c.id,
                target_concept_id=None,
                action="add relation link",
                detail={
                    "matched_text": matched[0],
                    "matched_lines": matched,
                },
            )
        )
    return out


# ---------------------------------------------------------------------------
# orphan_concepts
# ---------------------------------------------------------------------------


@_rule("orphan_concepts")
def _rule_orphan_concepts(bundle: Bundle) -> list[Suggestion]:
    out: list[Suggestion] = []
    graph = bundle.graph()
    for cid in sorted(graph.concept_ids):
        if graph.in_edges.get(cid) or graph.out_edges.get(cid):
            continue
        concept = bundle.concepts.get(cid)
        title = concept.title if concept else concept_id_to_str(cid)
        out.append(
            Suggestion(
                rule="orphan_concepts",
                severity="info",
                message=(
                    f"{title!r} has no incoming or outgoing internal links "
                    "(orphan node in the graph)."
                ),
                concept_id=cid,
                target_concept_id=None,
                action="connect",
                detail={},
            )
        )
    return out
