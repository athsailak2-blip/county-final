"""
v5.4.0 pipeline inter-stage data contracts — frozen Python typed structures.

This module is the executable Python mirror of the JSON Schema files in this
package. Every shape that crosses a stage boundary in the v5.4.0 staged engine
has both a `.schema.json` file (for data validation) and a frozen dataclass
here (for typed construction and the engine's own type hints).

The five inter-stage shapes, in pipeline order:

    RawEventRecord       stage 1 — output of a source translator
                         (raw_event_record.schema.json)
    DebtorResolvedRecord stage 2 — output of the debtor party engine (17)
                         (debtor_resolved_record.schema.json)
    LeadsBaseRecord      stage 3 — one record in <source>_leads_base.json,
                         output of the leads-base writer
                         (leads_base_record.schema.json)
    MatchedLeadRecord    stage 4 — one record in matched_leads.json,
                         output of the idempotent aggregator (19)
                         (matched_lead_record.schema.json)
    EvidenceLedgerEntry  evidence ledger stage — one evidence object (08)
                         (evidence_ledger_entry.schema.json)

These dataclasses are `frozen=True, kw_only=True`: instances are immutable, and
every field must be supplied by name. Collection fields are tuples, not lists,
so a constructed contract instance is fully immutable.

These are the design lock for v5.4.0 Sessions 2-5. No engine logic lives here —
this file defines shapes only. See knowledge_base/architecture/16-20 and
knowledge_base/protocols/02 for the governing contracts.

This module is universal framework code: it contains no county-specific,
state-specific, or vendor-specific literal. The county-agnostic regression
scanner enforces that.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, Optional

# ---------------------------------------------------------------------------
# Enum value sets — the controlled vocabularies the contracts reference.
# Kept as tuples so they are importable, immutable, and testable.
# ---------------------------------------------------------------------------

SOURCE_ROLES: tuple[str, ...] = (
    "PRIMARY_EVENT_SOURCE",
    "SUPPORTING_EVENT_SOURCE",
    "ENRICHMENT_SOURCE",
    "REFERENCE_SOURCE",
    "BLOCKED_SOURCE",
)
"""16.E source-role contract. Only PRIMARY_EVENT_SOURCE originates a lead."""

NAME_TYPES: tuple[str, ...] = ("TP", "DF", "GR", "GE", "PL", "OTHER")
"""Party role codes. 17.C defines TP/DF/GR/GE; PL and OTHER are added by this
contract (see contract finding F-2 — 17.C names plaintiff filers but gives no
name_type code for them)."""

OWNER_TYPES: tuple[str, ...] = (
    "ENTITY",
    "ESTATE",
    "TRUST",
    "INDIVIDUAL",
    "UNKNOWN",
)
"""17.F owner-type classifier outputs. Precedence ENTITY > ESTATE > TRUST >
INDIVIDUAL; UNKNOWN only for empty / punctuation-only names."""

DEBTOR_RESOLUTION_STATUSES: tuple[str, ...] = ("RESOLVED", "REVIEW_REQUIRED")
"""The debtor party engine's own verdict (v5.4.0 inter-stage field — finding F-1)."""

DEBTOR_EXTRACTION_METHODS: tuple[str, ...] = (
    "STRUCTURED_NAME_TYPE",
    "FALLBACK_NAME_TYPE",
    "DOCUMENT_BODY",
    "REVIEW_ROUTED",
)
"""How owner_name was derived by the debtor party engine."""

PARCEL_RESOLUTION_STATUSES: tuple[str, ...] = (
    "RESOLVED",
    "UNRESOLVED",
    "REVIEW_REQUIRED",
)
"""13.14.1 parcel resolution status. REVIEW_REQUIRED is the 17.E debtor-routing
value."""

ENRICHMENT_STATUSES: tuple[str, ...] = ("ENRICHED", "UNENRICHED")
"""13.14.1 enrichment status. ENRICHED requires a RESOLVED parcel."""

EVIDENCE_STATUSES: tuple[str, ...] = (
    "Confirmed",
    "Estimated",
    "Possible",
    "Unknown",
    "Needs Review",
    "Unsupported",
)
"""08 evidence status labels."""

CONFIDENCE_STATUSES: tuple[str, ...] = (
    "Confirmed",
    "Estimated",
    "Possible",
    "Unknown",
)
"""18.J rolled-up confidence label for a leads-base record — the four 08
prime-directive labels. Derived from a record's evidence-ledger entries by the
weakest-evidence roll-up rule (leads_base_writer.derive_confidence_status)."""

SOURCE_CLASSES: tuple[str, ...] = (
    "lead_generating",
    "enrichment",
    "negative_signal",
    "review_required",
)
"""08 / domain 02 source classes."""

SOURCE_RELIABILITY_GRADES: tuple[str, ...] = ("A", "B", "C", "D", "E")
"""08 source reliability grades."""

