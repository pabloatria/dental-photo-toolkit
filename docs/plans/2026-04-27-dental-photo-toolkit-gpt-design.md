# Dental Photo Toolkit — Custom GPT Design

**Date**: 2026-04-27
**Author**: Pablo Atria (with Claude)
**Status**: Approved, ready for implementation
**Companion artifact**: `dental-photo-processor/` (Claude skill, already built and tested)

## Context

The Claude skill `dental-photo-processor` is built and verified end-to-end — it takes a folder of clinical dental photos and produces white-balanced versions, AACD-standard crops, before/after composites, polarization comparisons, and the 12-photo AACD accreditation board. It runs locally with zero ongoing cost.

The next deliverable is a **Custom GPT** in the OpenAI GPT Store that exposes the same pipeline to a wider audience, free of charge to the user, branded under Pablo Atria's personal name.

A web app version was considered and **deferred** — we revisited it during this brainstorming and chose not to implement it now. The Claude skill stays as Pablo's personal tool; the Custom GPT becomes the public-facing version. The web app remains an option for the future if traffic justifies it.

## Goals

1. Free, public dental photography post-processing tool, accessible from anywhere via ChatGPT.
2. Branded under "Dr. Pablo Atria" — a small, credibility-building product, not a marketing campaign.
3. Zero ongoing cost to Pablo. No backend, no domains, no hosting bills.
4. Output parity with the Claude skill where the platform allows (JPEG path).
5. Predictable user experience with clear guidelines so the user knows what to upload and what they'll get.

## Non-goals

- RAW (CR3, NEF, ARW, DNG) processing. The Code Interpreter sandbox cannot install `rawpy`. Users with RAW workflows will export JPEG first.
- User accounts, history, persistent storage. Each session is ephemeral by design.
- Charging users. Monetization, if any, comes later via sponsorships or affiliate links — never paywalls on this tool.
- A web app, marketing site, custom domain. Parked for now.
- Multi-language UI translation in v1. Welcome message and outputs in English. Spanish-speaking dentists are comfortable with English clinical terms; we can add Spanish in v2 if traction warrants.

## Constraints inherited from the Custom GPT platform

| Constraint | Implication |
|---|---|
| Custom GPTs require ChatGPT Plus to use | Audience is paying ChatGPT users. Acceptable — dental professionals overlap heavily. |
| Code Interpreter cannot install `rawpy` | JPEG/PNG/TIFF only. Stated upfront in welcome. |
| Code Interpreter session ~30 min | Pipeline runs in <60 sec for 12 photos; non-issue. |
| Upload limit ~512 MB total, ~10 files per turn | Cap user at 36 files, < 500 MB total, allow ZIP for bulk. |
| GPT Store revenue share is US-only and small | Distribution is the value, not direct revenue. |
| No external Actions in v1 | Keeps it free for Pablo and self-contained. Future v2 could add Actions for richer features. |

## User flow

Drop-and-go (locked at the brainstorming stage):

1. User opens the GPT — the welcome message appears with explicit guidelines (format, count, naming).
2. User drags JPEG files or a ZIP into the chat.
3. GPT runs the pipeline silently in Code Interpreter (~30–60 sec for a 12-photo case).
4. GPT replies with:
   - The AACD board rendered inline as an image
   - A downloadable ZIP of all outputs (WB-corrected, crops, before/after, board)
   - A one-paragraph report — what was detected, what was missing, what was flagged for manual review
5. User can ask follow-ups in plain language: *"rerun without the watermark," "give me just the before/after for the right lateral retracted," "label the composite."*

## User guidelines (shown in welcome message and reinforced in system prompt)

| Rule | Value |
|---|---|
| Format | JPEG, PNG, TIFF only. RAW → export to JPEG first. |
| Per-file size | < 20 MB |
| Total upload | < 500 MB, max 36 files per session |
| Naming convention | `pre_retracted_apart.jpg`, `post_face_smile.jpg`, etc. Full list shown in welcome. Unrecognized files trigger a clarification prompt. |
| Minimum for AACD board | 8 of the 12 standard views. Missing slots render as labeled placeholders. |
| Minimum for before/after | At least one matching pre/post pair, identical view name. |

## Branding

