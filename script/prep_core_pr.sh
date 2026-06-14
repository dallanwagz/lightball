#!/usr/bin/env bash
# Stage the lightball integration + tests into a Home Assistant core checkout,
# applying the mechanical transforms a core PR needs:
#   - copy custom_components/lightball -> homeassistant/components/lightball
#   - strip the HACS-only manifest "version" key + sort manifest keys
#   - copy tests -> tests/components/lightball, rewriting the import root and
#     swapping the pytest-homeassistant-custom-component shim for core fixtures
#
# Usage: ./script/prep_core_pr.sh /path/to/home-assistant/core
set -euo pipefail

CORE="${1:?usage: prep_core_pr.sh /path/to/home-assistant/core}"
HERE="$(cd "$(dirname "$0")/.." && pwd)"
COMP="$CORE/homeassistant/components/lightball"
TESTS="$CORE/tests/components/lightball"

mkdir -p "$COMP/translations" "$TESTS"

# --- integration sources -----------------------------------------------------
cp "$HERE"/custom_components/lightball/*.py "$COMP"/
cp "$HERE"/custom_components/lightball/*.yaml "$COMP"/
cp "$HERE"/custom_components/lightball/strings.json "$COMP"/
cp "$HERE"/custom_components/lightball/translations/*.json "$COMP/translations"/

python3 - "$HERE/custom_components/lightball/manifest.json" "$COMP/manifest.json" <<'PY'
import json, sys
m = json.load(open(sys.argv[1]))
m.pop("version", None)  # forbidden in core
ordered = {k: m[k] for k in ("domain", "name") if k in m}
ordered.update({k: m[k] for k in sorted(m) if k not in ("domain", "name")})
with open(sys.argv[2], "w") as f:
    json.dump(ordered, f, indent=2)
    f.write("\n")
PY

# --- tests -------------------------------------------------------------------
touch "$TESTS/__init__.py"
for f in "$HERE"/tests/test_*.py; do
    sed 's/custom_components\.lightball/homeassistant.components.lightball/g' \
        "$f" > "$TESTS/$(basename "$f")"
done

# conftest: rewrite imports, drop the custom-component shim, use core fixtures
python3 - "$HERE/tests/conftest.py" "$TESTS/conftest.py" <<'PY'
import sys
s = open(sys.argv[1]).read()
s = s.replace("custom_components.lightball", "homeassistant.components.lightball")
s = s.replace(
    "from pytest_homeassistant_custom_component.common import MockConfigEntry",
    "from tests.common import MockConfigEntry",
)
s = s.replace('\npytest_plugins = "pytest_homeassistant_custom_component"\n', "")
block = (
    '@pytest.fixture(autouse=True)\n'
    'def auto_enable_custom_integrations(\n'
    '    enable_custom_integrations: None,\n'
    ') -> Generator[None]:\n'
    '    """Enable loading the lightball custom integration in every test."""\n'
    '    yield\n\n\n'
)
s = s.replace(block, "")
open(sys.argv[2], "w").write(s)
PY

echo "Staged into $CORE"
echo "Next:"
echo "  cd $CORE"
echo "  python -m script.hassfest -p lightball"
echo "  python -m pytest tests/components/lightball --cov=homeassistant.components.lightball"
