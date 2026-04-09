from __future__ import annotations

from backend.services.analysis import (
    _build_analysis_payload,
    _collect_agent_outputs,
)


def test_collect_agent_outputs_prefers_standardized_agent_outputs():
    all_agents = {
        "technical_analyst_agent": {
            "latest": {
                "output_state": {
                    "data": {
                        "agent_outputs": {
                            "technicals": {
                                "signal": "bullish",
                                "confidence": "80%",
                                "agent_type": "rule_engine",
                            }
                        },
                        "technical_analysis": {
                            "signal": "bearish",
                            "confidence": "20%",
                        },
                    },
                    "messages": [
                        {
                            "content": '{"signal": "neutral", "confidence": "50%"}',
                            "type": "human",
                        }
                    ],
                },
                "technical_analyst_agent_reasoning": {
                    "signal": "bearish",
                    "confidence": "10%",
                },
            }
        }
    }

    agent_outputs = _collect_agent_outputs(
        agent_names=["technical_analyst_agent"],
        all_agents=all_agents,
    )

    assert agent_outputs == {
        "technicals": {
            "signal": "bullish",
            "confidence": "80%",
            "agent_type": "rule_engine",
        }
    }


def test_collect_agent_outputs_falls_back_to_last_message_and_reasoning():
    all_agents = {
        "fundamentals_agent": {
            "latest": {
                "output_state": {
                    "data": {
                        "fundamental_analysis": {
                            "signal": "bullish",
                            "confidence": "75%",
                            "reasoning": {"profitability_signal": {"signal": "bullish"}},
                        }
                    },
                    "messages": [
                        {
                            "content": '{"signal": "neutral", "confidence": "50%"}',
                            "type": "human",
                        }
                    ],
                },
            }
        },
        "researcher_bull": {
            "latest": {
                "researcher_bull_reasoning": {
                    "perspective": "bull",
                    "thesis_points": ["盈利改善", "估值处于低位"],
                    "confidence": 0.76,
                }
            }
        },
    }

    agent_outputs = _collect_agent_outputs(
        agent_names=["fundamentals_agent", "researcher_bull"],
        all_agents=all_agents,
    )

    assert agent_outputs["fundamentals"]["signal"] == "bullish"
    assert agent_outputs["fundamentals"]["confidence"] == "75%"
    assert agent_outputs["researcher_bull"]["perspective"] == "bull"
    assert len(agent_outputs["researcher_bull"]["thesis_points"]) == 2


def test_collect_agent_outputs_supports_relative_valuation_alias_from_legacy_data():
    all_agents = {
        "technical_analyst_agent": {
            "latest": {
                "output_state": {
                    "data": {
                        "relative_valuation_analysis": {
                            "signal": "neutral",
                            "confidence": "55%",
                            "analysis_domain": "relative_valuation",
                        }
                    }
                }
            }
        }
    }

    agent_outputs = _collect_agent_outputs(
        agent_names=["technical_analyst_agent"],
        all_agents=all_agents,
    )

    assert agent_outputs == {
        "technicals": {
            "signal": "neutral",
            "confidence": "55%",
            "analysis_domain": "relative_valuation",
        }
    }


def test_collect_agent_outputs_supports_relative_valuation_agent_name_alias():
    all_agents = {
        "relative_valuation": {
            "latest": {
                "output_state": {
                    "data": {
                        "relative_valuation_analysis": {
                            "signal": "bullish",
                            "confidence": "70%",
                            "analysis_domain": "relative_valuation",
                        }
                    }
                }
            }
        }
    }

    agent_outputs = _collect_agent_outputs(
        agent_names=["relative_valuation"],
        all_agents=all_agents,
    )

    assert agent_outputs == {
        "technicals": {
            "signal": "bullish",
            "confidence": "70%",
            "analysis_domain": "relative_valuation",
        }
    }


def test_build_analysis_payload_exposes_agent_outputs_as_primary_contract():
    agent_outputs = {
        "technicals": {"signal": "bullish", "confidence": "80%"},
        "risk_manager": {"signal": "neutral", "confidence": "60%"},
    }

    payload = _build_analysis_payload(
        ticker="000001",
        run_id="run-123",
        final_decision={"action": "buy", "confidence": 0.82},
        agent_outputs=agent_outputs,
        completion_time="2026-04-08T12:00:00+00:00",
    )

    assert payload["ticker"] == "000001"
    assert payload["run_id"] == "run-123"
    assert payload["final_decision"]["action"] == "buy"
    assert payload["agent_outputs"] == agent_outputs
    assert payload["agent_results"] == agent_outputs


def test_build_analysis_payload_normalizes_relative_valuation_agent_output_alias():
    payload = _build_analysis_payload(
        ticker="000001",
        run_id="run-relative-valuation",
        final_decision={"action": "hold", "confidence": 0.6},
        agent_outputs={
            "relative_valuation": {
                "signal": "neutral",
                "confidence": "55%",
                "analysis_domain": "relative_valuation",
            }
        },
        completion_time="2026-04-08T12:00:00+00:00",
    )

    assert "relative_valuation" not in payload["agent_outputs"]
    assert payload["agent_outputs"]["technicals"]["analysis_domain"] == "relative_valuation"
    assert "relative_valuation" not in payload["agent_results"]
    assert payload["agent_results"]["technicals"]["confidence"] == "55%"
