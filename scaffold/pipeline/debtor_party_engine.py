"""
debtor_party_engine — v5.4.0 staged pipeline, stage 2 (the §17 engine).

STATUS: IMPLEMENTED in v5.4.0 Session 2. This module resolves the debtor /
lead subject for one raw event record per the §17 Debtor Party Rules. The
behavioral spec is scaffold/tests/v5_4_0/test_debtor_party_engine_behavior.py,
test_filer_suppression_behavior.py, and test_debtor_party_engine_units.py.

Contract: knowledge_base/architecture/17_debtor_party_rules.md.

This engine takes a raw event record (raw_event_record.schema.json) and
resolves the debtor / lead subject — the party in the source record that is
the property owner being acted against — distinct from the filer, lienholder,
or claimant. It emits a debtor-resolved record
(debtor_resolved_record.schema.json), which it validates before returning.

Why this engine exists (§17.B): different doc types invert party roles
differently. A naive translator that takes the first-named party as "owner"
produces filer-as-owner inversions — it would name the hospital as the owner
of a hospital lien, the IRS as the owner of a federal tax lien, the lender as
the owner of a foreclosure. §17 specifies, per canonical_doc_type, which party
is the debtor.

v5.4.0 finding F-1, RATIFIED Session 2 (see §17.K): this engine records its
verdict in `debtor_resolution_status` only. It MUST NOT write
`parcel_resolution_status` — that is a downstream parcel-stage field.

v5.4.0 finding F-5, resolved for Session 2: the §17.C table covers 17 canonical
doc types (UNIVERSAL_DEBTOR_PARTY_RULES below). A canonical_doc_type with NO
§17.C rule row hits the DEFAULT rule — route to REVIEW_REQUIRED with
review_reason "no_debtor_rule_for_doc_type". The engine NEVER guesses a debtor
for an unmapped doc type and NEVER silently passes it through.

This module is universal framework code: the §17.C debtor_party_rules table
and the §17.D filer-suppression patterns are universal; the per-county
doc-type taxonomy and any county-specific suppression additions are passed in
at call time. No county / state / vendor literal appears here.
"""

from __future__ import annotations

import functools
import json
import re
from typing import Optional

from jsonschema import Draft202012Validator

from scaffold.pipeline.contracts import schema_path
from scaffold.pipeline.contracts.records import single_owner_block

# ---------------------------------------------------------------------------
# §17.C — the universal debtor_party_rules table.
#
# Rule row shape:
#   expected_debtor_name_type  the name_type carrying the debtor identity
#   fallback_debtor_name_type  secondary name_type if the primary is absent
#   filer_name_types           name_type(s) whose parties are filers (used to
#                              populate filer_entity — best-effort, see F-6)
#   debtor_source              "STRUCTURED" (name_type fields) or
#                              "DOCUMENT_BODY" (extracted from document text)
#   known_filer_role           descriptive label of the filer's role. §17.C
#                              names filer pattern-sets ("plaintiff patterns",
#                              "contractor patterns", "executor/administrator
#                              patterns", "heir-affiant patterns", "sheriff/
#                              marshal patterns") that §17.D does NOT
#                              enumerate — finding F-6, an open gap. This
#                              engine implements only the concretely-defined
#                              §17.D patterns; known_filer_role is descriptive
#                              metadata, not an executable pattern set.
# ---------------------------------------------------------------------------

