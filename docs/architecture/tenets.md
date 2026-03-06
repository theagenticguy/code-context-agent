# Design Tenets

Principles for large codebase analysis. Listed in priority order.

These tenets assume the reality of most codebases: they are brownfield, messy, inconsistently named, partially documented, and evolved by multiple people over years. The consuming AI agent has never seen this code before and has a finite context window. Every design decision flows from these constraints.

---

## 1. Measure, don't guess

A file's importance comes from its position in the graph --not its name, size, or directory. We rank code by betweenness centrality, PageRank, and git coupling because these metrics surface what intuition misses -- the 50-line utility that 80% of the codebase depends on, the config file that co-changes with every feature.

!!! example "Tie-breaker"
    The agent finds `utils.py` with the highest betweenness centrality, and `PaymentService.py` with zero inbound references. We rank `utils.py` higher.

    **Why:** In brownfield codebases, naming conventions are unreliable. A file named "utils" might be the most critical module; a file named "PaymentService" might be dead code. Graph metrics are evidence; filenames are suggestions.

---

## 2. Layer signals, read less

Source code is one representation of a system among many. We combine five signal layers --static structure (AST/types), dynamic relationships (call graphs, references), temporal evolution (git history, churn, co-changes), compressed abstractions (signatures without bodies), and human intent (commit messages, naming) --because no single layer tells the full story. Multi-signal coverage across all files beats deep reading of a few.

!!! example "Tie-breaker"
    The agent has 2000 files and a time budget. It can either read the 50 most important-looking files in full, or run LSP + AST-grep + git coupling across all 2000 and read only the 10 that score highest across multiple signals. We choose multi-signal.

    **Why:** Most codebases have misleading entry points, stale READMEs, and logic scattered across unexpected files. Reading "obvious" files first is a trap --it biases toward well-named code and misses the messy reality. Casting a wide net with cheap signals finds the real hotspots.

---

## 3. Compress aggressively, expand selectively

Token budgets are finite. We start with the most compressed representation (file manifest -> token tree -> signatures -> graph metrics) and only expand to full source for code that earns it through high scores. Tree-sitter compression strips function bodies. Comment removal strips narration. Every token in the output bundle defends its presence.

!!! example "Tie-breaker"
    A 200-line file has 5 important functions and 15 boilerplate helpers. We bundle the compressed signatures-only version rather than the full file, saving 80% of tokens while preserving the API surface.

    **Why:** The consuming AI agent needs its context window for the actual task --answering questions, writing code, debugging. Wasting tokens on boilerplate in the context bundle directly reduces the quality of the agent's downstream work. Less context, better used, beats more context, poorly curated.

---

## 4. The model picks the depth

Analysis depth scales with codebase complexity, not user configuration. A 50-file project and a 5000-file monorepo need fundamentally different treatment. The model observes the file manifest, detects framework diversity, measures entrypoint count, and calibrates its effort. Users point at a repo; the model figures out the rest.

!!! example "Tie-breaker"
    We're deciding whether to add a `--depth` flag with "shallow/medium/deep/exhaustive" options. We choose not to --the model reads the file count and framework complexity from the manifest and self-calibrates.

    **Why:** Most users don't know how complex their codebase is relative to others. A developer who thinks their 300-file project is "big" would over-provision analysis; a developer on a 10K-file monorepo would under-provision. The model has better information for this decision than the user does.

---

## 5. Machines read it first

The primary consumer of our output is another AI agent, not a human reader. Every output --rankings, file lists, architectural diagrams, risk assessments --uses typed schemas, consistent table columns, and bounded diagrams. When choosing between a paragraph that explains well and a table that parses well, we choose the table.

!!! example "Tie-breaker"
    The agent writes the Architecture section of CONTEXT.md. It can produce three paragraphs of natural language explanation or a 12-node Mermaid diagram with a 2-sentence caption. We choose the diagram.

    **Why:** AI coding assistants parse structure natively --tables, code blocks, diagrams. They struggle to extract actionable information from prose. A ranked table with file paths and scores is immediately usable; a paragraph describing "key architectural components" requires the consuming agent to re-analyze what we already analyzed.

---

## 6. Fail loud, fill gaps

When a signal source is unavailable --no git history, LSP server won't start, AST-grep finds no matches --we surface it explicitly and compensate with remaining signals rather than silently producing lower-quality output. The consuming agent needs to know what it doesn't know.

!!! example "Tie-breaker"
    The LSP server fails to start for a Python project (missing `ty`). The agent can either silently skip LSP analysis and produce results from ripgrep + AST-grep alone, or report the failure prominently and note which rankings lack semantic data. We report the failure.

    **Why:** In messy brownfield codebases, tooling failures are common --missing type stubs, non-standard project layouts, unsupported frameworks. The consuming AI agent makes better decisions when it knows "these rankings are based on text search only, LSP was unavailable" than when it trusts rankings that silently lack a key signal.
