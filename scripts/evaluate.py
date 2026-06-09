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

    md_lines = [
        "# 测试与评估报告",
        "",
        "本评估用于课程项目自测，覆盖阿里云 OSS 技术支持问答、权限配置、API 参考、故障排查和成本优化，检查意图识别、关键字段覆盖和引用覆盖。",
        "",
        f"- 样例数：{summary['total']}",
        f"- 意图识别准确率：{summary['intent_accuracy']}",
        f"- 关键字段覆盖率：{summary['must_include_accuracy']}",
        f"- 引用覆盖率：{summary['citation_rate']}",
        "",
        "| ID | 问题 | 期望意图 | 实际意图 | 关键字段通过 | 引用数 |",
        "|---|---|---|---|---:|---:|",
    ]
    for row in rows:
        md_lines.append(
            f"| {row['id']} | {row['question']} | {row['expected_intent']} | {row['actual_intent']} | {row['include_ok']} | {row['citation_count']} |"
        )
    report_path = PROJECT_ROOT / "docs" / "evaluation_report.md"
    report_path.write_text("\n".join(md_lines), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