UNIVERSAL_DEBTOR_PARTY_RULES: dict[str, dict] = {
    "hospital_lien": {
        "expected_debtor_name_type": "TP",
        "fallback_debtor_name_type": "GE",
        "filer_name_types": ["GR"],
        "debtor_source": "STRUCTURED",
        "known_filer_role": "hospital entity",
    },
    "code_lien": {
        "expected_debtor_name_type": "TP",
        "fallback_debtor_name_type": "GE",
        "filer_name_types": ["GR"],
        "debtor_source": "STRUCTURED",
        "known_filer_role": "municipal agency",
    },
    "administrative_lien": {
        "expected_debtor_name_type": "TP",
        "fallback_debtor_name_type": "GE",
        "filer_name_types": ["GR"],
        "debtor_source": "STRUCTURED",
        "known_filer_role": "state agency",
    },
    "federal_tax_lien": {
        "expected_debtor_name_type": "TP",
        "fallback_debtor_name_type": "GE",
        "filer_name_types": ["GR"],
        "debtor_source": "STRUCTURED",
        "known_filer_role": "federal taxing authority",
    },
    "state_tax_lien": {
        "expected_debtor_name_type": "TP",
        "fallback_debtor_name_type": "GE",
        "filer_name_types": ["GR"],
        "debtor_source": "STRUCTURED",
        "known_filer_role": "state taxing authority",
    },
    "mechanic_lien": {
        "expected_debtor_name_type": "GR",
        "fallback_debtor_name_type": "DF",
        "filer_name_types": ["GE"],
        "debtor_source": "STRUCTURED",
        "known_filer_role": "contractor / construction entity",
    },
    "construction_lien": {
        "expected_debtor_name_type": "GR",
        "fallback_debtor_name_type": "DF",
        "filer_name_types": ["GE"],
        "debtor_source": "STRUCTURED",
        "known_filer_role": "contractor / construction entity",
    },
    "lis_pendens": {
        "expected_debtor_name_type": "DF",
        "fallback_debtor_name_type": "TP",
        "filer_name_types": ["PL"],
        "debtor_source": "STRUCTURED",
        "known_filer_role": "plaintiff",
    },
    "civil_judgment": {
        "expected_debtor_name_type": "DF",
        "fallback_debtor_name_type": "TP",
        "filer_name_types": ["PL"],
        "debtor_source": "STRUCTURED",
        "known_filer_role": "judgment creditor",
    },
    "abstract_of_judgment": {
        "expected_debtor_name_type": "DF",
        "fallback_debtor_name_type": "TP",
        "filer_name_types": ["PL"],
        "debtor_source": "STRUCTURED",
        "known_filer_role": "judgment creditor",
    },
    "executor_deed": {
        "expected_debtor_name_type": "GR",
        "fallback_debtor_name_type": None,
        "filer_name_types": [],
        "debtor_source": "STRUCTURED",
        "known_filer_role": "none (the estate is the lead subject)",
    },
    "administrator_deed": {
        "expected_debtor_name_type": "GR",
        "fallback_debtor_name_type": None,
        "filer_name_types": [],
        "debtor_source": "STRUCTURED",
        "known_filer_role": "none (the estate is the lead subject)",
    },
    "sheriff_sale": {
        "expected_debtor_name_type": "DF",
        "fallback_debtor_name_type": None,
        "filer_name_types": [],
        "debtor_source": "STRUCTURED",
        "known_filer_role": "sheriff / marshal",
    },
    "affidavit_of_heirship": {
        "expected_debtor_name_type": None,
        "fallback_debtor_name_type": None,
        "filer_name_types": [],
        "debtor_source": "DOCUMENT_BODY",
        "known_filer_role": "heir-affiant",
    },
    "foreclosure_notice": {
        "expected_debtor_name_type": None,
        "fallback_debtor_name_type": None,
        "filer_name_types": [],
        "debtor_source": "DOCUMENT_BODY",
        "known_filer_role": "mortgagee / trustee / lender",
    },
    "trustee_sale": {
        "expected_debtor_name_type": None,
        "fallback_debtor_name_type": None,
        "filer_name_types": [],
        "debtor_source": "DOCUMENT_BODY",
        "known_filer_role": "trustee / mortgagee",
    },
    "probate": {
        "expected_debtor_name_type": None,
        "fallback_debtor_name_type": None,
        "filer_name_types": [],
        "debtor_source": "DOCUMENT_BODY",
        "known_filer_role": "executor / administrator",
    },
}

# ---------------------------------------------------------------------------
# §17.D — universal known-filer suppression patterns.
#
# A name matching any of these MUST NEVER be returned as owner_name. The
# patterns are grouped by category for review_reason reporting. Each entry is
# a compiled, case-insensitive regex; multi-word patterns tolerate flexible
# whitespace. <*> wildcards in §17.D become "match the marker phrase anywhere
# in the name".
# ---------------------------------------------------------------------------

def _ci(pattern: str) -> re.Pattern:
    return re.compile(pattern, re.IGNORECASE)


