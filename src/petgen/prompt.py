from __future__ import annotations


def build_pet_prompt(description: str) -> str:
    """Build the image prompt for a 3-row desktop-pet action source sheet."""
    cleaned = description.strip()
    if not cleaned:
        raise ValueError("description must not be empty")

    return f"""
Create a premium 2D cartoon desktop-pet action source sheet.

Pet concept from the user:
{cleaned}

If reference images are provided, preserve the subject's recognizable colors,
silhouette, markings, accessories, material cues, and personality, while
redesigning it as one original cute companion pet.

Style:
- Polished modern 2D mascot with a plush, dimensional "vinyl toy / 3D sticker" feel.
- Soft rounded shapes, expressive face, clean silhouette, crisp edges.
- Subtle hand-painted shading, high-quality app icon / sticker finish.
- Not pixel art. Not realistic photo.

Premium finish (important for texture quality):
- Soft matte fur / plush texture with visible fluffy volume, not flat color fills.
- Gentle volumetric lighting with a soft rim light and ambient occlusion for depth.
- Rich, harmonious, slightly warm color palette with smooth gradients.
- Thick clean outer outline, glossy highlight in the eyes, rosy cheek blush.
- Cozy, high-end collectible-toy aesthetic; every frame equally polished.

Canvas and background:
- One single image, landscape or square.
- Solid chroma-key green background exactly #00FF00 across all empty areas.
- No shadows touching the frame edge.
- No scenery, text, logo, watermark, grid lines, or borders.

Layout, strict:
- 3 horizontal action rows with clear empty green gaps.
- Top row: 6 idle frames, calm breathing / blink variations.
- Middle row: 4 attentive hover frames, curious lean / listening variations.
- Bottom row: 5 happy click frames, delighted / celebratory variations.
- Every frame shows the SAME pet, full body, centered.
- Leave generous padding around head, ears, tail, wings, limbs, props, and feet.
- Do not crop any body part. Do not let characters overlap.
- Keep the pet's outside colors away from #00FF00.

Make the pet adorable, rounded, memorable, and suitable as a small desktop companion.
""".strip()
