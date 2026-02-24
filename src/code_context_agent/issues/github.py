"""GitHub issue provider using gh CLI."""

from __future__ import annotations

import json
import re
import subprocess

from . import Issue, IssueComment, IssueProvider


class GitHubIssueProvider(IssueProvider):
    """Fetch GitHub issues using the gh CLI (deterministic, not model-invoked)."""

    def fetch(self, ref: str) -> Issue:
        """Fetch a GitHub issue.

        Args:
            ref: Issue reference. Formats:
                - "1694" (issue number in current repo)
                - "owner/repo#1694" (full reference)

        Returns:
            Normalized Issue object.
        """
        # Parse reference
        repo_flag = []
        match = re.match(r"^([^#]+)#(\d+)$", ref)
        if match:
            repo_flag = ["--repo", match.group(1)]
            issue_number = match.group(2)
        else:
            issue_number = ref

        cmd = [
            "gh", "issue", "view", issue_number,
            "--json", "title,body,state,labels,comments,url",
            *repo_flag,
        ]

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30,
            )
        except (subprocess.SubprocessError, OSError) as e:
            raise RuntimeError(f"Failed to fetch GitHub issue {ref}: {e}") from e

        if result.returncode != 0:
            raise RuntimeError(
                f"gh issue view failed (exit {result.returncode}): {result.stderr.strip()}",
            )

        data = json.loads(result.stdout)

        comments = [
            IssueComment(
                author=c.get("author", {}).get("login", "unknown"),
                body=c.get("body", ""),
                created_at=c.get("createdAt", ""),
            )
            for c in data.get("comments", [])
        ]

        labels = [label.get("name", "") for label in data.get("labels", [])]

        return Issue(
            provider="github",
            ref=f"gh:{ref}",
            title=data.get("title", ""),
            body=data.get("body", ""),
            state=data.get("state", "unknown"),
            labels=labels,
            comments=comments,
            url=data.get("url"),
        )


def parse_issue_ref(ref_string: str) -> tuple[str, str]:
    """Parse a --issue flag value into (provider, ref).

    Args:
        ref_string: e.g., "gh:1694", "gh:owner/repo#1694", "jira:PROJ-123"

    Returns:
        Tuple of (provider_name, reference)

    Raises:
        ValueError: If format is not recognized
    """
    if ":" not in ref_string:
        raise ValueError(
            f"Invalid issue reference: {ref_string}. "
            "Expected format: provider:ref (e.g., gh:1694, gh:owner/repo#1694)",
        )
    provider, ref = ref_string.split(":", 1)
    return provider.lower(), ref
