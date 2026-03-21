from __future__ import annotations

import io
import logging
from typing import Any

import httpx
import imagehash
from PIL import Image

from config.settings import settings
from domain.normalized_product import NormalizedProduct

logger = logging.getLogger(__name__)


class ImageClassifierPipeline:
    """
    Downloads images to memory, classifies (CLIP + heuristics), optional rembg in memory.
    Does not persist bytes anywhere. Output: original store URLs only, best first.
    """

    def __init__(self) -> None:
        self.max_ranked = settings.MAX_IMAGES_PER_PRODUCT
        self.rembg_threshold = settings.REMBG_CONFIDENCE_THRESHOLD
        self._clip_model = None
        self._clip_preprocess = None
        self._clip_tokenizer = None
        self._device = None

    @classmethod
    def from_crawler(cls, crawler: Any) -> ImageClassifierPipeline:
        return cls()

    def open_spider(self, spider: Any) -> None:
        try:
            import torch
            import open_clip

            self._device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
            model, _, preprocess = open_clip.create_model_and_transforms("ViT-B-32", pretrained="openai")
            self._clip_model = model.to(self._device)
            self._clip_preprocess = preprocess
            self._clip_tokenizer = open_clip.get_tokenizer("ViT-B-32")
            self._clip_model.eval()
        except Exception:
            logger.warning("[IMAGE_PIPELINE] open_clip unavailable; heuristic scoring only")

    def _user_agent(self, spider: Any) -> str:
        ua = "uz-tech-scraper/1.0"
        cr = getattr(spider, "crawler", None)
        if cr is not None:
            ua = cr.settings.get("USER_AGENT") or ua
        return ua

    def _download(self, client: httpx.Client, url: str, ua: str) -> bytes | None:
        try:
            resp = client.get(url, headers={"User-Agent": ua}, timeout=10.0)
            if resp.status_code == 200:
                return resp.content
        except Exception as exc:
            logger.warning("[IMAGE_SKIP] download %s: %s", url, exc)
        return None

    def _aspect_penalty(self, pil: Image.Image) -> float:
        w, h = pil.size
        if h <= 0:
            return 0.0
        r = w / h
        if r > 2.8 or r < 0.35:
            return -0.4
        return 0.0

    def _clip_score(self, pil_rgb: Image.Image) -> float:
        if self._clip_model is None or self._clip_preprocess is None or self._clip_tokenizer is None:
            return 0.5
        try:
            import torch

            image_input = self._clip_preprocess(pil_rgb).unsqueeze(0).to(self._device)
            text_tokens = self._clip_tokenizer(
                ["clean product photo on white background", "website advertising banner collage"]
            ).to(self._device)
            with torch.no_grad():
                image_features = self._clip_model.encode_image(image_input)
                text_features = self._clip_model.encode_text(text_tokens)
                image_features = image_features / image_features.norm(dim=-1, keepdim=True)
                text_features = text_features / text_features.norm(dim=-1, keepdim=True)
                sim = (image_features @ text_features.T).squeeze(0)
            return float(sim[0] - sim[1])
        except Exception:
            logger.debug("[IMAGE_PIPELINE] CLIP score failed", exc_info=True)
            return 0.5

    def _score_image(self, pil_rgb: Image.Image) -> float:
        return self._clip_score(pil_rgb) + self._aspect_penalty(pil_rgb)

    def _maybe_rembg_bytes(self, image_bytes: bytes) -> bytes:
        try:
            from rembg import remove

            return remove(image_bytes)
        except Exception:
            logger.debug("[IMAGE_PIPELINE] rembg failed", exc_info=True)
            return image_bytes

    def process_item(self, item: dict[str, Any], spider: Any) -> dict[str, Any]:
        if "discovered_url" in item:
            return item
        raw_urls = item.get("image_urls") or []
        if not raw_urls:
            return item

        ua = self._user_agent(spider)
        scored: list[tuple[str, float]] = []
        seen_hashes: set[str] = set()

        with httpx.Client(follow_redirects=True) as client:
            for url in raw_urls[:10]:
                try:
                    image_bytes = self._download(client, url, ua)
                    if not image_bytes:
                        continue
                    pil = Image.open(io.BytesIO(image_bytes)).convert("RGB")
                    ph = str(imagehash.phash(pil))
                    if ph in seen_hashes:
                        continue
                    seen_hashes.add(ph)

                    base_score = self._score_image(pil)
                    final_score = base_score
                    if base_score < self.rembg_threshold:
                        cleaned = self._maybe_rembg_bytes(image_bytes)
                        if cleaned != image_bytes:
                            try:
                                pil2 = Image.open(io.BytesIO(cleaned)).convert("RGB")
                                final_score = max(base_score, self._score_image(pil2))
                            except Exception:
                                pass

                    scored.append((url, final_score))
                except Exception as exc:
                    logger.warning("[IMAGE_SKIP] %s: %s", url, exc)

        scored.sort(key=lambda x: x[1], reverse=True)
        ranked = [u for u, _ in scored[: self.max_ranked]]

        item["image_urls_ranked"] = ranked
        item["image_urls"] = ranked

        norm = item.get("_normalized")
        if isinstance(norm, NormalizedProduct):
            item["_normalized"] = norm.model_copy(update={"images": ranked})

        return item


# Scrapy settings reference
ImagePipeline = ImageClassifierPipeline