_FILER_SUPPRESSION_PATTERNS: dict[str, list[tuple[str, re.Pattern]]] = {
    "government_entity": [
        ("CITY OF <*>", _ci(r"\bCITY\s+OF\b")),
        ("COUNTY OF <*>", _ci(r"\bCOUNTY\s+OF\b")),
        ("STATE OF <*>", _ci(r"\bSTATE\s+OF\b")),
        ("UNITED STATES OF AMERICA", _ci(r"\bUNITED\s+STATES(\s+OF\s+AMERICA)?\b")),
        ("IRS", _ci(r"\bIRS\b")),
        ("INTERNAL REVENUE SERVICE", _ci(r"\bINTERNAL\s+REVENUE\s+SERVICE\b")),
    ],
    "state_agency": [
        ("<STATE> COMPTROLLER", _ci(r"\bCOMPTROLLER\b")),
        ("<STATE> WORKFORCE COMMISSION", _ci(r"\bWORKFORCE\s+COMMISSION\b")),
        ("<STATE> DEPARTMENT OF <*>", _ci(r"\bDEPARTMENT\s+OF\b")),
    ],
    "hospital_entity": [
        ("HOSPITAL", _ci(r"\bHOSPITALS?\b")),
        ("HEALTH SYSTEM", _ci(r"\bHEALTH\s+SYSTEM\b")),
        ("MEDICAL CENTER", _ci(r"\bMEDICAL\s+CENTER\b")),
    ],
    "mortgage_lender": [
        ("MORTGAGE COMPANY", _ci(r"\bMORTGAGE\s+COMPANY\b")),
        ("MORTGAGE CORP", _ci(r"\bMORTGAGE\s+CORP(ORATION)?\b")),
        ("MORTGAGE LLC", _ci(r"\bMORTGAGE\s+L\.?L\.?C\.?\b")),
        ("BANK N.A.", _ci(r"\bBANK\s+N\.?\s*A\.?\b")),
        ("BANK NATIONAL ASSOCIATION", _ci(r"\bBANK\s+NATIONAL\s+ASSOCIATION\b")),
    ],
    "federal_mortgage_agency": [
        ("FREDDIE MAC", _ci(r"\bFREDDIE\s+MAC\b")),
        ("FANNIE MAE", _ci(r"\bFANNIE\s+MAE\b")),
        ("FEDERAL HOME LOAN MORTGAGE CORPORATION",
         _ci(r"\bFEDERAL\s+HOME\s+LOAN\s+MORTGAGE\s+CORPORATION\b")),
        ("FEDERAL NATIONAL MORTGAGE ASSOCIATION",
         _ci(r"\bFEDERAL\s+NATIONAL\s+MORTGAGE\s+ASSOCIATION\b")),
        ("GINNIE MAE", _ci(r"\bGINNIE\s+MAE\b")),
        ("GOVERNMENT NATIONAL MORTGAGE ASSOCIATION",
         _ci(r"\bGOVERNMENT\s+NATIONAL\s+MORTGAGE\s+ASSOCIATION\b")),
    ],
    "servicer": [
        ("NATIONSTAR", _ci(r"\bNATIONSTAR\b")),
        ("MR. COOPER", _ci(r"\bMR\.?\s+COOPER\b")),
        ("PHH MORTGAGE", _ci(r"\bPHH\s+MORTGAGE\b")),
        ("NEWREZ", _ci(r"\bNEWREZ\b")),
        ("SHELLPOINT", _ci(r"\bSHELLPOINT\b")),
        ("RUSHMORE", _ci(r"\bRUSHMORE\b")),
        ("SERVBANK", _ci(r"\bSERVBANK\b")),
    ],
    "trustee": [
        ("SUBSTITUTE TRUSTEE", _ci(r"\bSUBSTITUTE\s+TRUSTEE\b")),
        ("TRUSTEE SERVICES", _ci(r"\bTRUSTEE\s+SERVICES\b")),
    ],
}

# ---------------------------------------------------------------------------
# §17.F — owner-type classifier patterns.
# ---------------------------------------------------------------------------