LEAD_STATUSES: tuple[str, ...] = (
    "RAW_RECORD",
    "NORMALIZED_SIGNAL",
    "MATCHED_PARCEL",
    "STACKED_LEAD",
    "REVIEW_REQUIRED",
    "APPROVED_FOR_DASHBOARD",
    "EXPORTED_TO_CRM",
    "CONTACTED",
    "DEAD",
    "ARCHIVED",
)
"""FRAMEWORK_VERSION.json lead_status_lifecycle."""

# Literal type aliases for field annotations.
SourceRole = Literal[
    "PRIMARY_EVENT_SOURCE",
    "SUPPORTING_EVENT_SOURCE",
    "ENRICHMENT_SOURCE",
    "REFERENCE_SOURCE",
    "BLOCKED_SOURCE",
]
NameType = Literal["TP", "DF", "GR", "GE", "PL", "OTHER"]
OwnerType = Literal["ENTITY", "ESTATE", "TRUST", "INDIVIDUAL", "UNKNOWN"]
DebtorResolutionStatus = Literal["RESOLVED", "REVIEW_REQUIRED"]
DebtorExtractionMethod = Literal[
    "STRUCTURED_NAME_TYPE", "FALLBACK_NAME_TYPE", "DOCUMENT_BODY", "REVIEW_ROUTED"
]
ParcelResolutionStatus = Literal["RESOLVED", "UNRESOLVED", "REVIEW_REQUIRED"]
EnrichmentStatus = Literal["ENRICHED", "UNENRICHED"]
EvidenceStatus = Literal[
    "Confirmed", "Estimated", "Possible", "Unknown", "Needs Review", "Unsupported"
]
ConfidenceStatus = Literal["Confirmed", "Estimated", "Possible", "Unknown"]


# ---------------------------------------------------------------------------
# Shared nested shapes.
# ---------------------------------------------------------------------------

@dataclass(frozen=True, kw_only=True)
class Party:
    """A name-type-tagged party carried in a source row (17.C)."""

    name: str
    name_type: NameType
    raw_role: Optional[str] = None


@dataclass(frozen=True, kw_only=True)
class PropertyRefs:
    """Property identifiers carried in a source row. parcel_id may be null
    when the source does not link to a parcel (13.14)."""

    parcel_id: Optional[str] = None
    situs_address: Optional[str] = None
    legal_description: Optional[str] = None
    case_number: Optional[str] = None


@dataclass(frozen=True, kw_only=True)
class MonetaryAmount:
    """A labelled monetary amount carried in a source row."""

    label: str
    value: Optional[float] = None


@dataclass(frozen=True, kw_only=True)
class AggregationKey:
    """The 18.B aggregation key tuple (parcel_id, canonical_doc_type,
    signal_type) — the dedup boundary for signal aggregation."""

    parcel_id: Optional[str]
    canonical_doc_type: str
    signal_type: str


# ---------------------------------------------------------------------------
# Stage 1 — raw event record (output of a source translator).
# ---------------------------------------------------------------------------

@dataclass(frozen=True, kw_only=True)
class RawEventRecord:
    """A normalized, source-specific raw event, before debtor-party resolution.
    Input to the debtor party engine. Mirror of raw_event_record.schema.json."""

    raw_event_id: str
    source_id: str
    source_role: SourceRole
    canonical_doc_type: str
    source_url: str
    recorded_date: Optional[str]
    instrument_number: Optional[str]
    parties: tuple[Party, ...] = ()
    property_refs: PropertyRefs = field(default_factory=PropertyRefs)
    raw_doc_type: Optional[str] = None
    event_date: Optional[str] = None
    document_body_text: Optional[str] = None
    amounts: tuple[MonetaryAmount, ...] = ()
    evidence_ids: tuple[str, ...] = ()
    parser_name: Optional[str] = None
    parser_version: Optional[str] = None
    parser_confidence: Optional[float] = None
    captured_at: Optional[str] = None


# ---------------------------------------------------------------------------
# Stage 2 — debtor-party-resolved record (output of the 17 engine).
# ---------------------------------------------------------------------------

@dataclass(frozen=True, kw_only=True)
class DebtorResolvedRecord:
    """A raw event record with the 17 debtor identity attached. Mirror of
    debtor_resolved_record.schema.json.

    v5.4.0 finding F-1, RATIFIED Session 2: the 17 engine's verdict lives in
    `debtor_resolution_status` only. This record carries NO parcel-stage field
    — `parcel_resolution_status` first appears on LeadsBaseRecord."""

    raw_event_id: str
    source_id: str
    source_role: SourceRole
    canonical_doc_type: str
    source_url: str
    recorded_date: Optional[str]
    instrument_number: Optional[str]
    property_refs: PropertyRefs
    owner_name: str
    owner_type: OwnerType
    filer_entity: Optional[str]
    debtor_resolution_status: DebtorResolutionStatus
    review_reason: Optional[str]
    debtor_extraction_method: DebtorExtractionMethod
    expected_debtor_name_type: Optional[str] = None
    event_date: Optional[str] = None
    evidence_ids: tuple[str, ...] = ()


