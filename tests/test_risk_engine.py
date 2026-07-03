from models.config import RiskConfig
from services.risk_engine import (
    evaluate_activity,
    evaluate_communication,
    expected_activities,
    overall_risk,
    weekly_distribution,
)


def test_expected_activities_15():
    assert [expected_activities(15, week, 5) for week in range(1, 6)] == [3, 6, 9, 12, 15]


def test_expected_activities_17_rounds_up():
    assert [expected_activities(17, week, 5) for week in range(1, 6)] == [4, 7, 11, 14, 17]


def test_distribution_sums_total():
    distribution = weekly_distribution(17, 5)
    assert sum(distribution) == 17
    assert distribution == [4, 3, 4, 3, 3]


def test_activity_risk():
    config = RiskConfig()
    assert evaluate_activity(8, 9, config).risk == "Bajo"
    assert evaluate_activity(5, 9, config).risk == "Moderado"
    assert evaluate_activity(4, 9, config).risk == "Alto"


def test_overall_uses_worst_available_indicator():
    config = RiskConfig()
    low = evaluate_activity(9, 9, config)
    high = evaluate_communication(None, 130, True, config)
    assert overall_risk([low, high]) == "Alto"