# Corporate-suffix tokens (§17.F ENTITY). Word-boundary guarded so a suffix is
# matched only as a standalone token, never as a substring inside a longer
# word. Dotted abbreviations tolerate optional periods.
_ENTITY_RE = re.compile(
    r"(?<![A-Za-z])(?:"
    r"L\.?L\.?C\.?|L\.?L\.?P\.?|L\.?P\.?|"
    r"INCORPORATED|INC\.?|"
    r"CORPORATION|CORP\.?|"
    r"P\.?L\.?L\.?C\.?|"
    r"P\.?C\.?|P\.?A\.?|"
    r"LTD\.?|"
    r"COMPANY|CO\.?|"
    r"GROUP|ASSOCIATES|ENTERPRISES|PARTNERS|SERVICES|"
    r"AUTHORITY|COMMISSION|DISTRICT"
    r")(?![A-Za-z])",
    re.IGNORECASE,
)

# Decedent patterns (§17.F ESTATE). "REAL ESTATE" is stripped before testing.
_ESTATE_RE = re.compile(
    r"\b(?:EST(?:ATE)?\.?\s+OF\b|HEIRS?\s+OF\b|ESTATE\b)",
    re.IGNORECASE,
)
_REAL_ESTATE_RE = re.compile(r"\bREAL\s+ESTATE\b", re.IGNORECASE)

# Family/decedent trust patterns (§17.F TRUST). Corporate "TRUST COMPANY"
# names are caught by _ENTITY_RE first (ENTITY precedence).
_TRUST_RE = re.compile(
    r"\b(?:REVOCABLE|FAMILY|LIVING|REV)\s+TRUST\b|\bTRUST\b",
    re.IGNORECASE,
)
_ALNUM_RE = re.compile(r"[A-Za-z0-9]")

# ---------------------------------------------------------------------------
# §17.C document-body extraction labels, per doc type.
# ---------------------------------------------------------------------------

_BODY_DEBTOR_LABELS: dict[str, list[str]] = {
    "foreclosure_notice": [
        "ORIGINAL MORTGAGOR", "MORTGAGOR", "GRANTOR", "DEBTOR", "BORROWER",
        "PROPERTY OWNER", "RECORD OWNER", "OWNER OF RECORD",
    ],
    "trustee_sale": [
        "ORIGINAL MORTGAGOR", "MORTGAGOR", "GRANTOR", "DEBTOR", "BORROWER",
        "PROPERTY OWNER", "RECORD OWNER",
    ],
    "probate": ["NAME OF DECEDENT", "DECEDENT", "DECEASED"],
    "affidavit_of_heirship": ["NAME OF DECEDENT", "DECEDENT", "DECEASED"],
}

# The §17.E placeholder owner_name for a REVIEW_REQUIRED record.
_PLACEHOLDER = "{doc_type} against unidentified party"


@functools.lru_cache(maxsize=1)
def _output_validator() -> Draft202012Validator:
    """Lazy-load the debtor_resolved_record JSON Schema validator."""
    schema = json.loads(
        schema_path("debtor_resolved_record").read_text(encoding="utf-8")
    )
    return Draft202012Validator(schema)


def _validate_output(record: dict) -> dict:
    """Validate an engine output record against debtor_resolved_record.schema.json.

    Raises ValueError when the engine produced a non-conforming record — that
    is an engine bug, not a data problem, and must fail loudly.
    """
    errors = sorted(
        _output_validator().iter_errors(record), key=lambda e: list(e.path)
    )
    if errors:
        detail = "; ".join(
            f"{list(e.path) or '<root>'}: {e.message}" for e in errors
        )
        raise ValueError(
            "debtor_party_engine produced a record that violates "
            f"debtor_resolved_record.schema.json: {detail}"
        )
    return record


# ---------------------------------------------------------------------------
# Public engine functions.
# ---------------------------------------------------------------------------

def classify_owner_type(name: str) -> str:
    """Classify an owner name into one of the §17.F owner types.

    Returns one of ENTITY, ESTATE, TRUST, INDIVIDUAL, UNKNOWN.

    Precedence ENTITY > ESTATE > TRUST > INDIVIDUAL (§17.F). Word-boundary and
    position rules are enforced: a corporate suffix is matched only as a
    standalone token, "REAL ESTATE" is stripped before the ESTATE test, and a
    corporate "TRUST COMPANY" is caught as ENTITY first. UNKNOWN is returned
    only when the name is empty or carries no alphanumeric character.

    Args:
        name: The owner name to classify.

    Returns:
        One of the §17.F owner-type strings.
    """
    if not isinstance(name, str):
        return "UNKNOWN"
    stripped = name.strip()
    if not stripped or not _ALNUM_RE.search(stripped):
        return "UNKNOWN"
    if _ENTITY_RE.search(stripped):
        return "ENTITY"
    estate_text = _REAL_ESTATE_RE.sub(" ", stripped)
    if _ESTATE_RE.search(estate_text):
        return "ESTATE"
    if _TRUST_RE.search(stripped):
        return "TRUST"
    return "INDIVIDUAL"


