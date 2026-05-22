"""
debtor_party_engine — v5.4.0 staged pipeline, stage 2 (the §17 engine).

STATUS: SCAFFOLD ONLY (v5.4.0 Session 1). Every function in this module is a
signature + contract docstring + `raise NotImplementedError`. No resolution
logic exists yet — it is built in Session 2. The behavioral spec these
functions must satisfy lives in scaffold/tests/v5_4_0_pending/.

Contract: knowledge_base/architecture/17_debtor_party_rules.md.

This engine takes a raw event record (raw_event_record.schema.json) and
resolves the debtor / lead subject — the party in the source record that is
the property owner being acted against — distinct from the filer, lienholder,
or claimant. It emits a debtor-resolved record
(debtor_resolved_record.schema.json).

Why this engine exists (§17.B): different doc types invert party roles
differently. A naive translator that takes the first-named party as "owner"
produces filer-as-owner inversions — it would name the hospital as the owner
of a hospital lien, the IRS as the owner of a federal tax lien, the lender as
the owner of a foreclosure. §17 specifies, per canonical_doc_type, which party
is the debtor.

This module is universal framework code: the §17 debtor_party_rules table and
the §17.D filer-suppression patterns are universal; the per-county doc-type
taxonomy and any county-specific suppression additions are passed in at call
time (from config/counties/<county_slug>.json). No county / state / vendor
literal appears here.
"""

from __future__ import annotations

from typing import Optional


def resolve_debtor_party(
    raw_event: dict,
    *,
    debtor_party_rules: dict,
    additional_suppressions: tuple[str, ...] = (),
) -> dict:
    """Resolve the debtor party for one raw event record (§17.C / §17.E).

    The contract (§17.C, §17.E):

      1. Look up `debtor_party_rules[raw_event["canonical_doc_type"]]` to get
         the rule: `expected_debtor_name_type`, `fallback_debtor_name_type`,
         `filer_name_types`, and the known-filer pattern set.
      2. Extract the debtor:
         - structured doc types — take the party whose `name_type` matches
           `expected_debtor_name_type`; if absent, the fallback name_type;
         - document-body doc types (foreclosure_notice, trustee_sale, probate,
           affidavit_of_heirship) — call `extract_debtor_from_document_body`.
      3. Route to review (§17.E) when the expected debtor is missing OR a
         known-filer pattern matches the proposed owner. Routing sets
         `owner_name` to the placeholder
         "<canonical_doc_type> against unidentified party", captures
         `filer_entity` and `review_reason`, and sets
         `parcel_resolution_status = REVIEW_REQUIRED`. The lead is NEVER
         dropped.
      4. Classify `owner_type` with `classify_owner_type` (§17.F).

    Args:
        raw_event: A raw event record conforming to
            raw_event_record.schema.json.
        debtor_party_rules: The universal §17.C debtor_party_rules mapping,
            keyed by canonical_doc_type.
        additional_suppressions: County-specific filer-suppression patterns
            from config/counties/<county_slug>.json
            (`debtor_party_rules.additional_suppressions`), applied on top of
            the universal §17.D patterns.

    Returns:
        A debtor-resolved record conforming to
        debtor_resolved_record.schema.json.

    Raises:
        NotImplementedError: always — v5.4.0 Session 1 scaffold.
    """
    raise NotImplementedError(
        "debtor_party_engine.resolve_debtor_party is a v5.4.0 Session 1 "
        "scaffold stub; the §17 resolution logic is built in Session 2."
    )


