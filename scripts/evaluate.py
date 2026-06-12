"""Evaluate the Aliyun OSS Support RAG pipeline on a small benchmark."""

from __future__ import annotations

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from aliyun_oss_rag import agent as agent_module  # noqa: E402


class EvaluationLLM:
    def generate(self, prompt: str) -> str:
        return f"{prompt}\n答案：以上内容来自 OSS 检索资料。"

    def stream_events(self, prompt: str):
        yield {"type": "content", "content": self.generate(prompt)}


def main() -> None:
    benchmark_path = PROJECT_ROOT / "data" / "eval" / "benchmark.json"
    benchmark = json.loads(benchmark_path.read_text(encoding="utf-8"))
    agent_module.get_llm = lambda settings=None: EvaluationLLM()
    agent = agent_module.AliyunOssAgent()
    rows = []
    for case in benchmark:
        response = agent.run(case["question"])
        include_hits = [term for term in case["must_include"] if term.lower() in response.answer.lower()]
        rows.append(
            {
                "id": case["id"],
                "question": case["question"],
                "expected_intent": case["expected_intent"],
                "actual_intent": response.intent,
                "intent_ok": response.intent == case["expected_intent"],
                "include_hits": include_hits,
                "include_ok": len(include_hits) == len(case["must_include"]),
                "citation_count": len(response.citations),
                "tool_calls": [call.name for call in response.tool_calls],
                "answer_preview": response.answer[:180],
            }
        )
    total = len(rows)
    summary = {
        "total": total,
        "intent_accuracy": round(sum(row["intent_ok"] for row in rows) / total, 3),
        "must_include_accuracy": round(sum(row["include_ok"] for row in rows) / total, 3),
        "citation_rate": round(sum(1 for row in rows if row["citation_count"] > 0) / total, 3),
    }
    result = {"summary": summary, "cases": rows}
    results_path = PROJECT_ROOT / "data" / "eval" / "results.json"
    results_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
