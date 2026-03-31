# <Primitive Name> -- Integration Guide

> This document is designed for AI agent consumption. Each section provides
> step-by-step instructions with canonical code and adaptation notes.

## Prerequisites

<!-- What must exist in the target app before this primitive can be integrated -->

- [ ] Prerequisite 1
- [ ] Prerequisite 2

## 1. Database Layer

### 1.1 Models

<!-- List each model that must be added. Include the canonical code from schema/models.py -->

**Adaptation notes:**
- Update import paths for your project's `Base` declarative base
- Update any foreign key references to match your User model

### 1.2 Migration

<!-- Provide the SQL or Alembic migration instructions -->

## 2. Backend Layer

### 2.1 Dependencies

<!-- List pip packages to add to requirements.txt -->

### 2.2 Module Placement

<!-- Where to copy backend code and what import paths to update -->

**Adaptation notes:**
- Update all `from app.` imports to match your project structure

### 2.3 Router Registration

<!-- How to register API routes in main.py or equivalent -->

### 2.4 Startup Hooks

<!-- Any initialization that must run at app startup -->

### 2.5 Environment Variables

<!-- Required env vars with descriptions -->

## 3. Frontend Layer

### 3.1 Dependencies

<!-- npm/pnpm packages to install -->

### 3.2 Component Placement

<!-- Where to place components and how to wire them into the app -->

### 3.3 Provider Wiring

<!-- Context providers, runtime providers, etc. -->

### 3.4 API Client

<!-- Methods to add to the API client -->

### 3.5 Types

<!-- TypeScript types to add -->

## 4. Infrastructure

<!-- Docker compose fragments, config files, etc. -->

## 5. Extension Points

<!-- How to customize this primitive for domain-specific needs -->

## 6. Verification

<!-- How to confirm the integration works end-to-end -->

- [ ] Verification step 1
- [ ] Verification step 2
