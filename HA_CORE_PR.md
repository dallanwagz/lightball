# Home Assistant Core PR readiness — `lightball`

This branch (`ha-core-pr`) reshapes the integration to Home Assistant **Core**
standards. `main` stays HACS-installable (self-contained, `version` in the
manifest); this branch is what would be copied into `homeassistant/components/lightball`.

## What was done

**Architecture**
- Extracted all protocol + BLE code into a standalone library, **`lightball-ble`**,
  now its own public repo: https://github.com/dallanwagz/lightball-ble (CI +
  PyPI trusted-publishing workflows, 100% test coverage). The integration is now
  thin HA glue. (`dependency-transparency` is satisfied once that repo's `0.1.0`
  is published to PyPI.) The nested `lib/` here mirrors it for local test runs.
- `entry.runtime_data` (typed `LightBallConfigEntry = ConfigEntry[LightBallDevice]`)
  instead of `hass.data`. (`runtime-data`)
- `__init__.py` raises `ConfigEntryNotReady` when the ball isn't visible. (`test-before-setup`)
- Base entity in `entity.py`, constants in `const.py`. (`common-modules`)
- `light.py` sets `PARALLEL_UPDATES = 1` (serialize writes to a fragile BLE target),
  `_attr_assumed_state = True` (no readback), `_attr_has_entity_name = True`,
  `unique_id`, and a typed `DeviceInfo`.
- Availability + `entity-event-setup` via a Bluetooth advertisement callback.
- `diagnostics.py` added (no secrets to redact — the network key is a fixed
  product-line value, not user data).
- `quality_scale.yaml` declares Bronze with per-rule status; manifest sets
  `integration_type: device`, `iot_class: local_push`, `quality_scale: bronze`,
  `loggers`, and the `lightball-ble` requirement.

**Tests** (run with `pytest-homeassistant-custom-component`)
- `tests/` — config flow, init/unload/not-ready, device wrapper, light entity,
  diagnostics, advert callback.
- **100% coverage** of every integration module, **config_flow.py included**
  (the Bronze hard requirement), overall **100%** (exceeds Silver's >95%).
- `lib/tests/` — protocol byte-exactness (key + captured MultiColor bytes),
  split-write ordering, and the client connect/write/disconnect path. **100%**.
- `ruff check` and `ruff format --check` pass (E/F/W/I/UP/B/SIM/RET/PTH/ASYNC/C4/PIE/TID).

```
custom_components/lightball  201 stmts   100%   (22 tests)
lightball_ble (lib)          106 stmts   100%   (10 tests)
```

## Known deviation (worth a reviewer note)

The ball rotates its BLE address and exposes no IRK, so it is identified by its
**stable local name** (the config-entry `unique_id`), not `CONF_ADDRESS`. The
device wrapper resolves the current `BLEDevice` by name through
`bluetooth.async_discovered_service_info` before each command. This is the one
place the integration departs from the address-keyed BLE convention, and it is
intentional.

## Remaining before opening the PR (external, can't be done in-repo)

1. **Publish `lightball-ble` to PyPI** (repo ready at
   https://github.com/dallanwagz/lightball-ble — configure a PyPI trusted
   publisher, then cut a GitHub Release and the `publish.yml` workflow uploads
   it) and pin the exact version in `manifest.json` `requirements`. (Until then
   this branch won't load via HACS — that's why it's not on `main`.)
2. **Remove the `version` key** from `manifest.json` (forbidden in core; required
   for HACS, hence still present on this branch).
3. **Add brand assets** (icon + logo) via a PR to `home-assistant/brands`. (`brands`)
4. **Write documentation** at `home-assistant.io` (high-level description,
   installation, removal). (`docs-*`)
5. Run `python3 -m script.hassfest` inside a core checkout to regenerate
   `requirements_all.txt` / `CODEOWNERS`, and move the tests to
   `tests/components/lightball/`.

## Running the tests

```bash
python3.13 -m venv .venv-test
.venv-test/bin/pip install pytest-homeassistant-custom-component pytest-cov ruff
.venv-test/bin/pip install -e lib                       # the protocol/BLE library
.venv-test/bin/pip install aiousbwatcher bluetooth-auto-recovery \
    bluetooth-data-tools dbus-fast habluetooth pyserial  # bluetooth deps
.venv-test/bin/python -m pytest tests/ --cov=custom_components.lightball --cov-report=term-missing
.venv-test/bin/python -m pytest lib/tests/ --cov=lightball_ble --cov-report=term-missing
```
