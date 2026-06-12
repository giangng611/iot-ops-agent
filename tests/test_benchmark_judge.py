import unittest

from scripts.judge_runtime_results import (
    aggregate_judgments,
    build_judge_prompt,
    has_tool_evidence,
)


class BenchmarkJudgeTests(unittest.TestCase):
    def test_judge_prompt_hides_runtime_identity(self):
        prompt = build_judge_prompt({
            "mode": "IOA v2 - Secret Runtime",
            "prompt": "show fleet health",
            "expected_focus": "fleet summary",
            "reference_context_json": '{"total_devices": 2}',
            "answer": "There are two devices.",
        })

        self.assertNotIn("Secret Runtime", prompt)
        self.assertIn("There are two devices.", prompt)

    def test_tool_evidence_requires_action_and_output(self):
        self.assertTrue(has_tool_evidence({
            "steps_json": (
                '[{"action":"check_system_overview",'
                '"output":{"total_devices":2}}]'
            ),
        }))
        self.assertFalse(has_tool_evidence({
            "steps_json": '[{"action":"check_system_overview","output":{}}]',
        }))
        self.assertFalse(has_tool_evidence({"steps_json": "not-json"}))

    def test_aggregate_uses_median_scores(self):
        judgments = [
            {
                "factual_correctness": 1,
                "evidence_grounding": 2,
                "task_completion": 3,
                "actionability": 4,
                "source_discipline": 5,
                "critical_error": True,
                "rationale": "first",
            },
            {
                "factual_correctness": 5,
                "evidence_grounding": 4,
                "task_completion": 3,
                "actionability": 2,
                "source_discipline": 1,
                "critical_error": False,
                "rationale": "second",
            },
            {
                "factual_correctness": 4,
                "evidence_grounding": 4,
                "task_completion": 4,
                "actionability": 4,
                "source_discipline": 4,
                "critical_error": False,
                "rationale": "third",
            },
        ]

        result = aggregate_judgments(judgments)

        self.assertEqual(result["factual_correctness"], 4)
        self.assertEqual(result["evidence_grounding"], 4)
        self.assertEqual(result["quality_score"], 3.8)
        self.assertTrue(result["critical_error"])


if __name__ == "__main__":
    unittest.main()
