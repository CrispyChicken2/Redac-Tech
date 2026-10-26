"""Éléments partagés par les deux sens de conversion.

Convention utilisée pour représenter un arbre XML dans un document Word
------------------------------------------------------------------------
Chaque nœud XML porteur d'information est placé dans un *contrôle de contenu*
Word (élément ``w:sdt``) dont le champ « Balise » (``w:tag``) décrit le nœud :

    xml:e:<nom qualifié>   élément           (ex. ``xml:e:dc:title``)
    xml:a:<nom qualifié>   valeur d'attribut (ex. ``xml:a:xml:lang``, ``xml:a:xmlns:dc``)
    xml:t                  nœud texte
    xml:c                  commentaire
    xml:p:<cible>          instruction de traitement
    xml:r:<nom>            référence d'entité (``&nom;``)
    xml:dtd                déclaration DOCTYPE

Tout ce qui se trouve *hors* de ces contrôles (titres affichant le nom des
balises, ponctuation, etc.) est purement décoratif et ignoré au retour.
L'utilisateur peut donc modifier librement les textes dans Word : les balises
restent à leur place.
"""

from __future__ import annotations

from lxml import etree

TAG_PREFIX = "xml:"
XML_NS = "http://www.w3.org/XML/1998/namespace"

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
R_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"


def w(local: str) -> str:
    """Nom Clark d'un élément WordprocessingML (ex. ``w('p')``)."""
    return f"{{{W_NS}}}{local}"


class ConversionError(Exception):
    """Erreur présentable telle quelle à l'utilisateur."""


def secure_parser() -> etree.XMLParser:
    """Analyseur XML sans résolution d'entités ni accès réseau (protection XXE)."""
    return etree.XMLParser(
        resolve_entities=False,
        no_network=True,
        load_dtd=False,
        remove_comments=False,
        remove_pis=False,
        strip_cdata=True,
    )


def parse_xml(data: bytes) -> etree._ElementTree:
    try:
        root = etree.fromstring(data, secure_parser())
    except etree.XMLSyntaxError as exc:
        raise ConversionError(f"Fichier XML invalide : {exc}") from exc
    return root.getroottree()


def is_real_element(node) -> bool:
    """Vrai pour un élément, faux pour commentaire / PI / entité."""
    return isinstance(node.tag, str)


def canonical(data: bytes) -> bytes:
    """Forme canonique (C14N 2.0) indépendante de l'indentation, pour comparer deux XML."""
    root = parse_xml(data).getroot()
    return etree.tostring(root, method="c14n2", strip_text=True, with_comments=True)


def indent(element, flow: set, level: int = 0, space: str = "  ") -> None:
    """Indente les éléments « conteneurs » sans toucher au contenu mixte.

    ``flow`` contient les éléments dont le contenu est du texte courant
    (paragraphes, contenu mixte) : on n'y insère jamais d'espace.
    """
    children = list(element)
    if not children or element in flow:
        return
    if (element.text or "").strip() or any((c.tail or "").strip() for c in children):
        return
    pad = "\n" + space * (level + 1)
    element.text = pad
    for child in children:
        child.tail = pad
        if is_real_element(child):
            indent(child, flow, level + 1, space)
    children[-1].tail = "\n" + space * level


def serialize(root, prolog=(), epilog=(), doctype: str | None = None) -> bytes:
    """Sérialise l'élément racine avec déclaration XML, DOCTYPE et nœuds de premier niveau."""
    root.tail = None
    parts = [b'<?xml version="1.0" encoding="UTF-8"?>']
    if doctype:
        parts.append(doctype.encode("utf-8"))
    for node in prolog:
        node.tail = None
        parts.append(etree.tostring(node, encoding="UTF-8"))
    parts.append(etree.tostring(root, encoding="UTF-8"))
    for node in epilog:
        node.tail = None
        parts.append(etree.tostring(node, encoding="UTFqua-8"))
    return b"\n".join(parts) + b"\n"
