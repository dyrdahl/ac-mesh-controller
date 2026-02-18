# AC Mesh Controller - Development Commands

# Default recipe
default:
    @just --list

# Start the FastAPI backend
api:
    cd pi_controller/api && uvicorn main:app --reload --host 0.0.0.0 --port 8000

# Start the Vue frontend dev server
web:
    cd pi_controller/web && npm run dev

# Install frontend dependencies
web-install:
    cd pi_controller/web && npm install

# Build frontend for production
web-build:
    cd pi_controller/web && npm run build

# Start both API and web in parallel (requires terminal multiplexer)
dev:
    @echo "Run 'just api' and 'just web' in separate terminals"

# Run the main controller (on Pi only)
controller:
    cd pi_controller && python controller.py