# ---------------------------------------------------------------------------
# Stage 3 — leads-base record (one record in <source>_leads_base.json).
# ---------------------------------------------------------------------------

@dataclass(frozen=True, kw_only=True)
class LeadsBaseRecord:
    """One record in the stable per-source base file <source>_leads_base.json.
    Mirror of leads_base_record.schema.json."""

    base_record_id: str
    raw_event_id: str
    source_id: str
    source_role: SourceRole
    canonical_doc_type: str
    signal_type: str
    aggregation_key: AggregationKey
    owner_name: str
    owner_type: OwnerType
    filer_entity: Optional[str]
    review_reason: Optional[str]
    parcel_resolution_status: ParcelResolutionStatus
    enrichment_status: EnrichmentStatus
    confidence_status: ConfidenceStatus
    instrument_number: Optional[str]
    recorded_date: Optional[str]
    source_url: str
    property_refs: PropertyRefs
    evidence_ids: tuple[str, ...] = ()
    event_date: Optional[str] = None


# ---------------------------------------------------------------------------
# Stage 4 — matched-lead record (one record in matched_leads.json).
# ---------------------------------------------------------------------------

@dataclass(frozen=True, kw_only=True)
class SignalGroup:
    """One aggregated signal on a matched lead — a group of leads-base records
    that shared the full 18.B aggregation key, merged per 18.C."""

    aggregation_key: AggregationKey
    signal_type: str
    canonical_doc_type: str
    count: int
    instrument_numbers: tuple[str, ...] = ()
    source_urls: tuple[str, ...] = ()
    evidence_ids: tuple[str, ...] = ()
    source_ids: tuple[str, ...] = ()
    earliest_recorded_date: Optional[str] = None
    latest_recorded_date: Optional[str] = None
    recorded_date_range: tuple[Optional[str], Optional[str]] = (None, None)


@dataclass(frozen=True, kw_only=True)
class MatchedLeadRecord:
    """One record in matched_leads.json, the idempotent aggregator output.
    Mirror of matched_lead_record.schema.json."""

    lead_id: str
    primary_parcel_id: Optional[str]
    owner_name: str
    owner_type: OwnerType
    filer_entity: Optional[str]
    review_reason: Optional[str]
    parcel_resolution_status: ParcelResolutionStatus
    enrichment_status: EnrichmentStatus
    signals: tuple[SignalGroup, ...]
    source_ids: tuple[str, ...]
    evidence_ids: tuple[str, ...] = ()
    lead_status: Optional[str] = None


# ---------------------------------------------------------------------------
# Evidence ledger entry (08).
# ---------------------------------------------------------------------------

@dataclass(frozen=True, kw_only=True)
class EvidenceLedgerEntry:
    """One evidence object backing one claim (08). Mirror of
    evidence_ledger_entry.schema.json."""

    evidence_id: str
    record_id: str
    field: str
    value: Any
    status: EvidenceStatus
    source_id: str
    source_reliability_grade: str
    source_url: str
    captured_at: str
    source_name: Optional[str] = None
    source_class: Optional[str] = None
    source_document_id: Optional[str] = None
    source_row_id: Optional[str] = None
    parser_name: Optional[str] = None
    parser_version: Optional[str] = None
    parser_confidence: Optional[float] = None
    match_confidence: Optional[float] = None
    derivation: Optional[dict] = None
    notes: Optional[str] = None


# ---------------------------------------------------------------------------
# Contract registry — maps each contract name to its schema file and dataclass.
# Sessions 2-5 and the v5_4_0 contract-shape tests resolve schemas through this.
# ---------------------------------------------------------------------------

CONTRACT_SCHEMA_FILES: dict[str, str] = {
    "raw_event_record": "raw_event_record.schema.json",
    "debtor_resolved_record": "debtor_resolved_record.schema.json",
    "leads_base_record": "leads_base_record.schema.json",
    "matched_lead_record": "matched_lead_record.schema.json",
    "evidence_ledger_entry": "evidence_ledger_entry.schema.json",
}
"""Contract name -> JSON Schema filename (relative to this package)."""

CONTRACT_DATACLASSES: dict[str, type] = {
    "raw_event_record": RawEventRecord,
    "debtor_resolved_record": DebtorResolvedRecord,
    "leads_base_record": LeadsBaseRecord,
    "matched_lead_record": MatchedLeadRecord,
    "evidence_ledger_entry": EvidenceLedgerEntry,
}
"""Contract name -> frozen dataclass mirror."""