def match_known_filer(
    name: str,
    *,
    additional_suppressions: tuple[str, ...] = (),
) -> Optional[str]:
    """Test whether a name matches a known-filer suppression pattern (§17.D).

    Government entities, state agencies, hospital entities, mortgage/lender
    entities, federal mortgage agencies, servicers, and trustee patterns must
    never appear as owner_name. County-specific suppression entries are
    layered on top as case-insensitive substring patterns.

    Args:
        name: The candidate owner name to test.
        additional_suppressions: County-specific suppression patterns.

    Returns:
        A "<category>:<pattern>" label when `name` is a known filer, or None
        when it is not.
    """
    if not isinstance(name, str) or not name.strip():
        return None
    for category, patterns in _FILER_SUPPRESSION_PATTERNS.items():
        for label, regex in patterns:
            if regex.search(name):
                return f"{category}:{label}"
    upper = name.upper()
    for entry in additional_suppressions:
        if entry and str(entry).upper() in upper:
            return f"county_suppression:{entry}"
    return None


def extract_debtor_from_document_body(
    document_body_text: str,
    canonical_doc_type: str,
) -> Optional[str]:
    """Extract the debtor name from unstructured document text (§17.C).

    For the doc types whose §17.C expected_debtor is "extracted from the
    document body" — foreclosure_notice, trustee_sale, probate,
    affidavit_of_heirship — the debtor identity is read from labelled fields
    in the document text ("DEBTOR: ...", "MORTGAGOR: ...", "DECEDENT: ...",
    "ESTATE OF ...", etc.). Absence of an extractable debtor returns None,
    which routes the record to REVIEW_REQUIRED (§17.E).

    This is a deterministic labelled-field extractor — it does not infer a
    debtor from free prose. A source whose document text does not carry a
    recognised debtor label is routed for operator review rather than guessed.

    Args:
        document_body_text: The full document text from the raw event record.
        canonical_doc_type: The canonical doc type, selecting the label set.

    Returns:
        The extracted debtor name, or None when no debtor can be extracted.
    """
    if not isinstance(document_body_text, str) or not document_body_text.strip():
        return None
    text = document_body_text

    labels = _BODY_DEBTOR_LABELS.get(canonical_doc_type, [])
    for label in labels:
        pattern = re.compile(
            r"\b" + re.escape(label).replace(r"\ ", r"\s+") + r"\b\s*[:\-]\s*([^\n;]+)",
            re.IGNORECASE,
        )
        match = pattern.search(text)
        if match:
            value = _clean_extracted_name(match.group(1))
            if value:
                return value

    # "ESTATE OF <name>" / "HEIRS OF <name>" appear without a colon for
    # probate and affidavit-of-heirship document text.
    if canonical_doc_type in ("probate", "affidavit_of_heirship"):
        match = re.search(
            r"\b(ESTATE\s+OF|HEIRS?\s+OF)\s+([^\n;,]+)", text, re.IGNORECASE
        )
        if match:
            value = _clean_extracted_name(
                f"{match.group(1)} {match.group(2)}"
            )
            if value:
                return value

    return None


