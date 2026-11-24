# professional-distribution

Turn phone-mic from a working checkout into something a stranger can install and
keep: a self-contained per-user install, an environment preflight with actionable
messages, an install smoke test and an MIT license. Scope agreed with the owner:
Bloque 1 only, no AUR packaging in this round.

## Specs

S1. License: MIT. The owner selected "MIT" when asked which license to use.

S2. Scope for this round is the owner-selected option "Bloque 1: hacerlo
instalable de verdad": license, self-contained install, `--uninstall`,
`--version`, environment check and an install test. Nothing from Bloque 2 (AUR
package, tags, CHANGELOG) and nothing from Bloque 3.

S3. The program must be usable by someone who, in the owner's words, "tiene el
mismo problema que yo tuve", without keeping the git checkout. Installed
artifacts must run from the install prefix, never from the repository path.
Deleting or moving the checkout must not break the installed command or the
bridge service.

S4. The install stays per-user: no root, and nothing written under `/usr` or
`/etc`. This preserves the existing project rule.

S5. Existing behaviour is preserved: the `phone-mic` panel, `start`, `stop` and
`status` keep working; the bridge unit is still NOT enabled at login; the
installer still never restarts PipeWire.

S6. Uninstall removes exactly what the installer created. Runtime leftovers that
only disappear with a PipeWire restart are reported, never cleared by restarting
the audio server.

S7. Environment problems are reported before the install finishes, with the
command that fixes each one. A missing `scrcpy` older than 3.2, an unreachable
`pipewire-pulse` and a missing `adb` are named explicitly.

## Tasks

One line per task: ID, specs, route, commit.

- T1 — Add the MIT license and point the README at it. S1. inline.
  `docs(license): add the MIT license` — done, `136195c`.
- T2 — Self-contained install: copy `tui/`, `scripts/`, `conf/` and the docs into
  the install prefix, generate the wrapper and the unit at that prefix, add
  `--prefix`, `--version` and `--uninstall`. S2 S3 S4 S5 S6. worker.
  `feat(packaging): install a self-contained copy` — done, `0060890` (shared with
  T3, same file). Uninstall target guarded by a marker and the unit substitution
  escaped for `&`; both covered by R11 and R12.
- T3 — Preflight the environment with actionable messages. S7. worker.
  `feat(packaging): check the environment before installing` — done, `0060890`.
- T4 — `packaging/tests/install-smoke.sh`: install into a temporary HOME, assert
  the prefix layout, the generated unit and `--version`, then uninstall and
  assert nothing of ours remains. S2 S6. worker. — parked by L6.
  `test(packaging): prove a clean install and uninstall`
- T5 — README: install, compatibility matrix and uninstall from the prefix.
  S2 S3 S6. worker. — parked by L6.
  `docs(readme): document the self-contained install`

## Log

L1 — owner, verbatim: "lo que sucede es que el progrma lo quiero llevar a algo
profesionalk verdad que ya ses un progrma usable por gente que haya  o tiene el
miso problem que yo tube"

L2 — owner decisions, verbatim from the questionnaire: license "MIT"; scope
"Bloque 1: hacerlo instalable de verdad".

L3 — context before this feature: the review lifecycle found that the installed
unit pointed at a fixed checkout path (finding R3-001), then that the substituted
path was unquoted for systemd (finding R1-001). Both were fixed, but the install
still executes the repository working copy. T2 removes that coupling instead of
keeping the path correct.

L4 — the owner accepted an incomplete native review of the previous work unit
(no validator signature) and has not authorized publishing: everything stays
local on `feat/phone-mic`.

L5 — delivery shape not yet decided. The branch carries roughly 2,900 authored
lines across 16 commits since `origin/main`, far past a single reviewable slice.
A natural first boundary already exists: `e051fa7`, `56bcd74`, `f6a988a`,
`076a046` and `136195c` touch only `conf/`, `packaging/`, `README.md`, `LICENSE`
and `odd/`, so they can be published as one slice independent of the `site/`
and `design/` work that precedes them.

L6 — owner, verbatim: "claro pero antes de hacer un instaldaor profesional hay que
pulir el progrma"

L6 reorders priority. Polishing the program comes before reaching the
professional installer bar. The installer core already delegated (T2, T3) lands
as the current installation foundation, but T4, T5 and any further install work
wait until the polish scope is agreed and delivered. The polish work gets its own
feature document; it is not silently folded into this one.
