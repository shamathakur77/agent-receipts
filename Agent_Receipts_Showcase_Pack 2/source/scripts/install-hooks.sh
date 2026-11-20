#!/bin/sh
# Installs a plain git pre-commit hook that runs the secret scan. No pre-commit framework needed.
set -e
root="$(git rev-parse --show-toplevel)"
cat > "$root/.git/hooks/pre-commit" <<'EOF'
#!/bin/sh
exec python3 "$(git rev-parse --show-toplevel)/scripts/secret_scan.py" --staged
EOF
chmod +x "$root/.git/hooks/pre-commit"
echo "pre-commit hook installed"
