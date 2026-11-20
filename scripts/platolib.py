"""Bouwstenen om PLATO-graphs (0.9.0-alpha.3) te schrijven."""
import re

from rdflib import Dataset, Literal, Namespace, RDF, RDFS, URIRef
from rdflib.namespace import XSD

PLATO = Namespace('https://w3id.org/plato#')
GEO = Namespace('http://www.opengis.net/ont/geosparql#')
PROV = Namespace('http://www.w3.org/ns/prov#')

# Alles wat deze conversie zelf aanmaakt (attestaties, namen, tijdvakken)
# krijgt een IRI onder BASE. Entiteiten houden de IRI van hun bron.
BASE = 'https://linkeddata.cultureelerfgoed.nl/erfgeo/gemeentegeschiedenis/'


def slugify(text):
    return re.sub(r'[^A-Za-z0-9]+', '-', str(text)).strip('-').lower()


class PlatoGraph:
    """Eén named graph met de attestaties van één bron."""

    def __init__(self, name):
        self.graph_name = name
        self.dataset = Dataset()
        self.g = self.dataset.graph(URIRef(f'{BASE}graphs/{name}'))
        for prefix, namespace in (('plato', PLATO), ('geo', GEO), ('prov', PROV)):
            self.g.bind(prefix, namespace)

    def iri(self, kind, local_id):
        return URIRef(f'{BASE}id/{self.graph_name}/{kind}/{local_id}')

    def add(self, *triple):
        self.g.add(triple)

    def authority(self, cls, local_id, title, uri, version=None):
        node = self.iri('authority', local_id)
        self.add(node, RDF.type, cls)
        self.add(node, PLATO.authority_title, Literal(title, lang='nl'))
        self.add(node, PLATO.authority_uri, Literal(uri, datatype=XSD.anyURI))
        if version:
            self.add(node, PLATO.authority_version, Literal(version, datatype=XSD.string))
        return node

    def entity(self, iri, identifier, namespace):
        node = URIRef(iri)
        self.add(node, RDF.type, PLATO.SpatialEntity)
        self.add(node, PLATO.entity_identifier, Literal(identifier, datatype=XSD.string))
        self.add(node, PLATO.namespace, Literal(namespace, datatype=XSD.string))
        return node

    def attestation(self, local_id, entity, *authorities):
        node = self.iri('attestation', local_id)
        self.add(node, RDF.type, PLATO.Attestation)
        self.add(node, PLATO.attests_about, entity)
        for authority in authorities:
            self.add(node, PLATO.sourced_by, authority)
        return node

    def name(self, attestation, text, language=None, form_status=None):
        node = URIRef(f'{attestation}/name')
        self.add(node, RDF.type, PLATO.Name)
        self.add(node, PLATO.toponym, Literal(text, lang=language))
        if language:
            self.add(node, PLATO.language, Literal(language, datatype=XSD.string))
        self.add(node, PLATO.name_type, Literal('toponym', datatype=XSD.string))
        self.add(attestation, PLATO.attests_name, node)
        if form_status is not None:
            self.add(attestation, PLATO.form_status, form_status)

    def geometry(self, attestation, wkt, role):
        node = URIRef(f'{attestation}/geometry')
        self.add(node, RDF.type, PLATO.Geometry)
        self.add(node, PLATO.geo_wkt, Literal(wkt, datatype=GEO.wktLiteral))
        # plato:geo_wkt is een subeigenschap van geo:asWKT. Een endpoint zonder
        # afleiding ziet dat niet, dus de GeoSPARQL-eigenschap staat er ook bij;
        # kaartweergaven en GeoSPARQL-functies zoeken daarop.
        self.add(node, GEO.asWKT, Literal(wkt, datatype=GEO.wktLiteral))
        self.add(node, PLATO.geometry_role, role)
        self.add(attestation, PLATO.attests_geometry, node)

    def timespan(self, attestation, start=None, end=None, precision='day', open_end=False):
        """Tijdvak volgens de bron. Alleen een begin betekent: geldt vanaf dan."""
        if start is None and end is None and not open_end:
            return
        node = URIRef(f'{attestation}/timespan')
        self.add(node, RDF.type, PLATO.Timespan)
        if start is not None:
            self.add(node, PLATO.start_earliest, Literal(start))
            self.add(node, PLATO.start_latest, Literal(start))
            self.add(node, PLATO.start_precision, Literal(precision, datatype=XSD.string))
        if end is not None:
            self.add(node, PLATO.end_earliest, Literal(end))
            self.add(node, PLATO.end_latest, Literal(end))
            self.add(node, PLATO.end_precision, Literal(precision, datatype=XSD.string))
        if open_end:
            self.add(node, PLATO.open_end, Literal(True))
        self.add(attestation, PLATO.attests_timespan, node)

    def type(self, attestation, label, type_iri):
        node = self.iri('type', slugify(label))
        self.add(node, RDF.type, PLATO.Type)
        self.add(node, PLATO.type_label, Literal(label, lang='nl'))
        self.add(node, PLATO.type_identifier, Literal(str(type_iri), datatype=XSD.anyURI))
        self.add(attestation, PLATO.attests_type, node)

    def property_value(self, attestation, key, property_iri, label, value):
        node = URIRef(f'{attestation}/property/{key}')
        self.add(node, RDF.type, PLATO.PropertyValue)
        self.add(node, PLATO.property_type, Literal(str(property_iri), datatype=XSD.anyURI))
        self.add(node, PLATO.property_label, Literal(label, lang='nl'))
        self.add(node, PLATO.value_literal, Literal(value))
        self.add(attestation, PLATO.attests_property, node)

    def relation(self, attestation, target, relation_type, target_label=None, source_label=None):
        self.add(attestation, PLATO.relates_to, URIRef(target))
        self.add(attestation, PLATO.has_relation_type, relation_type)
        if target_label:
            self.add(attestation, PLATO.related_label, Literal(target_label))
        if source_label:
            self.add(attestation, PLATO.source_label, Literal(source_label, lang='nl'))

    def identity(self, local_id, subject, obj, identity_type, basis=None, authority=None):
        node = self.iri('identity', local_id)
        self.add(node, RDF.type, PLATO.IdentityRelation)
        self.add(node, PLATO.identity_subject, URIRef(subject))
        self.add(node, PLATO.identity_object, URIRef(obj))
        self.add(node, PLATO.identity_type, Literal(identity_type, datatype=XSD.string))
        if basis:
            self.add(node, PLATO.identity_basis, Literal(basis, lang='nl'))
        if authority is not None:
            self.add(node, PLATO.identity_sourced_by, authority)
        return node

    def save(self, path):
        self.dataset.serialize(destination=str(path), format='trig')
        return len(self.g)
