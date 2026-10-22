"""Safe in-memory report imports; no user filename is written to disk."""
from io import BytesIO
from pathlib import Path
from html.parser import HTMLParser
from fastapi import APIRouter, UploadFile, File, Form, Depends, HTTPException
from sqlalchemy.orm import Session
from database.database import get_db
from core.dates import parse_date
from api.ingestion import submit_document

router = APIRouter()

class ReportHTML(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts = []
        self.hidden = 0
    def handle_starttag(self, tag, attrs):
        if tag in ('script', 'style'):
            self.hidden += 1
        elif tag in ('p', 'br', 'div', 'h1', 'h2', 'li'):
            self.parts.append('\n')
    def handle_endtag(self, tag):
        if tag in ('script', 'style'):
            self.hidden = max(0, self.hidden - 1)
    def handle_data(self, data):
        if not self.hidden:
            self.parts.append(data)


def extract_file(filename, data):
    suffix = Path(filename).suffix.lower()
    if suffix == '.pdf':
        from pypdf import PdfReader
        reader = PdfReader(BytesIO(data))
        if reader.is_encrypted:
            raise ValueError('Encrypted PDFs are not supported.')
        if len(reader.pages) > 200:
            raise ValueError('PDFs must contain at most 200 pages.')
        content = '\n\n'.join(page.extract_text() or '' for page in reader.pages)
    elif suffix in ('.txt', '.md', '.html', '.htm'):
        content = data.decode('utf-8-sig')
        if suffix in ('.html', '.htm'):
            parser = ReportHTML()
            parser.feed(content)
            content = ''.join(parser.parts)
    else:
        raise ValueError('Choose a PDF, UTF-8 text, Markdown, or HTML report.')
    if not content.strip():
        raise ValueError('No readable text found. Scanned PDFs need OCR before import.')
    return content


@router.post('/upload-file', status_code=202)
def upload_file(file: UploadFile = File(...), source_name: str = Form('Manual Upload'),
                published_at: str | None = Form(None), db: Session = Depends(get_db)):
    data = file.file.read(10 * 1024 * 1024 + 1)
    if len(data) > 10 * 1024 * 1024:
        raise HTTPException(413, 'The maximum file size is 10 MB.')
    if published_at and not parse_date(published_at):
        raise HTTPException(422, 'Provide a valid publication date.')
    try:
        content = extract_file(file.filename or '', data)
    except (ValueError, UnicodeError) as exc:
        raise HTTPException(422, str(exc)) from exc
    except Exception as exc:
        raise HTTPException(422, 'The file could not be read. Check that it is a valid report.') from exc
    doc = submit_document(db, Path(file.filename or 'Report').name[:300], content,
                          source_name.strip()[:200] or 'Manual Upload', published_at=published_at)
    return {'status': doc.processing_status, 'document_id': str(doc.id)}
