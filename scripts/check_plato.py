#!/usr/bin/env python3
"""Controleert PLATO-data tegen de PLATO-ontologie.

PLATO publiceert geen SHACL-shapes. Dit script controleert daarom wat de
ontologie zelf vastlegt:

- elke gebruikte plato:-term bestaat;
- het onderwerp van een eigenschap heeft een type dat bij het domein past;
- de waarde heeft een type of datatype dat bij het bereik past;
- een functionele eigenschap komt hooguit één keer per onderwerp voor;
- elke attestatie heeft precies één attests_about en minstens één sourced_by.

Typen worden over alle opgegeven bestanden samen opgezocht, zodat een graph
naar entiteiten in een andere graph mag verwijzen.

Gebruik: python scripts/check_plato.py data.trig [data.trig ...] [--ontology pad-of-url]
"""
import collections
import sys
import warnings

from rdflib import Dataset, Graph, Literal, Namespace, RDF, RDFS, OWL, URIRef
from rdflib.namespace import SKOS, XSD

PLATO = Namespace('https://w3id.org/plato#')
DEFAULT_ONTOLOGY = 'https://w3id.org/plato/0.9.0-alpha.3'
# Bereiken die elke literal toelaten.
ANY_LITERAL = {RDFS.Literal, None}


def load_trig(path):
    dataset = Dataset()
    dataset.parse(path, format='trig')
    merged = Graph()
    for s, p, o, _ in dataset.quads((None, None, None, None)):
        merged.add((s, p, o))
    return merged


def superclasses(ontology, cls):
    return set(ontology.transitive_objects(cls, RDFS.subClassOf))


def types_of(data, ontology, node):
    """Alle typen van een node: uit de data, of (voor PLATO-concepten) uit de ontologie."""
    found = set()
    for source in (data, ontology):
        for direct in source.objects(node, RDF.type):
            found |= superclasses(ontology, direct)
    return found


def check(path, data, context, ontology):
    defined = {s for s in ontology.subjects() if str(s).startswith(str(PLATO))}
    problems = collections.Counter()
    examples = {}

    def report(message, node):
        problems[message] += 1
        examples.setdefault(message, str(node))

    for s, p, o in data:
        for term in (p, o):
            if isinstance(term, URIRef) and str(term).startswith(str(PLATO)) and term not in defined:
                report(f'onbekende PLATO-term {term}', s)
        if not str(p).startswith(str(PLATO)) or p not in defined:
            continue
        local = str(p)[len(str(PLATO)):]
        domain = ontology.value(p, RDFS.domain)
        if isinstance(domain, URIRef) and domain not in types_of(context, ontology, s):
            report(f'{local}: onderwerp is geen {domain.split("#")[1]}', s)
        range_ = ontology.value(p, RDFS.range)
        if (p, RDF.type, OWL.ObjectProperty) in ontology:
            if isinstance(o, Literal):
                report(f'{local}: waarde is een literal, verwacht een resource', s)
            elif isinstance(range_, URIRef) and range_ not in types_of(context, ontology, o):
                report(f'{local}: waarde is geen {range_.split("#")[1]}', s)
        elif (p, RDF.type, OWL.DatatypeProperty) in ontology:
            if not isinstance(o, Literal):
                report(f'{local}: waarde is een resource, verwacht een literal', s)
            elif range_ not in ANY_LITERAL and (o.datatype or XSD.string) != range_:
                report(f'{local}: datatype is niet {range_.split("#")[1]}', s)

    for p in set(data.predicates()):
        if (p, RDF.type, OWL.FunctionalProperty) in ontology:
            for s in set(data.subjects(p, None)):
                if len(set(data.objects(s, p))) > 1:
                    report(f'{str(p)[len(str(PLATO)):]}: meer dan één waarde', s)

    attestations = set(data.subjects(RDF.type, PLATO.Attestation))
    for attestation in attestations:
        if len(set(data.objects(attestation, PLATO.attests_about))) != 1:
            report('attestatie zonder precies één attests_about', attestation)
        if not set(data.objects(attestation, PLATO.sourced_by)):
            report('attestatie zonder sourced_by', attestation)

    entities = len(set(data.subjects(RDF.type, PLATO.SpatialEntity)))
    print(f'{path}: {len(data):,} triples, {entities} entiteiten, '
          f'{len(attestations)} attestaties, {sum(problems.values())} problemen')
    for message, count in sorted(problems.items()):
        print(f'  x{count}: {message}')
        print(f'    bijvoorbeeld {examples[message]}')
    return sum(problems.values())


def main(argv):
    warnings.filterwarnings('ignore', category=DeprecationWarning)
    arguments = argv[1:]
    location = DEFAULT_ONTOLOGY
    if '--ontology' in arguments:
        position = arguments.index('--ontology')
        location = arguments[position + 1]
        del arguments[position:position + 2]
    if not arguments:
        raise SystemExit(__doc__)
    ontology = Graph()
    ontology.parse(location, format='turtle')
    version = next(ontology.objects(None, OWL.versionInfo), 'onbekende versie')
    print(f'PLATO-ontologie {version} ({location})')
    graphs = {path: load_trig(path) for path in arguments}
    context = Graph()
    for graph in graphs.values():
        context += graph
    if sum(check(path, data, context, ontology) for path, data in graphs.items()):
        raise SystemExit(1)


if __name__ == '__main__':
    main(sys.argv)
