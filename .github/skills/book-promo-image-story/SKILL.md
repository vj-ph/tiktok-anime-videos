---
name: book-promo-image-story
description: Create a concise, image-first TikTok book-promotion story from a hook and book title. Use when planning promotional image sequences for books.
---

# Book Promotion Image Story

Create a short story that turns a reader's anxiety into confidence through the
book's visible, specific benefits. The output is a set of still-image prompts
for a later TikTok edit, not video prompts.

## Inputs

Ask for only what is missing:

- Hook
- Book title
- Three to five verified book features or pages to showcase
- Target audience and narration language
- Book cover and page images, when the product must appear

Do not invent features. Do not claim that the book guarantees an exam result,
job, visa, residence status, naturalisation, or other outcome.

## Story structure

Use five images by default; use no more than six.

1. **Hook:** Show the reader's high-stakes worry.
2. **Anxiety:** Make the specific obstacle visible.
3. **Proof:** Show a supplied book page or spread that solves the obstacle.
4. **Transformation:** Show the reader calmer or a visual metaphor for
   structured practice.
5. **Product and CTA:** Show the supplied cover clearly, with room for an
   editor-added CTA.

Combine related anxieties into one image. Prefer one strong visual idea per
image over explaining every feature.

## Output format

Return:

```markdown
# [Book title] Image Story

## Core message
[One sentence.]

| Image | Story beat | On-screen copy | Narration | Gemini image prompt | Assets to upload |
| --- | --- | --- | --- | --- | --- |
| 1 | ... | ... | ... | ... | ... |
```

- Keep narration to one or two short sentences per image.
- Make on-screen copy short; it is added later in the editor.
- Include a final CTA such as `Amazon-Link im Profil` only when appropriate.

## Gemini image prompt requirements

Every prompt must:

- Begin with `Vertical 9:16, 1080 x 1920, still image.`
- Specify subject, setting, emotion, lighting, visual style, framing, and
  space reserved for overlay text.
- State `No readable text, no logos, no watermarks` unless the user will upload
  an approved book cover or page.
- Keep the same fictional character's approximate age, appearance, clothing,
  and setting across character images.

When the book cover or an interior page should appear, say:

`Use the uploaded [cover/page] exactly as provided. Keep its title, typography,
layout, and visible text accurate and legible. Do not redraw, paraphrase, or
invent book text.`

Also identify the exact asset to upload. Use product images only when supplied
by the user or available locally with permission.

## Quality rules

- Generate still-image prompts only: no camera moves, animation, or duration.
- Use real book pages as product proof, not AI-invented pages.
- Reserve the lower and right TikTok UI-safe areas; place essential product
  imagery near the centre or upper-middle.
- Match the book cover's palette where practical.
- End on preparation and confidence, not a promise of success.
