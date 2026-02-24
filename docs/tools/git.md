# Git History Analysis

The git tools analyze repository history to surface temporal patterns that static analysis misses. Files that change frequently, change together, or have concentrated ownership reveal different insights than dependency graphs alone.

## Tools

### `git_hotspots`

Identifies files with the highest change frequency (churn). High-churn files are candidates for close inspection --- they may represent active development areas, unstable interfaces, or frequently-patched bugs.

### `git_files_changed_together`

Detects coupling between files based on co-change frequency. Files that consistently appear in the same commits likely have logical dependencies even if there's no import relationship.

This is particularly valuable for:

- Finding hidden dependencies not captured by import analysis
- Detecting configuration files that co-change with specific modules
- Identifying test files that correspond to implementation files

### `git_blame_summary`

Summarizes authorship distribution for a file. Shows which developers own which sections, revealing knowledge concentration and potential review bottlenecks.

### `git_file_history`

Retrieves the commit history for a specific file. Shows the evolution of a file over time, including commit messages that explain the "why" behind changes.

### `git_contributors`

Lists contributors to the repository with commit counts and recency. Helps identify active maintainers and domain experts.

### `git_recent_commits`

Retrieves recent commits across the repository. Provides context about current development activity and recent changes that may affect analysis.

### `git_diff_file`

Shows the diff for a specific file between two commits or against the working tree. Used to understand recent changes to high-scoring files.