def route_to_review(
    raw_event: dict,
    *,
    review_reason: str,
    filer_entity: Optional[str],
) -> dict:
    """Build a REVIEW_REQUIRED debtor-resolved record (§17.E routing contract).

    The §17.E contract: the record is NOT dropped. It is emitted with
    `debtor_resolution_status = REVIEW_REQUIRED`,
    `owner_name = "<canonical_doc_type> against unidentified party"`,
    `owner_type = UNKNOWN` (the owner is genuinely unidentified — see §17
    implementation note in the Session 2 report), `filer_entity` set to the
    original filer name when one was identified (None otherwise — e.g. the
    F-5 default rule), and `review_reason` set to the rule that triggered
    routing. Per ratified finding F-1, no parcel-stage field is written.

    Args:
        raw_event: The raw event record that could not be debtor-resolved.
        review_reason: The §17.E rule that triggered routing.
        filer_entity: The original filer name, or None when none was found.

    Returns:
        A debtor-resolved record with REVIEW_REQUIRED routing applied,
        conforming to debtor_resolved_record.schema.json.
    """
    doc_type = raw_event.get("canonical_doc_type") or "unknown_doc_type"
    placeholder = _PLACEHOLDER.format(doc_type=doc_type)
    record = _carry_forward(raw_event)
    record.update({
        "owner_name": placeholder,
        "owner_type": "UNKNOWN",
        "filer_entity": filer_entity,
        "debtor_resolution_status": "REVIEW_REQUIRED",
        "review_reason": review_reason,
        "expected_debtor_name_type": None,
        "debtor_extraction_method": "REVIEW_ROUTED",
    })
    # v5.4.0 Session 7A — a review-routed record has one (unidentified) owner
    # slot: the 17.E placeholder. multi_owner_status SINGLE_OWNER is descriptive
    # cardinality only; the needs-review verdict stays debtor_resolution_status.
    record.update(single_owner_block(
        placeholder,
        name_type=None,
        role="unresolved",
        resolution_status="REVIEW_REQUIRED",
        source_field=None,
    ))
    return record


def resolve_debtor_party(
    raw_event: dict,
    *,
    debtor_party_rules: Optional[dict] = None,
    additional_suppressions: tuple[str, ...] = (),
) -> dict:
    """Resolve the debtor party for one raw event record (§17.C / §17.E).

    The contract (§17.C, §17.E, §17.F):

      1. Look up the §17.C rule for `raw_event["canonical_doc_type"]`. With no
         rule (finding F-5), apply the DEFAULT rule: route to REVIEW_REQUIRED
         with review_reason "no_debtor_rule_for_doc_type".
      2. Extract the debtor:
         - STRUCTURED doc types — take the party whose `name_type` matches the
           rule's `expected_debtor_name_type`; if absent, the fallback
           name_type;
         - DOCUMENT_BODY doc types — call `extract_debtor_from_document_body`.
      3. Route to review (§17.E) when the expected debtor is missing, the
         document-body debtor is not extractable, OR a known-filer pattern
         (§17.D) matches the proposed owner. The lead is NEVER dropped.
      4. Classify `owner_type` via `classify_owner_type` (§17.F).
      5. The output is validated against debtor_resolved_record.schema.json.

    Per ratified finding F-1, the verdict is recorded in
    `debtor_resolution_status`; this engine writes no parcel-stage field.

    Args:
        raw_event: A raw event record conforming to
            raw_event_record.schema.json.
        debtor_party_rules: The §17.C debtor_party_rules mapping. When None,
            UNIVERSAL_DEBTOR_PARTY_RULES is used.
        additional_suppressions: County-specific filer-suppression patterns.

    Returns:
        A debtor-resolved record conforming to
        debtor_resolved_record.schema.json.

    Raises:
        ValueError: if the engine produces a non-conforming record.
    """
    rules = (
        debtor_party_rules
        if debtor_party_rules is not None
        else UNIVERSAL_DEBTOR_PARTY_RULES
    )
    doc_type = raw_event.get("canonical_doc_type")
    rule = rules.get(doc_type) if isinstance(rules, dict) else None

    # F-5 default rule — no §17.C rule for this canonical_doc_type.
    if rule is None:
        return _validate_output(
            route_to_review(
                raw_event,
                review_reason="no_debtor_rule_for_doc_type",
                filer_entity=None,
            )
        )

    parties = raw_event.get("parties") or []
    filer_name_types = set(rule.get("filer_name_types") or [])
    filer_entity = _first_party_name(parties, filer_name_types)
    debtor_source = rule.get("debtor_source", "STRUCTURED")

    if debtor_source == "DOCUMENT_BODY":
        debtor = extract_debtor_from_document_body(
            raw_event.get("document_body_text") or "", doc_type
        )
        if not debtor:
            return _validate_output(
                route_to_review(
                    raw_event,
                    review_reason="document_body_debtor_not_extractable",
                    filer_entity=filer_entity,
                )
            )
        filer_hit = match_known_filer(
            debtor, additional_suppressions=additional_suppressions
        )
        if filer_hit:
            return _validate_output(
                route_to_review(
                    raw_event,
                    review_reason=f"known_filer_pattern match: {filer_hit}",
                    filer_entity=debtor,
                )
            )
        return _validate_output(
            _build_resolved(
                raw_event,
                owner_name=debtor,
                filer_entity=filer_entity,
                method="DOCUMENT_BODY",
                expected_name_type=None,
            )
        )

    # STRUCTURED debtor extraction.
    expected = rule.get("expected_debtor_name_type")
    fallback = rule.get("fallback_debtor_name_type")

    candidate = _first_party_name(parties, {expected}) if expected else None
    method = "STRUCTURED_NAME_TYPE"
    used_name_type = expected
    if not candidate and fallback:
        fallback_candidate = _first_party_name(parties, {fallback})
        if fallback_candidate:
            candidate = fallback_candidate
            method = "FALLBACK_NAME_TYPE"
            used_name_type = fallback

    if not candidate:
        return _validate_output(
            route_to_review(
                raw_event,
                review_reason=f"expected_debtor_name_type {expected} missing",
                filer_entity=filer_entity,
            )
        )

    filer_hit = match_known_filer(
        candidate, additional_suppressions=additional_suppressions
    )
    if filer_hit:
        return _validate_output(
            route_to_review(
                raw_event,
                review_reason=f"known_filer_pattern match: {filer_hit}",
                filer_entity=candidate,
            )
        )

    return _validate_output(
        _build_resolved(
            raw_event,
            owner_name=candidate,
            filer_entity=filer_entity,
            method=method,
            expected_name_type=used_name_type,
        )
    )


