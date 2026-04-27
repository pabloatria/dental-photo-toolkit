# Dental Photo Toolkit — Custom GPT

Public Custom GPT companion to the `dental-photo-processor` Claude skill.
JPEG/PNG/TIFF only. Free. Branded as "Dr. Pablo Atria."

## Files in this folder

| File | Purpose |
|---|---|
| `pipeline.py` | Single-file Python pipeline. Upload as a knowledge file. |
| `instructions.md` | System prompt. Paste into the GPT's "Instructions" field. |
| `welcome_message.md` | First-message text + suggested conversation starters. |
| `knowledge/aacd_standards.md` | AACD 12-view reference. Upload as a knowledge file. |
| `knowledge/filename_conventions.md` | Filename → view mapping. Upload as a knowledge file. |
| `test_pipeline.py` | Local smoke test (not uploaded; run before publishing). |

## Pre-publish checklist

1. Run the smoke test once and confirm it passes:
   ```bash
   cd dental-photo-toolkit-gpt
   python3 -m pytest test_pipeline.py -v
   ```
2. Skim `instructions.md` for voice / accuracy.
3. Skim `welcome_message.md` for tone.

## Publishing to ChatGPT (10 minutes)

1. Open ChatGPT (Plus account required).
2. Sidebar → **Explore GPTs** → **+ Create**.
3. Switch to **Configure** tab.
4. Fill in:
   - **Name:** `Dental Photo Toolkit by Dr. Pablo Atria`
   - **Description:** "Process clinical dental photography in seconds — white balance, AACD-standard crops, before/after composites, and the 12-photo accreditation board. JPEG only. By Dr. Pablo Atria."
   - **Instructions:** paste the contents of `instructions.md`.
   - **Conversation starters:** paste the four starters from `welcome_message.md`.
   - **Knowledge:** upload `pipeline.py`, `knowledge/aacd_standards.md`, `knowledge/filename_conventions.md`.
   - **Capabilities:** **Code Interpreter & Data Analysis ✅**, Web Search ❌, Image Generation ❌.
   - **Actions:** none.
5. **Profile picture / icon:** upload a minimal mark (placeholder icon OK for v1; design later).
6. **Privacy** for soft launch: **Anyone with the link**. Test with 2–3 real cases yourself + 2–3 colleagues.
7. After feedback round: switch to **GPT Store: Everyone**.

## Soft-launch test cases to try in your published GPT

1. Upload the synthetic test case from the Claude skill (`/tmp/dental_test_case` after running `_make_test_case.py`). Should produce a complete board.
2. Upload only 6 retracted views, no portraits. Should produce a board with 6 placeholders + a clear missing-views note.
3. Upload one matched before/after pair (e.g. `pre_retracted_apart.jpg` + `post_retracted_apart.jpg`). Should produce a 2-up composite, no full board.
4. Upload a CR3. Should refuse cleanly with the JPEG-only message.

## Future updates

To update the GPT after publishing, edit the files in this folder, commit, then in ChatGPT re-upload the changed files into the GPT's knowledge section. The Custom GPT does not auto-sync from your local files — it's a manual re-upload.
