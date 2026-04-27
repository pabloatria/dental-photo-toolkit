# Dental Photo Toolkit

Post-processing for clinical dental photography — white balance, AACD-standard crops, before/after composites, and the 12-photo accreditation board, in a few seconds.

By Dr. Pablo Atria.

---

## Two ways to use it

Pick the one that matches the tool you already work in.

### ChatGPT — recommended for most users

A Custom GPT that processes your photos inside ChatGPT. Drop a folder (or a ZIP), get a clean AACD board and a downloadable archive of every output. JPEG, PNG, or TIFF only.

**[Open the GPT in ChatGPT →](https://chatgpt.com/g/g-69ef6afd5c948191941a7b370eef0032-dental-photo-toolkit-by-dr-pablo-atria)**

Requirements: ChatGPT Plus account (Custom GPTs require Plus).

### Claude Code — recommended if you shoot RAW or want full local control

A Claude skill that runs the full pipeline locally on your machine, with native RAW (CR3, NEF, ARW, DNG) support, no upload limits, and your photos never leave your computer.

```bash
# Clone the repo
git clone https://github.com/pabloatria/dental-photo-toolkit.git

# Install the skill
cp -r dental-photo-toolkit/dental-photo-processor ~/.claude/skills/

# Install Python dependencies
pip install -r dental-photo-toolkit/dental-photo-processor/requirements.txt
```

Then in Claude Code, ask Claude to process a case folder:

> "Process this dental case: /path/to/PatientID_2026-04-26"

Claude will pick up the skill automatically. See `dental-photo-processor/SKILL.md` for full details.

---

## What it does

For a folder of clinical photos, the toolkit produces:

| Output | Description |
|---|---|
| **White balance correction** | Three-tier algorithm: cross-polarized shots trusted as-shot, intraoral shots use enamel highlights as an internal neutral reference, portraits use skin-tone-protected gray-world. No color card required. |
| **AACD-standard crops** | Each image cropped to the aspect ratio for its view (4:5 portrait, 3:2 landscape, 4:3 occlusal). Occlusal mirror shots flipped per clinical convention. |
| **Before/after composites** | 2-up horizontal pairs with identical cell sizes — forced consistency for honest visual comparison. |
| **AACD 12-photo accreditation board** | The full submission-ready board, 4 × 3 grid, 300 dpi, 11" × 8.5" landscape. Missing views render as labeled placeholders. |
| **Polarization comparisons** | When non-pol and cross-pol shots of the same view are uploaded, side-by-side comparisons for shade matching. (Claude version only.) |
| **Manifest + report** | CSV listing every image's classification, a one-paragraph case report. |

The pipeline is non-destructive: originals are never modified.

---

## Filename conventions for auto-classification

The toolkit reads filenames to classify each photo by timepoint, view, and polarization. Naming files this way means zero manual mapping:

```
pre_face_smile.jpg
pre_retracted_apart.jpg
pre_retracted_apart_pol.jpg
pre_occlusal_max.jpg
post_face_smile.jpg
post_retracted_apart.jpg
...
```

Full keyword list: see `dental-photo-processor/references/filename_conventions.md`.

If your files are not named this way, the Claude skill writes a manifest CSV and asks you to fill it in once. The ChatGPT version asks you in chat.

---

## Privacy

Your patient photos are real clinical data. Handle them accordingly.

- **ChatGPT version:** uploads transit OpenAI's standard infrastructure. This is **not HIPAA-compliant out of the box**. OpenAI offers HIPAA via Enterprise BAA only — consumer ChatGPT does not. Do not upload identifiable patient photos without consent. Faces are visible in views 1–3 (full face, profile). Crop or de-identify as needed before uploading.
- **Claude Code version:** processing happens entirely on your local machine. Photos do not leave your computer.
- **All versions:** follow your jurisdiction's PHI rules — HIPAA in the US, Ley 19.628 in Chile, GDPR in the EU, and equivalents elsewhere. Obtain patient consent before sharing case photos.

This tool performs photographic post-processing only. It does not provide clinical advice, diagnosis, or treatment recommendations.

---

## About

Built by [Dr. Pablo J. Atria](https://github.com/pabloatria) (DDS, MS, PhD) — Director of the Operative and Digital Dentistry Advanced Clinical Fellowship at NYU College of Dentistry, and co-director of Clínica AS Odontología (Santiago, Chile).

This toolkit exists because clinical photography sits between art and evidence: it has to be aesthetically clean (presentation, social, publication) AND metrologically honest (shade decisions, longitudinal comparison). The most expensive mistake is publishing a case where white balance drifted between visits — the "after" looks better only because the camera saw it differently. This toolkit enforces consistency without flattening the image.

The output is yours. There is no watermark. Use the processed photos in your own publications, accreditation submissions, courses, and patient communication freely.

---

## Repository structure

```
dental-photo-toolkit/
├── README.md                         # this file
├── LICENSE                           # MIT
├── dental-photo-processor/           # Claude Code skill
│   ├── SKILL.md
│   ├── scripts/
│   ├── references/
│   └── requirements.txt
├── dental-photo-toolkit-gpt/         # ChatGPT Custom GPT artifacts
│   ├── pipeline.py                   # single-file JPEG pipeline
│   ├── instructions.md               # GPT system prompt
│   ├── welcome_message.md            # GPT welcome / starters
│   ├── knowledge/                    # AACD reference files
│   ├── PUBLISHING.md                 # how to publish to the GPT Store
│   └── test_pipeline.py
└── docs/plans/                       # design + implementation history
```

---

## License

MIT — see [LICENSE](LICENSE).

Contributions, bug reports, and feature requests welcome via GitHub issues.
