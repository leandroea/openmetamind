.PHONY: install test run streamlit slack format lint clean help

# Default target
help:
	@echo "OpenMetaMind - Makefile targets:"
	@echo ""
	@echo "  install    - Install dependencies and setup environment"
	@echo "  test       - Run tests with pytest"
	@echo "  run        - Run FastAPI backend server"
	@echo "  streamlit  - Run Streamlit UI"
	@echo "  slack      - Run Slack bot"
	@echo "  format     - Format code with black"
	@echo "  lint       - Lint code with ruff"
	@echo "  clean      - Clean up generated files"
	@echo ""

# Install dependencies
install:
	@echo "Installing OpenMetaMind..."
	python -m venv venv
	@if [ -f .env ]; then \
		echo "Using existing .env file"; \
	else \
		cp .env.example .env; \
		echo "Created .env from .env.example - please fill in your values"; \
	fi
	pip install -e ".[dev]"

# Run tests
test:
	@echo "Running tests..."
	pytest tests/ -v

# Run FastAPI backend
run:
	@echo "Starting FastAPI backend..."
	python -m src.main

# Run Streamlit UI
streamlit:
	@echo "Starting Streamlit UI..."
	streamlit run src/ui/streamlit_app.py

# Run Slack bot
slack:
	@echo "Starting Slack bot..."
	python src/ui/slack_bot.py

# Format code
format:
	@echo "Formatting code with black..."
	black src/ tests/ scripts/

# Lint code
lint:
	@echo "Linting code with ruff..."
	ruff check src/ tests/ scripts/

# Type check
typecheck:
	@echo "Type checking with mypy..."
	mypy src/

# Clean up
clean:
	@echo "Cleaning up..."
	rm -rf build/ dist/ *.egg-info
	rm -rf .pytest_cache .mypy_cache .ruff_cache
	rm -rf htmlcov .coverage
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
	rm -f checkpoints.db

# Docker targets
docker-build:
	@echo "Building Docker images..."
	docker-compose build

docker-up:
	@echo "Starting Docker services..."
	docker-compose up -d

docker-down:
	@echo "Stopping Docker services..."
	docker-compose down

# Development helpers
dev: install test

# Full test suite with coverage
test-cov:
	@echo "Running tests with coverage..."
	pytest tests/ --cov=src --cov-report=html --cov-report=term

# Run all checks
check: format lint typecheck test