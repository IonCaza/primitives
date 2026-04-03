# manifest.yaml Schema Reference

## Required Fields

| Field | Type | Description |
|-------|------|-------------|
| `name` | string | Kebab-case identifier matching the directory name |
| `version` | string | Semver version (e.g., "1.0.0") |
| `description` | string | What the primitive provides |
| `stack` | object | Technology requirements by layer |

## Stack Object

```yaml
stack:
  frontend: [react, next.js, ...]    # Frontend technologies
  backend: [python, fastapi, ...]    # Backend technologies
  persistence: [postgresql, ...]     # Data stores
  infrastructure: [docker, ...]      # Infrastructure tools
```

## Optional Fields

### requires_primitives

Other primitives that must or should be installed first.

```yaml
requires_primitives:
  - name: "other-primitive"
    reason: "Why this dependency exists"
    optional: false  # true = works without it but with reduced functionality
```

### provides

What the primitive adds to an application.

```yaml
provides:
  database_models:
    - ModelName
  api_routes:
    - { path: "/api/v1/resource", methods: [GET, POST], description: "..." }
  frontend_components:
    - ComponentName
  infrastructure_services:
    - service-name
```

### extension_points

Where applications are expected to customize.

```yaml
extension_points:
  - name: "Human-readable name"
    location: "relative/path/in/primitive/"
    description: "What can be customized here and how"
```

### extracted_from

Provenance tracking for each extraction.

```yaml
extracted_from:
  - repo: repo-name
    commit: abc123def
    date: "2026-03-31"
```

## Versioning Rules

- **Patch** (1.0.X): Bug fixes, doc improvements, no code changes affecting integration
- **Minor** (1.X.0): New features, new files, backward-compatible changes
- **Major** (X.0.0): Breaking changes to models, APIs, or integration steps
