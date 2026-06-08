#!/bin/bash
set -euo pipefail

echo "=== Centrica Trading Demo — Database Setup ==="

# Install PostgreSQL
echo "[1/5] Installing PostgreSQL..."
sudo apt-get update -qq
sudo apt-get install -y -qq postgresql postgresql-client

# Start PostgreSQL
echo "[2/5] Starting PostgreSQL..."
sudo service postgresql start

# Create database and user
echo "[3/5] Creating database and user..."
sudo -u postgres psql -c "DROP DATABASE IF EXISTS centrica_trading;" 2>/dev/null || true
sudo -u postgres psql -c "DROP USER IF EXISTS centrica_demo;" 2>/dev/null || true
sudo -u postgres psql -c "CREATE DATABASE centrica_trading;"
sudo -u postgres psql -c "CREATE USER centrica_demo WITH PASSWORD 'demo_password';"
sudo -u postgres psql -c "GRANT ALL PRIVILEGES ON DATABASE centrica_trading TO centrica_demo;"
sudo -u postgres psql -c "ALTER USER centrica_demo CREATEDB;"

# Load schema and data
echo "[4/5] Loading schema..."
sudo -u postgres psql -d centrica_trading -f schema.sql

echo "[4/5] Loading seed data (this may take a moment)..."
sudo -u postgres psql -d centrica_trading -f seed_data.sql

# Grant permissions
echo "[5/5] Granting permissions..."
sudo -u postgres psql -d centrica_trading -c "GRANT ALL ON ALL TABLES IN SCHEMA public TO centrica_demo;"
sudo -u postgres psql -d centrica_trading -c "GRANT ALL ON ALL SEQUENCES IN SCHEMA public TO centrica_demo;"

echo ""
echo "=== Setup complete! ==="
echo ""
echo "Connect with:"
echo "  postgresql://centrica_demo:demo_password@localhost:5432/centrica_trading"
echo ""
echo "Quick test:"
echo "  psql postgresql://centrica_demo:demo_password@localhost:5432/centrica_trading -c 'SELECT COUNT(*) FROM trades;'"
