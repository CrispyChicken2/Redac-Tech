"""Conversion XML → Word (.docx).

Le document produit est lisible (titres, champs, attributs mis en forme) et
chaque nœud XML est encapsulé dans un contrôle de contenu Word, ce qui permet
de revenir au XML d'origine sans perte, même après modification des textes.
Voir ``common.py`` pour la convention de balisage.
"""

from __future__ import annotations

import io
import itertools

from docx import Document
from docx.enum.style import WD_STYLE_TYPE
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor
from lxml import etree

from .common import TAG_PREFIX, XML_NS, is_real_element, parse_xml

# Éléments en ligne reconnus et mis en forme directement.
INLINE_FORMATS = {
    "b": "b", "strong": "b", "bold": "b",
    "i": "i", "em": "i", "italic": "i", "emphasis": "i",
    "u": "u", "underline": "u",
}

STYLE_TAG = "XML Balise"
STYLE_ATTR_NAME = "XML Attribut"
STYLE_ATTR_VALUE = "XML Valeur"
STYLE_PUNCT = "XML Ponctuation"
STYLE_COMMENT = "XML Commentaire"
STYLE_INLINE = "XML En ligne"
STYLE_ATTR_PARA = "XML Attributs"


def xml_to_docx(xml_bytes: bytes) -> bytes:
    tree = parse_xml(xml_bytes)
    return _Writer(tree).build()


def qualified_name(el) -> str:
    local = etree.QName(el).localname
    return f"{el.prefix}:{local}" if el.prefix else local


def _attribute_items(el, parent_nsmap: dict) -> list[tuple[str, str]]:
    """Attributs de l'élément, déclarations d'espaces de noms comprises, en noms qualifiés."""
    items: list[tuple[str, str]] = []
    for prefix, uri in el.nsmap.items():
        if parent_nsmap.get(prefix) != uri:
            items.append(("xmlns" if prefix is None else f"xmlns:{prefix}", uri))
    for key, value in el.attrib.items():
        qname = etree.QName(key)
        if qname.namespace is None:
            name = qname.localname
        elif qname.namespace == XML_NS:
            name = f"xml:{qname.localname}"
        else:
            prefix = next(
                (p for p, u in el.nsmap.items() if u == qname.namespace and p),
                None,
            )
            name = f"{prefix}:{qname.localname}" if prefix else qname.localname
        items.append((name, value))
    return items


def _is_flow(el) -> bool:
    """Vrai si l'élément se rend comme un paragraphe (feuille ou contenu mixte)."""
    if (el.text or "").strip():
        return True
    has_element_child = False
    for child in el:
        if (child.tail or "").strip() or isinstance(child, etree._Entity):
            return True
        has_element_child = has_element_child or is_real_element(child)
    return not has_element_child


