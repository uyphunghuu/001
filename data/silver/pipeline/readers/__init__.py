from data.silver.pipeline.readers.base import BaseReader
from data.silver.pipeline.readers.docx_reader import DocxReader
from data.silver.pipeline.readers.pdf_reader import PdfReader
from data.silver.pipeline.readers.txt_reader import TxtReader
from data.silver.pipeline.readers.csv_reader import CsvReader
from data.silver.pipeline.readers.xlsx_reader import XlsxReader
from data.silver.pipeline.readers.email_json_reader import EmailJsonReader
from data.silver.pipeline.readers.calendar_json_reader import CalendarJsonReader

READER_MAP = {
    ".docx": DocxReader,
    ".doc": DocxReader,
    ".pdf": PdfReader,
    ".txt": TxtReader,
    ".csv": CsvReader,
    ".xlsx": XlsxReader,
    ".xls": XlsxReader,
    "email_json": EmailJsonReader,
    "calendar_json": CalendarJsonReader,
    "email": EmailJsonReader,
    "gmail": EmailJsonReader,
    "calendar": CalendarJsonReader,
}


def get_reader(extension: str = "", source_type: str = ""):
    cls = READER_MAP.get(extension) or READER_MAP.get(source_type)
    return cls() if cls else None


__all__ = [
    "BaseReader",
    "DocxReader",
    "PdfReader",
    "TxtReader",
    "CsvReader",
    "XlsxReader",
    "EmailJsonReader",
    "CalendarJsonReader",
    "get_reader",
]
