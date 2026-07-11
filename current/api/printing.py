from __future__ import annotations

from html import escape


TRANSLITERATION_MAP = str.maketrans(
    {
        "А": "A",
        "Б": "B",
        "В": "V",
        "Г": "G",
        "Д": "D",
        "Е": "E",
        "Ё": "E",
        "Ж": "Zh",
        "З": "Z",
        "И": "I",
        "Й": "Y",
        "К": "K",
        "Л": "L",
        "М": "M",
        "Н": "N",
        "О": "O",
        "П": "P",
        "Р": "R",
        "С": "S",
        "Т": "T",
        "У": "U",
        "Ф": "F",
        "Х": "Kh",
        "Ц": "Ts",
        "Ч": "Ch",
        "Ш": "Sh",
        "Щ": "Sch",
        "Ъ": "",
        "Ы": "Y",
        "Ь": "",
        "Э": "E",
        "Ю": "Yu",
        "Я": "Ya",
        "а": "a",
        "б": "b",
        "в": "v",
        "г": "g",
        "д": "d",
        "е": "e",
        "ё": "e",
        "ж": "zh",
        "з": "z",
        "и": "i",
        "й": "y",
        "к": "k",
        "л": "l",
        "м": "m",
        "н": "n",
        "о": "o",
        "п": "p",
        "р": "r",
        "с": "s",
        "т": "t",
        "у": "u",
        "ф": "f",
        "х": "kh",
        "ц": "ts",
        "ч": "ch",
        "ш": "sh",
        "щ": "sch",
        "ъ": "",
        "ы": "y",
        "ь": "",
        "э": "e",
        "ю": "yu",
        "я": "ya",
    }
)


def _pdf_escape(value: str) -> str:
    return (
        value.translate(TRANSLITERATION_MAP)
        .replace("\\", "\\\\")
        .replace("(", "\\(")
        .replace(")", "\\)")
    )


def build_pdf(title: str, lines: list[str]) -> bytes:
    current_y = 790
    content_lines = [
        "BT",
        "/F1 16 Tf",
        f"50 {current_y} Td",
        f"({_pdf_escape(title)}) Tj",
        "/F1 10 Tf",
    ]
    current_y = 0
    for line in lines:
        current_y -= 16
        content_lines.append(f"0 {current_y} Td")
        content_lines.append(f"({_pdf_escape(line)}) Tj")
        current_y = 0
    content_lines.append("ET")
    stream = "\n".join(content_lines).encode("latin-1", errors="replace")

    objects = [
        b"1 0 obj<< /Type /Catalog /Pages 2 0 R >>endobj\n",
        b"2 0 obj<< /Type /Pages /Kids [3 0 R] /Count 1 >>endobj\n",
        b"3 0 obj<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>endobj\n",
        f"4 0 obj<< /Length {len(stream)} >>stream\n".encode("latin-1")
        + stream
        + b"\nendstream endobj\n",
        b"5 0 obj<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>endobj\n",
    ]

    buffer = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for obj in objects:
        offsets.append(len(buffer))
        buffer.extend(obj)

    xref_position = len(buffer)
    buffer.extend(f"xref\n0 {len(offsets)}\n".encode("latin-1"))
    buffer.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        buffer.extend(f"{offset:010d} 00000 n \n".encode("latin-1"))
    buffer.extend(
        f"trailer<< /Size {len(offsets)} /Root 1 0 R >>\nstartxref\n{xref_position}\n%%EOF".encode(
            "latin-1"
        )
    )
    return bytes(buffer)


def build_excel_xml(title: str, headers: list[str], rows: list[list[str]]) -> bytes:
    worksheet_rows = [
        "<Row>"
        + "".join(
            f"<Cell><Data ss:Type=\"String\">{escape(str(cell))}</Data></Cell>"
            for cell in headers
        )
        + "</Row>"
    ]
    for row in rows:
        worksheet_rows.append(
            "<Row>"
            + "".join(
                f"<Cell><Data ss:Type=\"String\">{escape(str(cell))}</Data></Cell>"
                for cell in row
            )
            + "</Row>"
        )

    xml = f"""<?xml version="1.0"?>
<?mso-application progid="Excel.Sheet"?>
<Workbook xmlns="urn:schemas-microsoft-com:office:spreadsheet"
 xmlns:o="urn:schemas-microsoft-com:office:office"
 xmlns:x="urn:schemas-microsoft-com:office:excel"
 xmlns:ss="urn:schemas-microsoft-com:office:spreadsheet">
 <Worksheet ss:Name="{escape(title)}">
  <Table>
   {''.join(worksheet_rows)}
  </Table>
 </Worksheet>
</Workbook>
"""
    return xml.encode("utf-8-sig")
