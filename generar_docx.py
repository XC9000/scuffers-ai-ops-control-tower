"""Genera archivos .docx limpios a partir de los Markdown del proyecto.

Uso:
    python generar_docx.py

Convierte los .md de esta carpeta a .docx con estilos legibles para
revisión / impresión / envío. No requiere dependencias externas: el .docx
se construye como un zip de XML estándar de Office Open XML.

Soporta:
  - Títulos H1/H2/H3 (#, ##, ###)
  - Negrita inline (**texto**)
  - Código inline (`texto`) y bloques (```)
  - Listas con guion (-) y numeradas (1.) con anidación por indentación
  - Párrafos normales y separadores
"""
from __future__ import annotations

import re
import zipfile
from pathlib import Path
from xml.sax.saxutils import escape

ROOT = Path(__file__).resolve().parent

INLINE_CODE_RE = re.compile(r"`([^`]+)`")
BOLD_RE = re.compile(r"\*\*([^*]+)\*\*")


def run_xml(text: str, *, bold: bool = False, code: bool = False) -> str:
    """Devuelve un <w:r> con la propiedad de estilo apropiada."""
    rpr_parts: list[str] = []
    if bold:
        rpr_parts.append("<w:b/>")
    if code:
        rpr_parts.append('<w:rFonts w:ascii="Consolas" w:hAnsi="Consolas"/>')
        rpr_parts.append('<w:sz w:val="19"/>')
    rpr = f"<w:rPr>{''.join(rpr_parts)}</w:rPr>" if rpr_parts else ""
    return f'<w:r>{rpr}<w:t xml:space="preserve">{escape(text)}</w:t></w:r>'


def parse_inline(text: str) -> str:
    """Convierte negritas y código inline a runs XML preservando el resto."""
    parts: list[tuple[str, dict]] = []

    def split(text: str, pattern: re.Pattern[str], style: str) -> list[tuple[str, dict]]:
        out: list[tuple[str, dict]] = []
        last = 0
        for m in pattern.finditer(text):
            if m.start() > last:
                out.append((text[last : m.start()], {}))
            out.append((m.group(1), {style: True}))
            last = m.end()
        if last < len(text):
            out.append((text[last:], {}))
        return out

    segments: list[tuple[str, dict]] = [(text, {})]

    expanded: list[tuple[str, dict]] = []
    for seg, attrs in segments:
        if attrs:
            expanded.append((seg, attrs))
            continue
        for sub_text, sub_attrs in split(seg, INLINE_CODE_RE, "code"):
            expanded.append((sub_text, sub_attrs))
    segments = expanded

    expanded = []
    for seg, attrs in segments:
        if attrs.get("code"):
            expanded.append((seg, attrs))
            continue
        for sub_text, sub_attrs in split(seg, BOLD_RE, "bold"):
            merged = {**attrs, **sub_attrs}
            expanded.append((sub_text, merged))
    segments = expanded

    return "".join(
        run_xml(seg, bold=attrs.get("bold", False), code=attrs.get("code", False))
        for seg, attrs in segments
        if seg
    )


def paragraph(content_xml: str, *, style: str | None = None, indent: int = 0) -> str:
    ppr_parts: list[str] = []
    if style:
        ppr_parts.append(f'<w:pStyle w:val="{style}"/>')
    if indent:
        ppr_parts.append(f'<w:ind w:left="{indent}"/>')
    ppr = f"<w:pPr>{''.join(ppr_parts)}</w:pPr>" if ppr_parts else ""
    return f"<w:p>{ppr}{content_xml}</w:p>"


def code_paragraph(text: str) -> str:
    return paragraph(run_xml(text, code=True), style="Code")


