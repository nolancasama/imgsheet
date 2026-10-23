# ChatGPT Image Sheet Playbook

Version: 1.0 · Updated: 2026-10-23

## What this file is

This document is the **reference specification for ChatGPT** to create downloadable, print-ready character image sheets from typed lists or handwritten Japanese photos. It is deliberately **separate from the existing Image Sheet Generator app** in this GitHub repository. It does not require running, modifying, or deploying that app.

**For a new ChatGPT conversation**, paste:

> Read https://github.com/nolancasama/imgsheet/blob/master/CHATGPT_IMAGE_SHEET_PLAYBOOK.md and follow its current instructions to create an image sheet from my attached photo or character list.

Attach the photo or provide the list. To add the optional humorous backs, explicitly say **"Include Matsubara joke backs."** Without that instruction, generate images only.

**Important:** ChatGPT does not automatically read a GitHub reference across every fresh conversation. The user must provide the link or otherwise direct ChatGPT to it. The current conversation's explicit instructions supersede this file.

## 1. Inputs and interpretation

Accept:
- Photographs/scans of handwritten Japanese names by elementary school children.
- Typed lists of Japanese or English names, anime/game characters, groups, celebrities, and similar subjects.
- Optional overrides of page dimensions, layout, number of images, printing, and whether to email.

For handwritten input:
1. Examine the *actual image*, not only OCR. Preserve reading order and recognize crossed-out or parenthetical notes.
2. Transcribe requested items and infer the child's **most likely intended subject** in Japanese. Account for childish writing, kana/kanji ambiguity, missing dakuten or small kana, spelling mistakes, phonetic approximations, English letters, and nicknames.
3. Prioritize age-appropriate recognition and Japanese elementary-school cultural context, but do not assume an ambiguous scribble must be a famous name.
4. When necessary, search Japanese and English spellings and verify the series/character's identity with external information.
5. Classify confidence as **High / Medium / Low**. These are qualitative judgments, not statistical probabilities.
6. Proceed with clearly recognizable items. For a materially ambiguous word, provide possible interpretations, flag it for review, and avoid confidently including an unrelated image. Ask a concise question only when ambiguity materially blocks the result; otherwise make the best possible document and report exclusions.
7. Do not identify or repeat unnecessary private student information.

Count **distinct requested subjects**, not duplicate mentions, unless the user explicitly asks otherwise.

## 2. Image search and selection priorities

Search for **existing online images**, not AI-generated illustrations, unless the user requests generation.

Choose images in this ranked order:
1. **Popular/recognizable:** Familiar portrayals Japanese elementary-school children would immediately recognize.
2. **Iconic:** Signature outfits, poses, moments, powers, or expressions.
3. **Artistic:** Attractive, high-quality, well-composed images.
4. **Funny:** Silly faces, amusing poses, lighthearted child-friendly memes.

Apply all these technical checks:
- It must be the **correct character or subject**, not a similarly named one.
- Prefer high-resolution and sharp images with recognizable subjects and minimal distracting backgrounds.
- Avoid large watermarks, picture collages, prominent text, blurry photos, low-quality screenshots, and heavily obstructed subjects.
- Prefer varied images, not five identical crops or near-duplicates.
- Where possible, choose official or representative artwork.
- Be mindful of source copyright/reuse rights; search availability is not a license. Do not claim that images are free for unrestricted use.
- If a download URL fails, choose another usable verified image rather than leave empty cards or silently substitute the wrong character.

For example, five Goku images may be classic Goku, Super Saiyan, Kamehameha, an artistic illustration, and a funny expression.

## 3. Default quantity, allocation, and page count

Default: **JIS B4 portrait sheet, 5 columns by 5 rows, 25 identically sized cells per image page**.

Distribute the 25 images **as evenly as possible** among subjects, selecting different images for repeat subjects.

