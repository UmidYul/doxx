from __future__ import annotations

from application.governance.dependency_policy import (
    classify_dependency_violation,
    infer_layer_from_module,
    is_dependency_allowed,
)


def test_domain_to_infrastructure_flagged() -> None:
    v = classify_dependency_violation("domain.foo", "infrastructure.transports.base")
    assert v is not None
    assert v.severity == "critical"
    assert "domain" in v.violated_rule


def test_application_to_tests_not_allowed() -> None:
    assert not is_dependency_allowed("application", "tests")


def test_infer_layer_from_dotted_module() -> None:
    assert infer_layer_from_module("domain.raw_product") == "domain"
    assert infer_layer_from_module("application/lifecycle/x.py") == "application"


def test_application_may_depend_on_infrastructure() -> None:
    assert is_dependency_allowed("application", "infrastructure")