class _Writer:
    def __init__(self, tree: etree._ElementTree):
        self.tree = tree
        self.doc = Document()
        self.body = self.doc.element.body
        self.ids = itertools.count(1)
        self._setup_styles()

    # ------------------------------------------------------------------ styles
    def _setup_styles(self) -> None:
        styles = self.doc.styles
        normal = styles["Normal"]
        normal.font.name = "Calibri"
        normal.font.size = Pt(11)
        normal.paragraph_format.space_after = Pt(4)

        def char(name, color, bold=False, italic=False, size=None):
            style = styles.add_style(name, WD_STYLE_TYPE.CHARACTER)
            style.font.color.rgb = RGBColor.from_string(color)
            style.font.bold = bold
            style.font.italic = italic
            if size:
                style.font.size = Pt(size)

        char(STYLE_TAG, "1F3A5F", bold=True)
        char(STYLE_ATTR_NAME, "6B7280", size=9)
        char(STYLE_ATTR_VALUE, "B45309", size=9)
        char(STYLE_PUNCT, "9CA3AF")
        char(STYLE_COMMENT, "2E7D32", italic=True)
        char(STYLE_INLINE, "1F5FAF")

        para = styles.add_style(STYLE_ATTR_PARA, WD_STYLE_TYPE.PARAGRAPH)
        para.base_style = normal
        para.paragraph_format.space_after = Pt(2)
        para.font.size = Pt(9)

    # ------------------------------------------------------- briques Word XML
    def _sdt(self, tag: str, alias: str, children) -> OxmlElement:
        sdt = OxmlElement("w:sdt")
        pr = OxmlElement("w:sdtPr")
        for name, value in (("w:alias", alias[:64]), ("w:tag", TAG_PREFIX + tag),
                            ("w:id", str(next(self.ids)))):
            node = OxmlElement(name)
            node.set(qn("w:val"), value)
            pr.append(node)
        sdt.append(pr)
        content = OxmlElement("w:sdtContent")
        for child in children:
            content.append(child)
        sdt.append(content)
        return sdt

    @staticmethod
    def _run(text: str, style: str | None = None, fmt: frozenset = frozenset()):
        run = OxmlElement("w:r")
        if style or fmt:
            rpr = OxmlElement("w:rPr")
            if style:
                rs = OxmlElement("w:rStyle")
                rs.set(qn("w:val"), style.replace(" ", ""))
                rpr.append(rs)
            for flag in ("b", "i", "u"):  # ordre imposé par le schéma
                if flag in fmt:
                    node = OxmlElement(f"w:{flag}")
                    if flag == "u":
                        node.set(qn("w:val"), "single")
                    rpr.append(node)
            run.append(rpr)
        lines = text.split("\n")
        for n, line in enumerate(lines):
            if n:
                run.append(OxmlElement("w:br"))
            for m, chunk in enumerate(line.split("\t")):
                if m:
                    run.append(OxmlElement("w:tab"))
                t = OxmlElement("w:t")
                t.set(qn("xml:space"), "preserve")
                t.text = chunk
                run.append(t)
        return run

    def _paragraph(self, style: str | None = None, depth: int = 0) -> OxmlElement:
        p = OxmlElement("w:p")
        ppr = OxmlElement("w:pPr")
        if style:
            ps = OxmlElement("w:pStyle")
            ps.set(qn("w:val"), self.doc.styles[style].style_id)
            ppr.append(ps)
        if depth:
            ind = OxmlElement("w:ind")
            ind.set(qn("w:left"), str(int(Cm(0.6 * depth).twips)))
            ppr.append(ind)
        p.append(ppr)
        return p

    def _add_block(self, node) -> None:
        self.body.sectPr.addprevious(node)

    # -------------------------------------------------------------- contenu
    def build(self) -> bytes:
        root = self.tree.getroot()
        title = self._paragraph("Title")
        title.append(self._run(f"Document XML « {qualified_name(root)} »"))
        self._add_block(title)
        self.doc.core_properties.title = qualified_name(root)

        doctype = self.tree.docinfo.doctype
        if doctype:
            p = self._paragraph()
            p.append(self._sdt("dtd", "DOCTYPE", [self._run(doctype, STYLE_PUNCT)]))
            self._add_block(p)

        for node in reversed(list(root.itersiblings(preceding=True))):
            self._add_block(self._block(node, {}, 0))
        self._add_block(self._block(root, {}, 0))
        for node in root.itersiblings():
            self._add_block(self._block(node, {}, 0))

        buffer = io.BytesIO()
        self.doc.save(buffer)
        return buffer.getvalue()

    def _block(self, node, parent_nsmap: dict, depth: int):
        """Rend un nœud au niveau bloc (paragraphe ou groupe de paragraphes)."""
        if not is_real_element(node):
            p = self._paragraph(depth=depth)
            p.append(self._inline_special(node))
            return p if not isinstance(node, etree._Comment) else self._wrap_paragraph(p)
        if _is_flow(node):
            return self._flow_element(node, parent_nsmap, depth)
        return self._container_element(node, parent_nsmap, depth)

    @staticmethod
    def _wrap_paragraph(p):
        return p

    def _attribute_runs(self, items) -> list:
        runs = []
        for n, (name, value) in enumerate(items):
            if n:
                runs.append(self._run("   ", STYLE_PUNCT))
            runs.append(self._run(f"{name} = ", STYLE_ATTR_NAME))
            runs.append(self._sdt(f"a:{name}", f"@{name}",
                                  [self._run(value, STYLE_ATTR_VALUE)]))
        return runs

    def _container_element(self, el, parent_nsmap: dict, depth: int):
        name = qualified_name(el)
        children = []
        heading = self._paragraph(f"Heading {min(depth + 1, 9)}")
        heading.append(self._run(name))
        children.append(heading)

        attrs = _attribute_items(el, parent_nsmap)
        if attrs:
            p = self._paragraph(STYLE_ATTR_PARA, depth)
            for run in self._attribute_runs(attrs):
                p.append(run)
            children.append(p)

        for child in el:
            children.append(self._block(child, el.nsmap, depth + 1))
        return self._sdt(f"e:{name}", name, children)

    def _flow_element(self, el, parent_nsmap: dict, depth: int):
        name = qualified_name(el)
        p = self._paragraph(depth=depth)
        p.append(self._run(name, STYLE_TAG))
        attrs = _attribute_items(el, parent_nsmap)
        if attrs:
            p.append(self._run(" (", STYLE_PUNCT))
            for run in self._attribute_runs(attrs):
                p.append(run)
            p.append(self._run(")", STYLE_PUNCT))
        p.append(self._run(" : ", STYLE_PUNCT))
        for run in self._content_runs(el, frozenset()):
            p.append(run)
        return self._sdt(f"e:{name}", name, [p])

    def _content_runs(self, el, fmt: frozenset) -> list:
        """Contenu d'un élément rendu en ligne (texte, sous-éléments, commentaires)."""
        runs = []
        has_children = len(el) > 0
        if el.text:
            runs.append(self._text(el.text, fmt))
        elif not has_children:
            # Élément vide : champ texte vide à remplir dans Word.
            runs.append(self._text("", fmt))
        for child in el:
            if is_real_element(child):
                runs.append(self._inline_element(child, el.nsmap, fmt))
            else:
                runs.append(self._inline_special(child))
            if child.tail:
                runs.append(self._text(child.tail, fmt))
        return runs

    def _text(self, text: str, fmt: frozenset):
        return self._sdt("t", "texte", [self._run(text, fmt=fmt)])

    def _inline_element(self, el, parent_nsmap: dict, fmt: frozenset):
        name = qualified_name(el)
        flag = INLINE_FORMATS.get(etree.QName(el).localname.lower())
        inner_fmt = fmt | {flag} if flag else fmt
        runs = []
        if not flag:
            # Élément en ligne non typographique : coloré pour être repérable.
            runs.append(self._run("‹", STYLE_PUNCT))
        for run in self._content_runs(el, inner_fmt):
            if not flag:
                _restyle(run, STYLE_INLINE)
            runs.append(run)
        if not flag:
            runs.append(self._run("›", STYLE_PUNCT))
        attrs = _attribute_items(el, parent_nsmap)
        if attrs:
            runs.append(self._run(" [", STYLE_PUNCT))
            runs.extend(self._attribute_runs(attrs))
            runs.append(self._run("]", STYLE_PUNCT))
        return self._sdt(f"e:{name}", name, runs)

    def _inline_special(self, node):
        if isinstance(node, etree._Comment):
            return self._sdt("c", "commentaire", [self._run(node.text or "", STYLE_COMMENT)])
        if isinstance(node, etree._ProcessingInstruction):
            return self._sdt(f"p:{node.target}", f"?{node.target}",
                             [self._run(node.text or "", STYLE_PUNCT)])
        if isinstance(node, etree._Entity):
            return self._sdt(f"r:{node.name}", f"&{node.name};",
                             [self._run(f"&{node.name};", STYLE_PUNCT)])
        raise TypeError(f"Nœud XML non pris en charge : {node!r}")


def _restyle(node, style: str) -> None:
    """Applique un style de caractère aux runs de texte non stylés d'un contrôle."""
    for run in node.iter(qn("w:r")):
        rpr = run.find(qn("w:rPr"))
        if rpr is None:
            rpr = OxmlElement("w:rPr")
            run.insert(0, rpr)
        if rpr.find(qn("w:rStyle")) is None:
            rs = OxmlElement("w:rStyle")
            rs.set(qn("w:val"), style.replace(" ", ""))
            rpr.insert(0, rs)
