# Launcher icons

`icon-profiles.json` is the source of truth for launcher PNG sizes:

| Display resolution | Icon pixels |
| --- | --- |
| 368x448, 448x368 | 128x128 |
| 410x502, 502x410 | 144x144 |

From the app repository, run `npm install` then `npm run icons` (Node.js and sharp 0.35.5).
Normal APP validation/packing does not require Node or sharp; generated PNGs are stored in the repository.

The generator renders SVG at high resolution and downsamples with Lanczos, retaining RGBA transparency.
It replaces only launcher icon variants under assets/<resolution>/ and generates
`apps/homepage/src/icon_profiles.lua`. Root PNGs remain generic fallback assets.
Home uses native sizes at these four resolutions, with bounds clamping for unusually small viewports.
Unknown resolutions retain the original responsive fallback.

Sources:
- `icons/app-default.svg`: the existing Homepage fallback artwork.
- `icons/system-settings-icon.svg`: imported from the user's q2-ui original SVG.
- `icons/music.svg`: vector transcription of the project's geometric record-player icon from
  `scripts/generate_music_assets.py`.

These are launch icons; status-bar icons, playback controls and wallpapers keep their existing resources.
Do not edit generated Lua separately. Change the profile JSON and regenerate both images and Lua.