| Element | Value |
|---|---|
| GPT name | **Dental Photo Toolkit by Dr. Pablo Atria** |
| Description | "Process clinical dental photography in seconds — white balance, AACD-standard crops, before/after composites, and the 12-photo accreditation board. JPEG only. By Dr. Pablo Atria." |
| Icon | Minimal mark — likely a stylized tooth + grid motif. Final design TBD. |
| Watermark on output board | None. Output is the user's clean clinical photography — they own it without anyone else's mark. (Earlier draft had a small footer; removed before launch on Pablo's call: dentists should be free to use these in their own publications, presentations, and patient records.) |
| Tone | Clinical, precise, English. No emoji, no marketing language. Matches Pablo's voice (scientific precision + aesthetic restraint). |

## Architecture

```
┌──────────────────────────────────────────────────────────┐
│  Custom GPT (hosted by OpenAI, distributed via GPT Store) │
│  ┌────────────────────────────────────────────────────┐  │
│  │  System instructions  (drives behavior)            │  │
│  │  Welcome message      (sets guidelines)            │  │
│  │  Knowledge files:                                  │  │
│  │   - pipeline.py       (single-file Python engine)  │  │
│  │   - aacd_standards.md (the 12 views, framing)      │  │
│  │   - filename_conventions.md                        │  │
│  └────────────────────────────────────────────────────┘  │
│  Tools: Code Interpreter ✓   Browsing ✗   DALL-E ✗      │
└──────────────────────────────────────────────────────────┘
                            │
                            ▼
                  ┌──────────────────┐
                  │  Code Interpreter │
                  │  Python sandbox   │
                  │  numpy, opencv,   │
                  │  Pillow available │
                  └──────────────────┘
```

The GPT's job: read the user's uploaded files, write them to the sandbox, exec `pipeline.py` against them, surface the outputs back to the user. The pipeline does the heavy lifting. The LLM's role is interpretation and presentation, not image processing.

## File structure to build

```
dental-photo-toolkit-gpt/
├── instructions.md          # GPT system prompt
├── welcome_message.md       # first-message guidelines
├── pipeline.py              # single-file pipeline (rawpy stripped, all scripts merged)
├── knowledge/
│   ├── aacd_standards.md    # adapted from the Claude skill's reference
│   └── filename_conventions.md
└── README.md                # publishing checklist for the GPT Store
```

`pipeline.py` will be produced by merging `classify.py` + `white_balance.py` + `crop_aacd.py` + `composite.py` + `process_photos.py` from the Claude skill, dropping RAW handling, and adapting paths to read from Code Interpreter's working directory and write outputs to a download-friendly ZIP.

## Pipeline adaptations vs. the Claude skill

| Concern | Claude skill | GPT version |
|---|---|---|
| Input format | RAW + JPEG | JPEG/PNG/TIFF only |
| File reading | filesystem walk | uploaded files in `/mnt/data/` (Code Interpreter convention) |
| Output | written to `_processed/` subfolder | written to a temp dir, then zipped, returned as a single download |
| Scripts | multi-file, importable | single `pipeline.py` for easy upload |
| Polarization detection | enabled | enabled (filename-based; works without RAW) |
| WB tier 1 (cross-pol) | EXIF-driven + case median | filename-driven + case median (EXIF less reliable in JPEG) |
| Watermark | none | small footer on AACD board, toggleable |

## Cost summary

| Item | Cost |
|---|---|
| Build | One session of focused work (~30 min on the engineering side, ~10 min on the publish side) |
| Ongoing hosting | **$0/month forever** — OpenAI hosts the GPT |
| Pablo's ChatGPT Plus | Already paid, unrelated |
| Per-user cost | $0 to Pablo. End user already pays OpenAI for ChatGPT Plus. |

## Distribution

1. Build the files (this plan).
2. Pablo creates the GPT in ChatGPT — paste `instructions.md`, upload `pipeline.py` and `knowledge/` files, set name + description + icon, choose privacy: **Anyone with the link** initially, then **GPT Store: Everyone** once tested with 2–3 real cases.
3. Soft launch: share the link with 5–10 dentist colleagues, NYU residents, Camila. Collect a week of feedback.
4. Polish based on feedback (likely: watermark size, board layout tweaks, naming conventions).
5. Submit to GPT Store, public listing.
6. Optional: a single LinkedIn post or NYU faculty newsletter mention. No paid promotion, no AS Odontología branding.

## Future (parked, not in v1)

- RAW support via a paid backend Action (only if traffic justifies hosting cost)
- Spanish localization
- Patient-facing share links (case viewer URL)
- Sponsorship integration (Phrozen, Exocad, Ivoclar) once traffic is meaningful
- Affiliate "Recommended gear" page
- Web app version (revisit when there's a reason)

## Open items to resolve during implementation

- Final icon design (placeholder OK for v1 launch)
- Welcome message wording — needs Pablo's voice review before publish
- Whether to bundle a tiny "What is the AACD board?" explainer in the welcome for non-AACD-aware users (probably yes, single sentence)

## Approval

Approved by Pablo on 2026-04-27 with one revision:
- Drop "NYU College of Dentistry" from public description. Branding is just "Dr. Pablo Atria."
