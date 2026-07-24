import json
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone
import json

class ReportGenerator:
    def __init__(self, target_name: str, config: Any):
        self.target_name = target_name
        self.config = config
        self.meta = {
            "tool_version": "0.1.0",
            "target_name": target_name,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "corpus_size": 0,
            "total_queries": 0
        }
        self.summary = {
            "verdict": "PASS",
            "hallucination_rate": 0.0,
            "tests_passed": 0,
            "tests_failed": 0,
            "tests_skipped": 0
        }
        self.tests: Dict[str, Any] = {}

    def add_test_result(self, test_name: str, result: Dict[str, Any]):
        self.tests[test_name] = result
        if result.get("status") == "FAIL":
            self.summary["tests_failed"] += 1
        elif result.get("status") == "PASS":
            self.summary["tests_passed"] += 1
        else:
            self.summary["tests_skipped"] += 1

    def calculate_summary(self):
        # Update verdict based on failures
        if self.summary["tests_failed"] > 0:
            self.summary["verdict"] = "FAIL"
        
        # Pull specific metrics up to summary if they exist
        if "hallucination_rate" in self.tests:
            self.summary["hallucination_rate"] = self.tests["hallucination_rate"].get("score", 0.0)

    def to_dict(self) -> Dict[str, Any]:
        self.calculate_summary()
        return {
            "meta": self.meta,
            "summary": self.summary,
            "tests": self.tests
        }

    def save_json(self, path: str):
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, indent=2)

    def save_markdown(self, path: str):
        data = self.to_dict()
        md = [
            f"# Legal RAG Audit Report: {data['meta']['target_name']}",
            f"**Date:** {data['meta']['timestamp']}",
            f"**Verdict:** {data['summary']['verdict']}",
            "",
            "## Summary",
            f"- **Tests Passed:** {data['summary']['tests_passed']}",
            f"- **Tests Failed:** {data['summary']['tests_failed']}",
            f"- **Tests Skipped:** {data['summary']['tests_skipped']}",
            f"- **Hallucination Rate:** {data['summary']['hallucination_rate'] * 100:.2f}%",
            "",
            "## Test Details"
        ]
        
        for test_name, result in data['tests'].items():
            status_icon = "✅" if result.get("status") == "PASS" else "❌" if result.get("status") == "FAIL" else "⏭️"
            md.append(f"### {status_icon} {test_name.replace('_', ' ').title()}")
            for k, v in result.items():
                if k not in ("status", "details"):
                    md.append(f"- **{k}:** {v}")
            if "details" in result and result["details"]:
                md.append("\n**Failures/Details:**")
                for item in result["details"]:
                    md.append(f"```json\n{json.dumps(item, indent=2)}\n```")
            md.append("")
            
        with open(path, "w", encoding="utf-8") as f:
            f.write("\n".join(md))