def classify_owner_type(name: str) -> str:
    """Classify an owner name into one of the §17.F owner types.

    Returns one of OWNER_TYPES — ENTITY, ESTATE, TRUST, INDIVIDUAL, UNKNOWN.

    The contract (§17.F):
      - ENTITY — the name carries a corporate suffix (LLC, INC, CORP, LP, LTD,
        P.A., P.C., PLLC, COMPANY, CO., GROUP, ASSOCIATES, ENTERPRISES,
        PARTNERS, SERVICES, AUTHORITY, COMMISSION, DISTRICT).
      - ESTATE — a decedent pattern by word boundary (ESTATE OF <name>,
        EST OF <name>, <name> ESTATE, <name> EST OF, HEIRS OF <name>). MUST
        NOT match when REAL ESTATE precedes ESTATE, or when ESTATE is a
        substring inside a corporate name.
      - TRUST — a family/decedent trust pattern by word boundary
        (<name> TRUST, <name> REVOCABLE TRUST, <name> FAMILY TRUST,
        <name> LIVING TRUST). MUST NOT match a corporate trust company.
      - INDIVIDUAL — the default when no other rule matches.
      - UNKNOWN — only when the name is empty, a dash, or pure punctuation.

    Classifier precedence: ENTITY > ESTATE > TRUST > INDIVIDUAL. Word-boundary
    and position rules MUST be enforced — substring matching alone produces
    false positives (REAL ESTATE GROUP LLC is ENTITY, not ESTATE).

    Args:
        name: The owner name to classify.

    Returns:
        One of the §17.F owner-type strings.

    Raises:
        NotImplementedError: always — v5.4.0 Session 1 scaffold.
    """
    raise NotImplementedError(
        "debtor_party_engine.classify_owner_type is a v5.4.0 Session 1 "
        "scaffold stub; the §17.F classifier is built in Session 2."
    )


def match_known_filer(
    name: str,
    *,
    additional_suppressions: tuple[str, ...] = (),
) -> Optional[str]:
    """Test whether a name matches a known-filer suppression pattern (§17.D).

    Patterns that MUST NEVER appear as owner_name regardless of where they sit
    in the raw record — government entities, state agencies, hospital
    entities, mortgage/lender entities, federal mortgage agencies, servicers,
    and trustee patterns (§17.D).

    Args:
        name: The candidate owner name to test.
        additional_suppressions: County-specific suppression patterns layered
            on top of the universal §17.D set.

    Returns:
        The label of the matched suppression pattern when `name` is a known
        filer, or None when it is not.

    Raises:
        NotImplementedError: always — v5.4.0 Session 1 scaffold.
    """
    raise NotImplementedError(
        "debtor_party_engine.match_known_filer is a v5.4.0 Session 1 "
        "scaffold stub; the §17.D suppression matcher is built in Session 2."
    )


def extract_debtor_from_document_body(
    document_body_text: str,
    canonical_doc_type: str,
) -> Optional[str]:
    """Extract the debtor name from unstructured document text (§17.C).

    For the doc types whose §17.C expected_debtor is "extracted from the
    document body" — foreclosure_notice, trustee_sale, probate,
    affidavit_of_heirship — the debtor identity is not in a structured
    name_type field and must be read from the document text. Absence of an
    extractable debtor routes the record to REVIEW_REQUIRED (§17.E).

    Args:
        document_body_text: The full document text from the raw event record.
        canonical_doc_type: The canonical doc type, selecting the extraction
            strategy (the foreclosed party from a notice body, the decedent
            from a probate record, etc.).

    Returns:
        The extracted debtor name, or None when no debtor can be extracted.

    Raises:
        NotImplementedError: always — v5.4.0 Session 1 scaffold.
    """
    raise NotImplementedError(
        "debtor_party_engine.extract_debtor_from_document_body is a v5.4.0 "
        "Session 1 scaffold stub; document-body extraction is built in "
        "Session 2."
    )


def route_to_review(
    raw_event: dict,
    *,
    review_reason: str,
    filer_entity: str,
) -> dict:
    """Build a REVIEW_REQUIRED debtor-resolved record (§17.E routing contract).

    The §17.E contract: the record is NOT dropped. It is emitted with
    `debtor_resolution_status = REVIEW_REQUIRED`,
    `parcel_resolution_status = REVIEW_REQUIRED`,
    `owner_name = "<canonical_doc_type> against unidentified party"`,
    `filer_entity` set to the original filer name, and `review_reason` set to
    the rule that triggered routing. It remains in the dashboard, visually
    distinct, as a research-pile entry for operator triage.

    Args:
        raw_event: The raw event record that could not be debtor-resolved.
        review_reason: The §17.E rule that triggered routing — e.g.
            "expected_debtor_name_type TP missing" or
            "known_filer_pattern match on STATE OF <*>".
        filer_entity: The original filer name from the raw record.

    Returns:
        A debtor-resolved record with REVIEW_REQUIRED routing applied,
        conforming to debtor_resolved_record.schema.json.

    Raises:
        NotImplementedError: always — v5.4.0 Session 1 scaffold.
    """
    raise NotImplementedError(
        "debtor_party_engine.route_to_review is a v5.4.0 Session 1 scaffold "
        "stub; the §17.E routing builder is built in Session 2."
    )
