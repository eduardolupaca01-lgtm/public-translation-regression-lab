# R11 — diálogo y dibujo directo, primera aparición

Scope: the existing MV/MZ translator; no game scripts or assets included. Real game observation remains separate from synthetic regression results.

- NEV-style leading AC/AL/AR/ALIGN controls are preserved as native controls. Late message replacement computes each translated line's width and alignment; mid-message alignment changes are intentionally not replayed.
- A pending native Bitmap rectangle is cancelled before an overlapping draw, clear, reuse, scene change, or input form. Cancellation never restores an old snapshot over a new draw.
- For active MZ NEV-style plugins, bounded native Bitmap/Canvas groups record their actual drawing operations and pixels. A late replay is accepted only when the original draw is reconstructed byte for byte on an offscreen bitmap and the live pixels/scene still match. This covers paired stroke/fill, multi-line static labels and simple instructions without a second visible window. Arbitrary Canvas contexts, unrecognized input/puzzle strings, unknown names, unsupported transforms, oversized or modified surfaces are not blindly repainted.
- The first-view regression verifies all Spanish word runs, native alignment, original event text, portrait preservation, and no restarted message. Pixel fixtures test paired fill/stroke and cancellation when the canvas is cleared or repainted.
- The automated runner is a synthetic fixture; OPUS model and Windows packaging must pass the real-IA workflow before delivery. A translated bitmap that cannot be proven safe is left intact, not erased or replaced by an overlay.