def parse_markdown(md: str) -> str:
    body: list[str] = []
    in_code = False
    code_lang_marker_open = False

    for raw_line in md.splitlines():
        line = raw_line.rstrip()

        if line.startswith("```"):
            in_code = not in_code
            code_lang_marker_open = in_code
            continue

        if in_code:
            body.append(code_paragraph(line))
            continue

        if not line.strip():
            body.append(paragraph(""))
            continue

        if line.startswith("# "):
            body.append(paragraph(parse_inline(line[2:].strip()), style="Title"))
            continue
        if line.startswith("## "):
            body.append(paragraph(parse_inline(line[3:].strip()), style="Heading1"))
            continue
        if line.startswith("### "):
            body.append(paragraph(parse_inline(line[4:].strip()), style="Heading2"))
            continue
        if line.startswith("#### "):
            body.append(paragraph(parse_inline(line[5:].strip()), style="Heading3"))
            continue

        bullet = re.match(r"^(\s*)-\s+(.*)$", line)
        if bullet:
            level = len(bullet.group(1)) // 2
            indent = 360 + (level * 360)
            body.append(
                paragraph(
                    run_xml("• ") + parse_inline(bullet.group(2)),
                    indent=indent,
                )
            )
            continue

        ordered = re.match(r"^(\s*)(\d+)\.\s+(.*)$", line)
        if ordered:
            level = len(ordered.group(1)) // 2
            indent = 360 + (level * 360)
            body.append(
                paragraph(
                    run_xml(f"{ordered.group(2)}. ") + parse_inline(ordered.group(3)),
                    indent=indent,
                )
            )
            continue

        body.append(paragraph(parse_inline(line)))

    sect = (
        "<w:sectPr>"
        '<w:pgSz w:w="11906" w:h="16838"/>'
        '<w:pgMar w:top="1440" w:right="1440" w:bottom="1440" w:left="1440" '
        'w:header="708" w:footer="708" w:gutter="0"/>'
        "</w:sectPr>"
    )

    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        f"<w:body>{''.join(body)}{sect}</w:body></w:document>"
    )


CONTENT_TYPES = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
  <Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>
</Types>
"""

RELS = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
</Relationships>
"""

DOC_RELS = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"/>
"""

STYLES = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:styles xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:style w:type="paragraph" w:default="1" w:styleId="Normal">
    <w:name w:val="Normal"/>
    <w:rPr><w:rFonts w:ascii="Aptos" w:hAnsi="Aptos"/><w:sz w:val="22"/></w:rPr>
    <w:pPr><w:spacing w:after="160" w:line="276" w:lineRule="auto"/></w:pPr>
  </w:style>
  <w:style w:type="paragraph" w:styleId="Title">
    <w:name w:val="Title"/>
    <w:basedOn w:val="Normal"/>
    <w:rPr><w:b/><w:sz w:val="40"/></w:rPr>
    <w:pPr><w:spacing w:before="0" w:after="320"/></w:pPr>
  </w:style>
  <w:style w:type="paragraph" w:styleId="Heading1">
    <w:name w:val="heading 1"/>
    <w:basedOn w:val="Normal"/>
    <w:rPr><w:b/><w:sz w:val="30"/></w:rPr>
    <w:pPr><w:spacing w:before="320" w:after="180"/><w:keepNext/></w:pPr>
  </w:style>
  <w:style w:type="paragraph" w:styleId="Heading2">
    <w:name w:val="heading 2"/>
    <w:basedOn w:val="Normal"/>
    <w:rPr><w:b/><w:sz w:val="26"/></w:rPr>
    <w:pPr><w:spacing w:before="240" w:after="140"/><w:keepNext/></w:pPr>
  </w:style>
  <w:style w:type="paragraph" w:styleId="Heading3">
    <w:name w:val="heading 3"/>
    <w:basedOn w:val="Normal"/>
    <w:rPr><w:b/><w:sz w:val="23"/></w:rPr>
    <w:pPr><w:spacing w:before="200" w:after="120"/><w:keepNext/></w:pPr>
  </w:style>
  <w:style w:type="paragraph" w:styleId="Code">
    <w:name w:val="Code"/>
    <w:basedOn w:val="Normal"/>
    <w:rPr><w:rFonts w:ascii="Consolas" w:hAnsi="Consolas"/><w:sz w:val="19"/></w:rPr>
    <w:pPr><w:spacing w:after="80"/></w:pPr>
  </w:style>
</w:styles>
"""


def write_docx(source: Path, target: Path) -> None:
    document_xml = parse_markdown(source.read_text(encoding="utf-8"))
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as docx:
        docx.writestr("[Content_Types].xml", CONTENT_TYPES)
        docx.writestr("_rels/.rels", RELS)
        docx.writestr("word/_rels/document.xml.rels", DOC_RELS)
        docx.writestr("word/styles.xml", STYLES)
        docx.writestr("word/document.xml", document_xml)
    print(f"OK  {target.name}")


def main() -> None:
    sources = [
        ("propuesta_tecnica_detallada.md", "Propuesta tecnica detallada Scuffers.docx"),
        ("guia_completa_ia_automatizacion.md", "Guia completa IA y automatizacion Scuffers.docx"),
    ]
    for src_name, dst_name in sources:
        src = ROOT / src_name
        dst = ROOT / dst_name
        if not src.exists():
            print(f"SKIP {src_name} (no existe)")
            continue
        write_docx(src, dst)


if __name__ == "__main__":
    main()
