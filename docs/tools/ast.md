# AST Pattern Matching

The AST tools use [ast-grep](https://ast-grep.github.io/) for structural code search based on abstract syntax trees. Unlike text search (ripgrep), AST patterns match code structure regardless of formatting, variable names, or comments.

## Tools

### `astgrep_scan`

Scans files using a pattern string. Matches structural patterns in the AST:

```yaml
# Find all function definitions with a specific parameter pattern
pattern: "def $FUNC($PARAMS):"
```

### `astgrep_scan_rule_pack`

Runs a predefined rule pack against the codebase. Rule packs are YAML files containing multiple patterns designed to detect specific code patterns:

- **`py_business_logic.yml`** --- Python business logic patterns (decorators, class hierarchies, error handling, API endpoints)
- **`ts_business_logic.yml`** --- TypeScript business logic patterns (React components, hooks, API routes, middleware)

### `astgrep_inline_rule`

Executes a custom ast-grep rule defined inline. Provides full access to ast-grep's rule syntax including:

- Pattern matching with metavariables (`$VAR`)
- `has` / `not` / `inside` constraints
- Multiple patterns with `all` / `any` combinators

## Rule Packs

Rule packs are stored in `src/code_context_agent/rules/` and contain curated patterns for detecting business-critical code structures:

### Python (`py_business_logic.yml`)

Detects patterns like:
- FastAPI/Flask route handlers
- SQLAlchemy models and queries
- Pydantic model definitions
- Exception hierarchies
- Decorator-based configuration

### TypeScript (`ts_business_logic.yml`)

Detects patterns like:
- React component definitions
- Next.js API routes
- Express middleware chains
- TypeORM/Prisma models
- Custom hook definitions