Examples:
- 5 subjects: 5 different images of each.
- 10 subjects: a mix of 2 and 3 images per subject; exactly 25 pictures.
- 15 subjects: a mix of 1 and 2 images per subject; exactly 25 pictures.
- 25 subjects: 1 each.
- 26–50 subjects: 2 separate 25-cell image pages, ensuring every subject appears.
- 51–75 subjects: 3 image pages.
- In general: at least \`ceil(subject_count / 25)\` image pages.

**Balance subjects across pages.** Do not make one page full and another almost exclusively one remaining subject; spread allocations sensibly and retain input grouping where useful.

The user may override any allocation or request a smaller total grid.

## 4. Paper, margins, cut lines, and cell geometry

Paper: **JIS B4 portrait 257 × 364 mm** by default.
Grid: **5 × 5 with 25 perfectly aligned, equally sized physical cutouts**.

### IMPORTANT: later preference overrides the old nominal card size

Earlier image sheets used approximately **45 × 65 mm** portraits, but the user has now prioritized **near-zero outer margins and fewer cuts**. These goals conflict: 5 × 45 = 225 mm, leaving 32 mm of unused B4 width; 5 × 65 = 325 mm, leaving 39 mm of unused height. Therefore:

- **New default:** expand the 5 × 5 grid to fill **nearly the entire printable B4 sheet**, making every physical cutout identical and all vertical/horizontal boundaries continuous.
- At true zero margins this would give approximately **51.4 × 72.8 mm** per cell. If a printer requires 2–3 mm safe margins, calculate cell width and height from the remaining printable area.
- Use the paper's outer edges as cutting boundaries whenever possible.
- If the user explicitly requests exactly **45 × 65 mm cutouts**, honor that physical dimension, explaining that white space at the outer edges is unavoidable.
- Report the actual chosen **cell dimensions** in the completed response. Do not falsely call expanded cells 45 × 65 mm.

**Cutting lines:** Dark enough to see while cutting in poor light, e.g. dark gray \`#555555\` or black, fine continuous single rules around **0.5–0.75 pt**. No double borders, cell gaps, wasted padding, or misaligned row segments. Visual priority is speed and straight, easy cuts.

For printers without borderless B4 support, use the smallest reliable printer-safe margins, and tell the user the printer may have nonprintable edges. Avoid auto-scaling when printing: choose **Actual size / 100%** to preserve dimensions.

## 5. Portrait and landscape image content in the *same* fixed grid

All **physical cells remain the same portrait rectangle**; cut boundaries never become staggered or irregular.

For each source image:
- Judge whether its composition is portrait or landscape.
- **Fit landscape-composition artwork horizontally inside its portrait cell** instead of distorting it into a portrait image.
- Do not rotate characters sideways merely to fill space.
- Preserve subject shape and recognition; use proportional scaling and **white padding** if necessary.
- Crop only where safe and where no important face, body, text, or other meaningful detail will be removed.
- Prefer an alternate image that uses the cell more effectively over a tiny subject surrounded by excess whitespace.
- Maintain equal cell dimensions, irrespective of the contained image's composition.

## 6. Optional Matsubara / character jokes on the reverse — OFF by default

**Only add back pages when the user explicitly requests "watermarks," "Matsubara joke backs," or an equivalent.** A normal sheet has NO backs and NO extra pages.

When on:
- Add one back page **immediately after each front page** in the Word file: page 1 pictures, page 2 jokes; page 3 pictures, page 4 jokes; etc.
- Every reverse cell contains a **different, original, short, funny Japanese sentence**, not the same watermark copied 25 times.
- Mix humor about **Matsubara City (松原市), Osaka**, Kansai dialect, the *actual subject printed on that card*, and playful character–Matsubara crossovers.
- Prefer subject-specific jokes when possible, not generic city slogans for every card.
- Keep jokes appropriate for Japanese elementary school students. Absurd exaggerations are fine when clearly jokes; do not invent serious factual claims or mock children.
- Examples:
  - Goku: 松原市の戦闘力、測定不能！
  - Luffy: 松原市で海賊王になる！海ないけど。
  - Pikachu: 松原市、電気代ゼロ計画！
  - My Melody: 松原市のかわいさ担当です♡
  - General: 大阪の中心は松原や！知らんけど。
- Printed backs must be **almost invisible at first glance**: text in pale gray around \`#D9D9D9\`, ordinary/thin font, NOT bold. Keep ink coverage minimal to help limit show-through onto the picture side; paper thickness/printing affects real show-through.
- Center the light-gray text in its matching reverse cell, never on the front image.
- **Ensure double-sided alignment**, including mirroring/reversing the back grid's column order when needed for portrait duplex printing. Confirm which duplex edge to flip; don't assume that one mirroring convention works with every printer. Check with a small test page if in doubt.
- Each back page uses exactly the same paper geometry and grid as its corresponding front. A 2-page image-only job becomes 4 physical pages with joke backs.

## 7. Word document creation, checking, and delivery

Primary output: **downloadable Microsoft Word \`.docx\`** suitable for printing, not only a rendered preview.

- Keep JIS B4 portrait page settings and correctly sized grid.
- A single high-resolution full-page printable composition embedded in the Word document is fine if that is more robust than independent table cells. Editable individual images are optional, not required.
- Use image sizing/resampling suitable for printing and avoid unnecessary compression.
- Prevent page reflow, trailing blank pages, unexpectedly split rows, clipped images, unequal cutouts, and cut guides that don't line up.
- Ideally render/proof each page and inspect paper size, image content, margins, cut lines, and page count before delivery.
- Return a **verified working file download link**.
- Briefly state: number of subjects, number of images, number of image pages, whether reverse joke pages are included, physical cell dimensions, and any uncertain/omitted names.
- A PDF companion may be provided if useful but **.docx is the required default**.
- **Do not email** unless requested. If the user asks to email, attach the actual completed document through the connected Gmail app, if available, and verify sending.
- Do not change or deploy the existing GitHub program when creating sheets. Editing this playbook itself requires an explicit instruction.

## 8. Final quality checklist

- [ ] Every clearly requested subject is included, or omissions are disclosed.
- [ ] Image selection favors recognition → iconic quality → artistry → humor.
- [ ] Duplicate-image repetition is minimized.
- [ ] B4 portrait, precisely aligned 5 × 5 grid, same cutout size.
- [ ] Outer margins minimal and dark cut lines visible.
- [ ] Wide/landscape artwork is fitted horizontally **inside** unchanged portrait cells.
- [ ] Subject not unnaturally stretched, rotated, or cropped.
- [ ] Correct front–back joke correspondence if optional backs are explicitly requested.
- [ ] Back text light gray, unique, kid-friendly and relevant; backs absent otherwise.
- [ ] Word file really exists and print layout/page count is checked.
- [ ] A working downloadable link and concise interpretation summary are given.
- [ ] Email only if the user requests it.

## Maintenance note

Treat this as the **living source-of-truth reference for ChatGPT**. If new user preferences are agreed later, update this Markdown file when asked. Changes to it do **not** automatically change the separate browser/desktop app, and neither app deployment nor automatic instruction loading in new conversations is implied.
