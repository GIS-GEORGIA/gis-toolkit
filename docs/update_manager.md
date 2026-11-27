# Update Manager (`tools/update_manager.py`)

Checks the official GitHub Releases of `GIS-GEORGIA/gis-toolkit`, downloads and installs new versions **only with the user's consent**. Stdlib only, independent of the GIS modules and of any GUI.

## Flow
1. **Check** (`check_for_updates`) - never downloads, never raises (errors come back as `status="error"`). Stable: `/releases/latest`; with *Allow prerelease*: the highest version among the latest 15 non-draft releases.
2. **Download** (`download_asset(..., confirmed=True)`) - official URLs only, through a `.part` file; a failed/cancelled/mismatching download leaves nothing behind.
3. **Install** (`install_update(..., confirmed=True, verified=...)`) - extract to a staging folder, **backup**, apply file by file, **automatic rollback** on any failure.
4. **Roll back** (`rollback_update(backup, confirmed=True)`) - restores replaced files, removes added ones.

`confirmed=True` is enforced in the module itself (not only in the UI).

## Which package
`select_asset`: Windows x64 → `*.zip`; Linux → `*.tar.gz`, else `*.AppImage`, else `*.deb`. Only `.zip`/`.tar.gz` are installed automatically; `.deb`/`.AppImage` are downloaded and verified, then installed **manually** (no `sudo`, no admin rights, nothing downloaded is ever executed).

## Verification
| Check | Behaviour |
|---|---|
| SHA256 | from the GitHub API `digest`, `<asset>.sha256` or `SHA256SUMS`; mismatch → file deleted, `checksum` error |
| No checksum published | download works but the package is **unverified**: installing needs `allow_unverified=True` (the UI asks a second, explicit question) |
| Signed manifest | `SHA256SUMS` + `SHA256SUMS.sig` (Ed25519) is verified when `PUBLIC_KEY_B64` in `update_manager.py` is set (needs `cryptography`). Not configured yet → releases are reported as unsigned |
| Source | API only `api.github.com/repos/GIS-GEORGIA/gis-toolkit/...`; downloads only `github.com/GIS-GEORGIA/gis-toolkit/releases/download/...`; redirects only to https GitHub hosts; assets with foreign URLs are ignored |
| Archive | extracted by hand: no absolute paths, `..`, drive letters, symlinks/hardlinks/devices; size and file-count limits |

## Safety of the install
- User data is **never overwritten**: `config.txt`, `gis_box_settings.json`, `GIS_BOX_config/`, `shp_coords_templates.txt`, `map_services.txt`, `*.mdb`, logs, `.venv` (see `PRESERVE`).
- Backup = full copy of the application folder (without `.git`, `.venv`, `build`, `dist`, logs) + `.update_manifest.json`, stored in the per-user folder (`.../GIS_BOX/update_backups`), newest 3 kept.
- A git checkout (a `.git` folder) is **refused** - use `git pull` there.
- Files are replaced atomically one by one (temp file + `os.replace`).
- **Running Windows exe:** a file that is in use (`GIS_BOX.exe`, loaded DLL/pyd) cannot be overwritten but can be **renamed**. The installer renames it to `<name>.gbold-<n>`, puts the new file under the original name, and the leftover is deleted at the next start (`cleanup_on_start`). If the second step fails the original is put back, so the app is never left without the file. A few short retries (~1.5 s in total) cover files that an antivirus scanner or the indexer holds for a moment; a permanent lock still fails and rolls back. After the install the app offers **Restart now**. No helper program or downloaded script is involved. (Linux needs none of this: replacing a running binary by rename is allowed.)

## Settings (Updates page in V2)
Automatic check ON/OFF (default **OFF**, at most once a day, only shows a notification), notify ON/OFF, allow prereleases, installed/latest version, release date, last check time, release notes. Stored in `v2_settings.json` → `updates`.

## Release assets (CI)
`.github/workflows/release.yml` now publishes a `<asset>.sha256` next to every package. The workflow still only runs on a `v*` tag; **nothing is released automatically by this work**.

## Known limitations (honest)
- **Self-update of the running exe** works through the rename trick above and is tested with a really running executable and a really loaded DLL (`tests/test_update_manager.py`). **End-to-end test (2026-11-26):** a copy of the 2.0.0-dev Windows build updated itself from a temporary public prerelease `2.0.1-updatetest` (`GIS_BOX-windows-x64.zip`, 433 MB, + `.sha256`; tag without `v` so the release workflow did not run): check without prereleases = "latest" (v0.1.0 stable is older), with prereleases = 2.0.1-updatetest found, download with SHA256 verified, install while running (8887 files replaced, the running exe and loaded DLLs renamed to `.gbold-*`), restart = 2.0.1-updatetest, all `.gbold-*` removed at start; then **Roll back** = 2.0.0-dev after restart. The prerelease, its tag and all local test files were deleted afterwards. The rest of this list is unchanged.
- A file that is held open **without** share-delete (rare: a plain data file kept open by the app) cannot be renamed either: the installer rolls everything back and reports "files are in use - close GIS_BOX".
- Between the rename and the restart the running process still executes the old code from memory; restart after the update.
- Signature verification is implemented and tested but inactive until a public key is published in `PUBLIC_KEY_B64` and releases carry `.sig` files.
- Files removed in a newer version are not deleted from the old installation.
- Exercised once against a real (temporary) published release on Windows - see above. Linux packages (`.tar.gz` / `.deb` / `.AppImage`) have still only been tested with mocked network traffic.
- After the rename the updater runs under a `GIS_BOX.exe.gbold-*` process image name until the restart; tools that identify the window by its executable name (e.g. automation / screen-control software) see a different program name for that short time.
