from __future__ import annotations

from snowwatch import classifier


def test_migration_intent(migration_signal):
    assert classifier.classify(migration_signal) == classifier.MIGRATION_INTENT


def test_cost_pain(cost_signal):
    assert classifier.classify(cost_signal) == classifier.COST_PAIN


def test_performance_complaint(performance_signal):
    assert classifier.classify(performance_signal) == classifier.PERFORMANCE_COMPLAINT


def test_other_for_neutral(neutral_signal):
    assert classifier.classify(neutral_signal) == classifier.OTHER


def test_classify_sets_attribute(cost_signal):
    classifier.classify(cost_signal)
    assert cost_signal.category == classifier.COST_PAIN
