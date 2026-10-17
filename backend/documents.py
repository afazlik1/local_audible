"""Direct document text extraction. Never OCR, execute macros, or follow links."""
from pathlib import Path
from zipfile import ZipFile, BadZipFile

MAX_TEXT = 2_000_000
MAX_PAGES = 500


def extract_document(path: Path) -> list[str]:
    if path.suffix.lower() == ".pdf":
        from pypdf import PdfReader
        reader = PdfReader(path)
        if reader.is_encrypted:
            raise ValueError("Password-protected PDFs are not supported. Upload an unlocked copy.")
        if not 1 <= len(reader.pages) <= MAX_PAGES:
            raise ValueError(f"PDFs must contain between 1 and {MAX_PAGES} pages.")
        sections = []
        total = 0
        for i, page in enumerate(reader.pages, 1):
            text = (page.extract_text() or "").strip()
            resources = page.get("/Resources")
            if not text and resources and resources.get_object().get("/XObject"):
                raise ValueError(f"PDF page {i} has no extractable text and may be scanned. Upload a text-based PDF, or use the image-folder OCR workflow.")
            total += len(text)
            if total > MAX_TEXT:
                raise ValueError("Document exceeds the two-million-character text limit.")
            sections.append(text)
    elif path.suffix.lower() == ".docx":
        # Check expanded size before handing the package to the XML parser.
        try:
            with ZipFile(path) as archive:
                if sum(item.file_size for item in archive.infolist()) > 100 * 1024 * 1024:
                    raise ValueError("Word document expands beyond the 100 MB safety limit.")
                if "word/document.xml" not in archive.namelist():
                    raise ValueError("This file is not a valid Word .docx document.")
        except BadZipFile as error:
            raise ValueError("Cannot read this Word file. Save it as a valid .docx document.") from error
        from docx import Document
        from docx.text.paragraph import Paragraph
        from docx.table import Table
        def blocks(container):
            for block in container.iter_inner_content():
                if isinstance(block, Paragraph):
                    if block.text.strip():
                        yield block.text.strip()
                elif isinstance(block, Table):
                    for row in block.rows:
                        seen = set()
                        cells = []
                        for cell in row.cells:
                            if cell._tc not in seen:
                                seen.add(cell._tc)
                                cells.append(" ".join(blocks(cell)))
                        yield " | ".join(cells)
        text = "\n\n".join(blocks(Document(path)))
        if len(text) > MAX_TEXT:
            raise ValueError("Document exceeds the two-million-character text limit.")
        # Word pagination depends on fonts/printer settings: these are sections,
        # not invented page numbers. Preserve paragraphs and document order.
        from .narration import review_chunks
        sections = review_chunks(text)
    else:
        raise ValueError("Choose a PDF or Word .docx file. Save older .doc files as .docx first.")
    if not any(text.strip() for text in sections):
        raise ValueError("No embedded text was found. Use a text-based PDF/Word file or upload page images for OCR.")
    return sections
