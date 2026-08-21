"""Cover thumbnail and publish-guide packaging stages."""

import io
import json
import subprocess
from pathlib import Path
from typing import Optional

from src.core.models import ContentPackage, Script
from src.pipeline.agent_io import (
    file_sha256,
    is_artifact_fresh,
    write_artifact_manifest,
)
from src.pipeline.paths import (
    publish_path,
    render_path,
    render_remotion_dir,
    render_root,
)
from src.pipeline.publish_guide_inputs import publish_guide_manifest_inputs
from src.providers.renderer.binary_finder import find_npx
from src.utils.atomic_io import atomic_write_json, atomic_write_text

COVER_VARIANT_COUNT = 3


class PackagingStageMixin:
    """Build cover stills and the human-facing publishing guide."""

    def _step_cover_thumbnail(
        self, content: ContentPackage, script: Optional[Script], date: str
    ) -> None:
        self.logger.info("Step: Cover thumbnail — render 3 bg × 3 text grid (9 stills)")
        if self.dry_run:
            self.logger.info("Dry run: skipping cover thumbnail render")
            return

        render_dir = render_root(date)

        # Collect up to 3 background candidates: cover_bg.png (v1),
        # cover_bg_v2.png, cover_bg_v3.png.
        bg_candidates = sorted(
            p for p in render_dir.glob("cover_bg*.png") if p.name.startswith("cover_bg")
        )
        # Dedup and cap at 3.
        seen = set()
        unique_bgs = []
        for p in bg_candidates:
            if p.name not in seen:
                seen.add(p.name)
                unique_bgs.append(p)
            if len(unique_bgs) >= 3:
                break

        # Collect the generated text variants.
        text_variants = [
            render_path(date, f"cover_props_v{i}.json")
            for i in range(1, COVER_VARIANT_COUNT + 1)
        ]
        text_variants = [p for p in text_variants if p.exists()]
        if not unique_bgs or not text_variants:
            raise FileNotFoundError(
                "  cover_thumbnail requires cover_bg*.png and cover_props_v*.json; "
                "run --steps cover_image first"
            )

        npx_path = find_npx()
        if not npx_path:
            raise FileNotFoundError(
                "npx not found; install Node.js or set PATH to include npx"
            )

        # cover_thumbnail renders via the Remotion CLI before prepare_render runs,
        # so the per-date public/fonts/ dir does not exist yet. Stage fonts now or
        # the still render 404s on every woff2 and fails.
        stage_fonts = getattr(self.renderer, "stage_fonts", None)
        if callable(stage_fonts):
            stage_fonts(date)

        n_bgs = len(unique_bgs)
        n_texts = len(text_variants)
        self.logger.info(
            f"  Rendering {n_bgs} bg(s) × {n_texts} text(s) = {n_bgs * n_texts} covers"
        )

        # Mirror every bg candidate into the per-date Remotion public dir so
        # the <Img> component can load them at render time.
        for bg_path in unique_bgs:
            self._mirror_cover_bg(date, bg_path)

        for bg_idx, bg_path in enumerate(unique_bgs, start=1):
            for t_idx, props_path in enumerate(text_variants, start=1):
                # Read text props, swap backgroundImage to current bg.
                with io.open(props_path, "r", encoding="utf-8") as f:
                    props = json.load(f)
                props["backgroundImage"] = bg_path.name

                # Write combined props file.
                combined_path = render_path(
                    date, f"cover_props_b{bg_idx}_t{t_idx}.json"
                )
                atomic_write_json(combined_path, props)

                # Render the cover.
                cover_path = publish_path(date, f"cover_b{bg_idx}_t{t_idx}.png")
                thumb_inputs = {
                    "props_hash": file_sha256(combined_path),
                    "bg_hash": file_sha256(bg_path),
                }
                if is_artifact_fresh(cover_path, thumb_inputs):
                    self.logger.info(f"  cover_b{bg_idx}_t{t_idx} already rendered")
                else:
                    self._render_cover_still(npx_path, combined_path, cover_path, date)
                    write_artifact_manifest(
                        cover_path,
                        step="cover_thumbnail",
                        date=date,
                        inputs=thumb_inputs,
                        config=self.config,
                    )

                # b1_t1 is the canonical cover.
                if bg_idx == 1 and t_idx == 1:
                    canonical = publish_path(date, "cover.png")
                    if not is_artifact_fresh(canonical, thumb_inputs):
                        import shutil

                        shutil.copy2(cover_path, canonical)
                        write_artifact_manifest(
                            canonical,
                            step="cover_thumbnail",
                            date=date,
                            inputs=thumb_inputs,
                            config=self.config,
                        )

    def _render_cover_still(
        self, npx_path: str, props_path: Path, output_path: Path, date: str
    ) -> None:
        """Render a single CoverThumbnail still via the Remotion CLI."""
        remotion_dir = Path("src/providers/renderer/remotion")
        cmd = [
            npx_path,
            "remotion",
            "still",
            "CoverThumbnail",
            f"--props={props_path.resolve()}",
            "--frame=0",
            f"--output={output_path.resolve()}",
            f"--public-dir={(render_remotion_dir(date) / 'public').resolve()}",
        ]
        try:
            result = subprocess.run(
                cmd,
                cwd=str(remotion_dir),
                check=True,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=120,
            )
            if result.stdout:
                self.logger.info(f"  [remotion] {result.stdout.strip()}")
            self.logger.info(f"  Cover thumbnail written to {output_path}")
        except subprocess.CalledProcessError as e:
            raise RuntimeError(
                f"Cover render failed (exit={e.returncode}):\n"
                f"  stderr: {(e.stderr or '').strip()}\n"
                f"  stdout: {(e.stdout or '').strip()}"
            ) from e
        except subprocess.TimeoutExpired as e:
            raise RuntimeError(f"Cover render timed out after 120s: {e}") from e
        except FileNotFoundError as e:
            raise FileNotFoundError(f"npx not found: {e}") from e
        if not output_path.exists() or output_path.stat().st_size <= 0:
            raise RuntimeError(
                f"Cover render did not produce a valid file: {output_path}"
            )

    def _write_publish_guide(
        self, content: ContentPackage, script: Optional[Script], date: str
    ) -> None:
        self.logger.info(
            "Step: Publish guide — generate human-facing publish checklist"
        )
        guide_path = publish_path(date, "publish_guide.md")
        title_path = publish_path(date, "title.json")
        title_payload = {}
        if title_path.exists():
            try:
                loaded_title = json.loads(title_path.read_text(encoding="utf-8"))
                if isinstance(loaded_title, dict):
                    title_payload = loaded_title
            except (OSError, json.JSONDecodeError):
                title_payload = {}
        items_payload = [
            {
                "title_cn": item.title_cn or item.title,
                "title": item.title,
                "editor_angle": item.editor_angle or item.dek or "",
                "category": item.category or "",
            }
            for item in content.items
        ]
        title_candidates = title_payload.get("title_candidates") or [
            title_payload.get("title") or (script.title if script else "HN每日观察")
        ]
        context = {
            "script_title": title_payload.get("title")
            or (script.title if script else "HN每日观察"),
            "title_candidates_json": json.dumps(
                title_candidates, ensure_ascii=False, indent=2
            ),
            "script_description": title_payload.get("description")
            or (script.description if script else ""),
            "items_json": json.dumps(items_payload, ensure_ascii=False, indent=2),
            "date": date,
        }
        # Freshness inputs are computed from disk via a shared helper so the
        # publishability audit derives an identical hash (otherwise the guide is
        # flagged stale forever: writer skips, audit complains).
        manifest_context = publish_guide_manifest_inputs(date)
        if is_artifact_fresh(guide_path, manifest_context):
            self.logger.info(f"  Publish guide already exists at {guide_path}")
            return

        if self.dry_run:
            self.logger.info("Dry run: skipping publish guide generation")
            return

        text = self.llm_provider.complete_prompt(
            "prompts/publish_guide.md",
            context,
            label="publish_guide",
            expect_json=False,
            model=self.llm_provider.fast_model,
            temperature=self.llm_provider.fast_temperature,
        )

        atomic_write_text(guide_path, text)
        write_artifact_manifest(
            guide_path,
            step="publish_guide",
            date=date,
            inputs=manifest_context,
            config=self.config,
        )
        self.logger.info(f"  Publish guide written to {guide_path}")
