.PHONY: help install install-dev test run demo roi docker docker-run clean

PORT ?= 8000

help:
	@echo "SupportCopilot — make targets"
	@echo "  make install      install runtime dependencies"
	@echo "  make install-dev  install dev dependencies (incl. pytest)"
	@echo "  make test         run the test suite (offline, no API keys)"
	@echo "  make demo         launch the app locally and print the URL"
	@echo "  make run          alias for 'make demo'"
	@echo "  make roi          print the ROI report to the terminal"
	@echo "  make docker       build the Docker image"
	@echo "  make docker-run   run the Docker image on port $(PORT)"

install:
	pip install -r requirements.txt

install-dev:
	pip install -r requirements-dev.txt

test:
	LLM_PROVIDER=stub python -m pytest -q

roi:
	python -m supportcopilot.cli roi

demo:
	@echo ""
	@echo "  SupportCopilot is starting (offline stub — no API key needed)."
	@echo "  Chat:      http://localhost:$(PORT)/"
	@echo "  Dashboard: http://localhost:$(PORT)/dashboard"
	@echo ""
	python -m uvicorn supportcopilot.app:app --host 0.0.0.0 --port $(PORT) --reload

run: demo

docker:
	docker build -t supportcopilot:latest .

docker-run:
	docker run --rm -p $(PORT):8000 supportcopilot:latest

clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .pytest_cache -exec rm -rf {} + 2>/dev/null || true
