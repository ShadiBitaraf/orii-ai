#!/usr/bin/env python3
"""
Prompt Engineering Tracker Utility

This script helps manage your prompt engineering documentation,
allowing you to add new issues, track iterations, and generate reports.
"""

import json
import datetime
from typing import Dict, List, Optional


class PromptTracker:
    def __init__(self, data_file: str = "prompt_engineering_data.json"):
        self.data_file = data_file
        self.data = self.load_data()

    def load_data(self) -> Dict:
        """Load data from JSON file"""
        try:
            with open(self.data_file, "r") as f:
                return json.load(f)
        except FileNotFoundError:
            return self.create_empty_structure()

    def save_data(self):
        """Save data to JSON file"""
        self.data["metadata"]["last_updated"] = datetime.date.today().isoformat()
        with open(self.data_file, "w") as f:
            json.dump(self.data, f, indent=2)

    def add_issue(
        self,
        category: str,
        title: str,
        user_input: str,
        current_response: str,
        expected_response: str,
        root_cause: str,
        priority: str = "medium",
    ):
        """Add a new issue to track"""

        # Generate issue ID
        category_prefix = category.split("_")[0][:2].upper()
        existing_ids = [
            k for k in self.data["issues"].keys() if k.startswith(category_prefix)
        ]
        next_num = len(existing_ids) + 1
        issue_id = f"{category_prefix}-{next_num:03d}"

        issue = {
            "title": title,
            "category": category,
            "status": "open",
            "priority": priority,
            "date_created": datetime.date.today().isoformat(),
            "current_iteration": 1,
            "user_input": user_input,
            "current_response": current_response,
            "expected_response": expected_response,
            "root_cause": root_cause,
            "proposed_solutions": [],
            "iterations": [],
        }

        self.data["issues"][issue_id] = issue
        self.data["metadata"]["total_issues"] += 1
        self.save_data()
        return issue_id

    def add_iteration(
        self,
        issue_id: str,
        changes_made: List[str],
        test_input: str,
        test_output: str,
        success: bool,
        notes: str,
    ):
        """Add an iteration to an existing issue"""
        if issue_id not in self.data["issues"]:
            raise ValueError(f"Issue {issue_id} not found")

        iteration = {
            "iteration": self.data["issues"][issue_id]["current_iteration"] + 1,
            "date": datetime.date.today().isoformat(),
            "changes_made": changes_made,
            "test_results": {
                "input": test_input,
                "output": test_output,
                "success": success,
            },
            "notes": notes,
        }

        self.data["issues"][issue_id]["iterations"].append(iteration)
        self.data["issues"][issue_id]["current_iteration"] += 1

        if success:
            self.data["issues"][issue_id]["status"] = "resolved"

        self.save_data()

    def get_open_issues_by_priority(self) -> Dict[str, List]:
        """Get open issues grouped by priority"""
        priorities = {"critical": [], "high": [], "medium": [], "low": []}

        for issue_id, issue in self.data["issues"].items():
            if issue["status"] == "open":
                priorities[issue["priority"]].append(
                    {
                        "id": issue_id,
                        "title": issue["title"],
                        "category": issue["category"],
                    }
                )

        return priorities

    def generate_progress_report(self) -> str:
        """Generate a progress report"""
        total_issues = len(self.data["issues"])
        open_issues = len(
            [i for i in self.data["issues"].values() if i["status"] == "open"]
        )
        resolved_issues = total_issues - open_issues

        report = f"""
# Progress Report - {datetime.date.today().isoformat()}

## Overview
- **Total Issues**: {total_issues}
- **Open Issues**: {open_issues}
- **Resolved Issues**: {resolved_issues}
- **Success Rate**: {(resolved_issues/total_issues*100):.1f}%

## Priority Breakdown
"""

        priorities = self.get_open_issues_by_priority()
        for priority, issues in priorities.items():
            if issues:
                report += f"\n### {priority.upper()} Priority ({len(issues)} issues)\n"
                for issue in issues:
                    report += (
                        f"- {issue['id']}: {issue['title']} ({issue['category']})\n"
                    )

        return report

    def get_test_cases_by_status(self) -> Dict[str, List]:
        """Get test cases grouped by status"""
        status_groups = {"failing": [], "passing": [], "untested": []}

        for category, test_cases in self.data["test_cases"].items():
            for test_case in test_cases:
                status_groups[test_case["status"]].append(
                    {
                        "category": category,
                        "input": test_case["input"],
                        "expected": test_case["expected"],
                    }
                )

        return status_groups


def main():
    """Simple CLI interface"""
    tracker = PromptTracker()

    print("🔍 Prompt Engineering Tracker")
    print("=" * 40)

    # Show current status
    priorities = tracker.get_open_issues_by_priority()
    print(f"📊 Open Issues: {sum(len(issues) for issues in priorities.values())}")

    for priority, issues in priorities.items():
        if issues:
            print(f"  {priority.upper()}: {len(issues)}")

    print("\n" + tracker.generate_progress_report())


if __name__ == "__main__":
    main()
