#!/usr/bin/env python3
"""v5.4.0 Group A (green) — engine module stubs are importable, carry the
declared signatures, and raise NotImplementedError when called.

This is a SHAPE / SCAFFOLDING test, not a behavioral test. It asserts that the
engine modules still awaiting implementation exist, expose the declared
functions with the declared parameter names, and every such function is an
unimplemented stub (`raise NotImplementedError`). It does NOT assert any engine
behaves correctly. Per the rule below, once a stage is implemented its
NotImplementedError check is removed here: v5.4.0 Session 2 implemented the §17
debtor_party_engine, so that module is no longer covered by this test — its
behavior is gated by the §17 specs in scaffold/tests/v5_4_0/.

This test is wired into scaffold/tests/run_all.py and must pass at the end of
Session 1. It will KEEP passing through Sessions 2-5 only for stubs that are
still stubs; once a function is implemented its NotImplementedError check is
moved out of this file by that session.

Run: python3 scaffold/tests/v5_4_0/test_engine_stubs.py
Exit 0 = pass, non-zero = fail.
"""
import importlib
import inspect
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# module path -> {function name -> expected parameter names (in order)}.
ENGINE_SPEC = {
    "scaffold.pipeline.aggregation_key_engine": {
        "resolve_signal_type": ["canonical_doc_type", "signal_type_labels"],
        "compute_aggregation_key": ["parcel_id", "canonical_doc_type",
                                    "signal_type"],
        "aggregation_key_tuple": ["aggregation_key"],
    },
    "scaffold.pipeline.aggregator": {
        "aggregate": ["base_file_paths", "output_path"],
        "merge_signal_group": ["base_records"],
        "idempotency_self_check": ["base_file_paths", "output_path"],
    },
    "scaffold.pipeline.leads_base_writer": {
        "build_base_record": ["debtor_resolved_record", "signal_type_labels"],
        "write_leads_base": ["source_id", "base_records", "output_dir"],
    },
}

# How to invoke each stub so it reaches its `raise NotImplementedError`.
# Keyed (module, function) -> thunk. Args are throwaway — the stubs raise
# before using them.
_P = Path("unused_stub_path")
CALL_THUNKS = {
    ("scaffold.pipeline.aggregation_key_engine", "resolve_signal_type"):
        lambda m: m.resolve_signal_type("", signal_type_labels={}),
    ("scaffold.pipeline.aggregation_key_engine", "compute_aggregation_key"):
        lambda m: m.compute_aggregation_key(parcel_id=None,
                                            canonical_doc_type="",
                                            signal_type=""),
    ("scaffold.pipeline.aggregation_key_engine", "aggregation_key_tuple"):
        lambda m: m.aggregation_key_tuple({}),
    ("scaffold.pipeline.aggregator", "aggregate"):
        lambda m: m.aggregate([]),
    ("scaffold.pipeline.aggregator", "merge_signal_group"):
        lambda m: m.merge_signal_group([]),
    ("scaffold.pipeline.aggregator", "idempotency_self_check"):
        lambda m: m.idempotency_self_check([], output_path=_P),
    ("scaffold.pipeline.leads_base_writer", "build_base_record"):
        lambda m: m.build_base_record({}, signal_type_labels={}),
    ("scaffold.pipeline.leads_base_writer", "write_leads_base"):
        lambda m: m.write_leads_base("", [], output_dir=_P),
}

# The contract dataclasses that must exist alongside the engine stubs.
EXPECTED_DATACLASSES = [
    "RawEventRecord", "DebtorResolvedRecord", "LeadsBaseRecord",
    "SignalGroup", "MatchedLeadRecord", "EvidenceLedgerEntry",
    "Party", "PropertyRefs", "AggregationKey",
]


def main() -> int:
    failures = []
    stub_count = 0

    # The contracts package and its dataclasses must import.
    try:
        contracts = importlib.import_module("scaffold.pipeline.contracts")
        for dc in EXPECTED_DATACLASSES:
            if not hasattr(contracts, dc):
                failures.append(f"contracts package missing dataclass: {dc}")
    except Exception as exc:
        failures.append(f"scaffold.pipeline.contracts not importable — {exc}")

    for module_path, funcs in ENGINE_SPEC.items():
        try:
            module = importlib.import_module(module_path)
        except Exception as exc:
            failures.append(f"engine module not importable: {module_path} — {exc}")
            continue

        for func_name, expected_params in funcs.items():
            fn = getattr(module, func_name, None)
            if fn is None:
                failures.append(f"{module_path}.{func_name} — function missing")
                continue
            if not callable(fn):
                failures.append(f"{module_path}.{func_name} — not callable")
                continue

            # Signature: parameter names match the declared contract.
            actual_params = list(inspect.signature(fn).parameters.keys())
            if actual_params != expected_params:
                failures.append(
                    f"{module_path}.{func_name} — signature mismatch: "
                    f"expected {expected_params}, got {actual_params}"
                )

            # Behavior expected of a Session 1 stub: raise NotImplementedError.
            thunk = CALL_THUNKS.get((module_path, func_name))
            if thunk is None:
                failures.append(
                    f"{module_path}.{func_name} — test has no call thunk"
                )
                continue
            try:
                thunk(module)
                failures.append(
                    f"{module_path}.{func_name} — did not raise "
                    f"NotImplementedError (Session 1 stubs must)"
                )
            except NotImplementedError:
                stub_count += 1
            except Exception as exc:
                failures.append(
                    f"{module_path}.{func_name} — raised {type(exc).__name__} "
                    f"instead of NotImplementedError: {exc}"
                )

    if failures:
        print("FAIL: v5.4.0 engine-stub shape test")
        for f in failures:
            print(f"  - {f}")
        return 1

    print("PASS: v5.4.0 engine module stubs present and well-formed")
    print(f"  {len(ENGINE_SPEC)} engine modules importable; {stub_count} stub functions with "
          f"declared signatures, all raising NotImplementedError")
    return 0


if __name__ == "__main__":
    sys.exit(main())
