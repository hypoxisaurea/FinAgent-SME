from __future__ import annotations

from pathlib import Path
from typing import Iterable


def _open_pdfplumber(pdf_path: str):
    try:
        import pdfplumber
    except ImportError as exc:
        raise RuntimeError(
            "pdfplumber is required for PDF extraction. Install it with 'pip install pdfplumber'"
        ) from exc

    return pdfplumber.open(pdf_path)


def extract_pdf_text(pdf_path: str) -> list[str]:
    """PDF의 각 페이지에서 텍스트를 추출합니다."""
    source_path = Path(pdf_path)
    if not source_path.exists():
        raise FileNotFoundError(f"PDF 파일을 찾을 수 없습니다: {source_path}")

    texts: list[str] = []
    with _open_pdfplumber(str(source_path)) as pdf:
        for page in pdf.pages:
            texts.append(page.extract_text() or "")
    return texts


def extract_pdf_chart_images(pdf_path: str, output_dir: Path | str) -> list[str]:
    """PDF에서 이미지 객체를 찾아 chart 이미지로 저장합니다."""
    source_path = Path(pdf_path)
    if not source_path.exists():
        raise FileNotFoundError(f"PDF 파일을 찾을 수 없습니다: {source_path}")

    target_dir = Path(output_dir)
    target_dir.mkdir(parents=True, exist_ok=True)

    image_paths: list[str] = []
    with _open_pdfplumber(str(source_path)) as pdf:
        for page_number, page in enumerate(pdf.pages, start=1):
            page_image = page.to_image(resolution=150)
            for image_index, image_object in enumerate(page.images, start=1):
                bbox = (
                    image_object["x0"],
                    image_object["top"],
                    image_object["x1"],
                    image_object["bottom"],
                )
                output_path = target_dir / f"page{page_number}_image{image_index}.png"
                page_image.crop(bbox).save(output_path)
                image_paths.append(str(output_path))

    return image_paths
