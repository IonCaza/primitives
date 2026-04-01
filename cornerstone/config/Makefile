.PHONY: test test-backend test-frontend test-e2e

test: test-backend test-frontend
	@echo "Backend and frontend unit tests passed."

test-backend:
	cd backend && pip install -q -r requirements.txt && python -m pytest tests -v

test-backend-cov:
	cd backend && pip install -q -r requirements.txt && python -m pytest tests --cov=app --cov-report=term-missing --cov-fail-under=25 -q

test-frontend:
	cd frontend && pnpm install --frozen-lockfile && pnpm run test:run

test-frontend-cov:
	cd frontend && pnpm run test:coverage

test-e2e:
	cd frontend && pnpm run test:e2e
