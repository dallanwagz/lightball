# Brand assets for the `lightball` integration

These are the icon/logo assets for submission to
[home-assistant/brands](https://github.com/home-assistant/brands), required before
a core integration can merge (`brands` quality-scale rule).

```
core_integrations/lightball/
  icon.png       256x256   (the orb)
  icon@2x.png    512x512
  logo.png       512x512
  logo@2x.png    1024x1024
```

All are square PNGs with transparent backgrounds (a glowing RGB orb, matching the
physical product).

## Submitting

1. Fork `home-assistant/brands`.
2. Copy `core_integrations/lightball/` into the fork's `core_integrations/`.
3. Run their `python3 -m script.optimize` (optimizes/validates the PNGs).
4. Open a PR. The brands PR can land in parallel with the integration PR.

> The orb here is generated (see the project's `script/`); if you'd prefer the
> official product mark, drop the real artwork in at the same sizes before
> submitting.