# ---------------------------------------------------------------------------
# Internal helpers.
# ---------------------------------------------------------------------------

def _carry_forward(raw_event: dict) -> dict:
    """Copy the fields a debtor-resolved record carries from the raw event."""
    property_refs = raw_event.get("property_refs") or {}
    return {
        "raw_event_id": raw_event.get("raw_event_id"),
        "source_id": raw_event.get("source_id"),
        "source_role": raw_event.get("source_role"),
        "canonical_doc_type": raw_event.get("canonical_doc_type"),
        "source_url": raw_event.get("source_url"),
        "recorded_date": raw_event.get("recorded_date"),
        "instrument_number": raw_event.get("instrument_number"),
        "event_date": raw_event.get("event_date"),
        "property_refs": {
            "parcel_id": property_refs.get("parcel_id"),
            "situs_address": property_refs.get("situs_address"),
            "legal_description": property_refs.get("legal_description"),
            "case_number": property_refs.get("case_number"),
        },
        "evidence_ids": list(raw_event.get("evidence_ids") or []),
    }


def _build_resolved(
    raw_event: dict,
    *,
    owner_name: str,
    filer_entity: Optional[str],
    method: str,
    expected_name_type: Optional[str],
) -> dict:
    """Build a RESOLVED debtor-resolved record."""
    record = _carry_forward(raw_event)
    record.update({
        "owner_name": owner_name,
        "owner_type": classify_owner_type(owner_name),
        "filer_entity": filer_entity,
        "debtor_resolution_status": "RESOLVED",
        "review_reason": None,
        "expected_debtor_name_type": expected_name_type,
        "debtor_extraction_method": method,
    })
    # v5.4.0 Session 7A — the 17 engine resolves one owner per record; wrap it
    # as the SINGLE_OWNER multi-owner block. Multi-owner resolution (the 9
    # deferred rules) is Session 7, which keys off this same block.
    record.update(single_owner_block(
        owner_name,
        name_type=expected_name_type,
        role="debtor",
        resolution_status="RESOLVED",
        source_field=expected_name_type or "document_body",
    ))
    return record


def _first_party_name(parties: list, name_types: set) -> Optional[str]:
    """Return the first non-empty party name whose name_type is in name_types."""
    if not name_types:
        return None
    for party in parties or []:
        if not isinstance(party, dict):
            continue
        if party.get("name_type") in name_types:
            name = (party.get("name") or "").strip()
            if name:
                return name
    return None


def _clean_extracted_name(value: str) -> str:
    """Trim a document-body-extracted name of surrounding noise."""
    cleaned = re.sub(r"\s+", " ", value).strip()
    cleaned = cleaned.strip("\"'")
    cleaned = cleaned.rstrip(".,;:- ").strip()
    return cleaned
