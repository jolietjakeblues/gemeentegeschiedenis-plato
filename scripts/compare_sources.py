#!/usr/bin/env python3
"""Vergelijkt wat gemeentegeschiedenis.nl en TOOI over dezelfde wijzigingen zeggen.

Gebruikt de identiteitsrelaties om gemeenten uit beide bronnen naast elkaar te
leggen en telt, voor de periode die beide bronnen dekken, welke wijzigingen in
beide voorkomen, of het relatietype gelijk is, en welke maar in één bron staan.

Gebruik: python scripts/compare_sources.py
"""
import collections
import warnings
from pathlib import Path

from rdflib import Dataset, Graph, Namespace, RDF

PLATO = Namespace('https://w3id.org/plato#')
DATA = Path(__file__).resolve().parent.parent / 'data'


def load(name):
    dataset = Dataset()
    dataset.parse(DATA / name, format='trig')
    merged = Graph()
    for s, p, o, _ in dataset.quads((None, None, None, None)):
        merged.add((s, p, o))
    return merged


def changes(graph):
    """(eerder, later, datum) -> relatietype, zonder ligging in provincie."""
    found = {}
    for attestation in graph.subjects(PLATO.has_relation_type, None):
        relation_type = graph.value(attestation, PLATO.has_relation_type)
        if relation_type == PLATO.ContainedIn:
            continue
        timespan = graph.value(attestation, PLATO.attests_timespan)
        date = str(graph.value(timespan, PLATO.start_earliest)) if timespan else None
        key = (graph.value(attestation, PLATO.attests_about), graph.value(attestation, PLATO.relates_to), date)
        found[key] = relation_type.split('#')[1]
    return found


def main():
    warnings.filterwarnings('ignore', category=DeprecationWarning)
    gg, tooi, identity = load('gemeentegeschiedenis.trig'), load('tooi.trig'), load('identiteit.trig')
    to_tooi = {identity.value(r, PLATO.identity_subject): identity.value(r, PLATO.identity_object)
               for r in identity.subjects(RDF.type, PLATO.IdentityRelation)
               if str(identity.value(r, PLATO.identity_type)) == 'exactMatch'}
    tooi_changes = changes(tooi)
    gg_changes = changes(gg)
    first = min(date for _, _, date in tooi_changes)
    last = max(date for _, _, date in gg_changes if date)
    print(f'Beide bronnen dekken {first} t/m {last}.')

    gg_mapped = {(to_tooi.get(e), to_tooi.get(l), d): t for (e, l, d), t in gg_changes.items()
                 if d and first <= d <= last}
    tooi_window = {k: t for k, t in tooi_changes.items() if first <= k[2] <= last}
    shared = [k for k in tooi_window if k in gg_mapped]
    print(f'TOOI: {len(tooi_window)} wijzigingen, gemeentegeschiedenis.nl: {len(gg_mapped)}; '
          f'in beide: {len(shared)}')
    same = sum(1 for k in shared if tooi_window[k] == gg_mapped[k])
    print(f'  zelfde relatietype: {same}')
    for (gg_type, tooi_type), count in collections.Counter(
            (gg_mapped[k], tooi_window[k]) for k in shared if tooi_window[k] != gg_mapped[k]).most_common():
        print(f'  gemeentegeschiedenis.nl {gg_type}, TOOI {tooi_type}: {count}')

    label = lambda graph, node: (graph.value(node, PLATO.entity_identifier) or node)
    only_tooi = sorted((d, str(label(tooi, e)), str(label(tooi, l)), tooi_window[(e, l, d)])
                       for e, l, d in tooi_window if (e, l, d) not in gg_mapped)
    only_gg = sorted((d, str(label(tooi, e)) if e else '?', str(label(tooi, l)) if l else '?', t)
                     for (e, l, d), t in gg_mapped.items() if (e, l, d) not in tooi_window)
    print(f'Alleen in TOOI: {len(only_tooi)}')
    for row in only_tooi:
        print('  ', *row)
    print(f'Alleen in gemeentegeschiedenis.nl: {len(only_gg)}')
    for row in only_gg:
        print('  ', *row)


if __name__ == '__main__':
    main()
