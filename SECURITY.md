# Security

This document records the security audit performed on the Dental Photo Toolkit before its public ChatGPT GPT launch, and the policy for reporting future vulnerabilities.

## Audit — 2026-04-27

A security review was performed against both deployment paths:

- The **Claude Code skill** (`dental-photo-processor/`), which runs locally on the user's own machine.
- The **ChatGPT Custom GPT** (`dental-photo-toolkit-gpt/`), which runs inside ChatGPT's Code Interpreter sandbox and is reachable by anyone on the public internet who has a ChatGPT Plus account.

### Method

| Tool / step | Outcome |
|---|---|
| `bandit -r .` | 16 findings, all Low severity (test-only subprocess use, `try/except/continue` for resilient median computation, pytest assertions). No High or Medium issues. |
| `pip-audit -r dental-photo-processor/requirements.txt` | 2 CVEs against Pillow ≤ 11.3.0 (PSD out-of-bounds, FITS bomb). Mitigated by bumping floor to 12.2.0. |
| Manual review for zip slip | Real finding — fixed (see below). |
| Manual review for path traversal in output filenames | Not exploitable. `Path.stem` strips parent components. |
| Manual review for image / decompression bombs | Real finding — fixed (see below). |
| Manual review for shell-execution patterns and arbitrary-code primitives | Zero hits in production code paths. Only test scaffolding uses subprocess, with a hardcoded argv list. |

### Findings and fixes

**HIGH — Zip slip in the GPT path.** The Custom GPT's instructions told the LLM to unzip user-uploaded archives into `/mnt/data/case/`. The LLM would have used a naive ZIP extraction, which is the textbook zip-slip primitive: a maliciously crafted ZIP containing entries with `../` paths could overwrite `/mnt/data/pipeline.py` itself, leading to attacker-controlled code execution within the same Code Interpreter session.

*Fix:* Added `pipeline.safe_unzip()` which validates each archive entry against absolute paths, drive letters, and `..` components, and rejects any path that resolves outside the destination. Updated `instructions.md` to forbid naive extraction and require `safe_unzip`. Regression tested in `test_pipeline.py` (`test_safe_unzip_rejects_traversal`, `test_safe_unzip_rejects_absolute`, `test_safe_unzip_extracts_clean_archive`).

**MEDIUM — Decompression-bomb DoS.** `cv2.imread` accepts any header dimensions and allocates `H × W × 3` bytes immediately. A small JPEG/PNG claiming 65,535 × 65,535 dimensions would have demanded ~12 GB of RAM, OOM-killing the Code Interpreter session for any visitor able to upload a crafted file.

*Fix:* Added an 80-megapixel cap (covers any clinical DSLR/mirrorless sensor with headroom). The pipeline now probes header dimensions via Pillow before invoking `cv2.imread`; over-cap images raise a clear `RuntimeError`. Pillow's `MAX_IMAGE_PIXELS` is also set as a defense-in-depth fallback. Pillow's auto-format dispatch is constrained to `("JPEG", "PNG", "TIFF")` to block the PSD/FITS code paths that historically have had bomb CVEs. Applied symmetrically to both the GPT pipeline (`pipeline.py`) and the Claude skill (`scripts/white_balance.py`). Regression tested in `test_pipeline.py` (`test_image_bomb_dimensions_rejected`, `test_pillow_extreme_bomb_rejected`).

**LOW → MEDIUM — Outdated Pillow.** `requirements.txt` allowed Pillow versions vulnerable to GHSA-cfh3-3jmp-rvhc (PSD out-of-bounds write) and GHSA-whj4-6x5x-4v2j (FITS decompression bomb). These were not reachable through the documented happy path (only JPEG/PNG/TIFF are accepted), but the format restriction added in the bomb fix above is a hardening measure rather than a guarantee.

*Fix:* Bumped `Pillow>=12.2.0` in `dental-photo-processor/requirements.txt`. The GPT side has no `requirements.txt` (Code Interpreter ships its own pinned environment); mitigated there by the format restriction in `Image.open(..., formats=(...))`.

### Audit verdict

The toolkit is safe to publish as a public Custom GPT after the three fixes above. The local Claude skill was already low-risk because its only attack surface is the user processing their own files. All fixes ship with regression tests so they cannot silently revert.

## Reporting a vulnerability

If you find a security issue in this toolkit, please open a GitHub issue at https://github.com/pabloatria/dental-photo-toolkit/issues and tag it `security`, or contact Dr. Pablo Atria directly at `atria.pablo@gmail.com`. Please do not include patient photos or PHI in vulnerability reports.

## Out of scope

- ChatGPT / Code Interpreter sandbox escape (OpenAI's responsibility).
- HIPAA / patient-data privacy at the operational level — covered in the README's *Privacy* section. The user is responsible for jurisdictional compliance.
- Prompt injection of the LLM itself, beyond what the system instructions can defend against.

## License

This security policy is part of the project and is licensed under the same terms — see [LICENSE](LICENSE).
