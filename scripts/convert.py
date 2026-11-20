#!/usr/bin/env python3
"""Zet de geschiedenis van de Nederlandse gemeenten om naar PLATO.

Bronnen (in bron/):
  rdfxml/*.rdf                    gemeentegeschiedenis.nl, één document per gemeente
  tooi/gemeenten.trig.gz          TOOI-waardelijst gemeenten met wijzigingen (LDV, rce/tooi)
  tooi/provincies.trig.gz         TOOI-provincies, alleen voor de namen (LDV, rce/tooi)

Uitvoer (in data/), één named graph per bestand:
  gemeentegeschiedenis.trig   wat gemeentegeschiedenis.nl zegt
  tooi.trig                   wat TOOI zegt, met de OWMS-identifiers die TOOI noemt
  identiteit.trig             welke entiteiten uit beide bronnen dezelfde gemeente zijn

Elke bron houdt haar eigen entiteiten en attestaties. Dat twee bronnen dezelfde
gemeente beschrijven is een aparte uitspraak (plato:IdentityRelation); records
worden niet samengevoegd.

Gebruik: python scripts/convert.py
"""
import collections
import datetime
import gzip
import re
import urllib.parse
from pathlib import Path

from rdflib import Dataset, Graph, Literal, Namespace, RDF, RDFS, URIRef
from rdflib.namespace import XSD

from platolib import PLATO, PROV, PlatoGraph, slugify

ROOT = Path(__file__).resolve().parent.parent
GG = Namespace('http://www.gemeentegeschiedenis.nl/gg-schema#')
GEO = Namespace('http://www.opengis.net/ont/geosparql#')
TOOI = Namespace('https://identifier.overheid.nl/tooi/def/ont/')
TOOIWL = Namespace('https://identifier.overheid.nl/tooi/def/wl/')
TOOI_LDV = 'https://linkeddata.cultureelerfgoed.nl/rce/tooi'
GG_SITE = 'https://www.gemeentegeschiedenis.nl'

# Formuleringen van gemeentegeschiedenis.nl bij de vier relatie-eigenschappen.
GG_WORDING = {
    'absorbedBy': 'opgegaan in',
    'absorbed': 'heeft opgenomen',
    'originatedFrom': 'ontstaan uit',
    'originated': 'is voortgekomen',
}


# --------------------------------------------------------------------------
# gemeentegeschiedenis.nl
# --------------------------------------------------------------------------

def gg_entity_iri(uri):
    """De bron schrijft dezelfde gemeente met http/https en met/zonder www.
    Eén vaste vorm, op basis van de slug."""
    slug = str(uri).rsplit('/gemeentenaam/', 1)[1]
    return f'{GG_SITE}/gemeentenaam/{urllib.parse.quote(urllib.parse.unquote(slug), safe="_-.~")}'


def last_segment(uri):
    return urllib.parse.unquote(str(uri).rstrip('/').rsplit('/', 1)[1])


def read_gg():
    """Leest alle gemeentedocumenten naar eenvoudige records."""
    records = {}
    for path in sorted((ROOT / 'bron' / 'rdfxml').glob('*.rdf')):
        graph = Graph()
        graph.parse(path, format='xml')
        subjects = list(graph.subjects(RDF.type, GG.Municipality))
        if len(subjects) != 1:
            raise SystemExit(f'{path.name}: verwacht één gemeente, vond {len(subjects)}')
        subject = subjects[0]
        iri = gg_entity_iri(subject)
        value = lambda p: graph.value(subject, p)
        record = {
            'iri': iri,
            'slug': last_segment(iri),
            'label': str(value(RDFS.label)),
            'start': str(value(GG.startDate)) if value(GG.startDate) else None,
            'end': str(value(GG.endDate)) if value(GG.endDate) else None,
            'amco': last_segment(value(GG.amsterdamCode)) if value(GG.amsterdamCode) else None,
            # De bron zet nul, één of meer codes in één URI:
            # '.../cbscode/', '.../cbscode/0305', '.../cbscode/0851 (Steenbergen), 1376 (...)'.
            'cbs': re.findall(r'(?<!\d)\d{4}(?!\d)', str(value(GG.cbsCode) or '').rsplit('/cbscode/', 1)[-1]),
            'provinces': sorted(last_segment(o) for o in graph.objects(subject, GG.inProvince)),
            'departments': sorted(last_segment(o) for o in graph.objects(subject, GG.inDepartement)),
            'links': sorted(str(o) for p in (GG.resourceWikipedia, GG.resourceDbpedia, GG.resourceGeonames)
                            for o in graph.objects(subject, p)
                            # Een lege verwijzing in de bron wijst naar het document zelf.
                            if str(o).startswith('http')),
            'relations': {key: sorted(gg_entity_iri(o) for o in graph.objects(subject, GG[key]))
                          for key in GG_WORDING},
            'geometries': sorted(
                (str(graph.value(node, GG.year)), str(graph.value(node, GG.name) or '').strip(),
                 str(graph.value(node, GEO.asWKT)))
                for node in graph.objects(subject, GEO.hasGeometry)),
        }
        # Eén gemeente is onder twee adressen op te vragen (Neuzen en Ter_Neuzen);
        # beide documenten zijn gelijk.
        records[iri] = record
    return records


def gg_changes(records):
    """Brengt de vier relatie-eigenschappen terug tot wijzigingen (eerder, later, datum).

    'A opgegaan in B' en 'B heeft A opgenomen' dateren op het einde van A;
    'B ontstaan uit A' en 'A is voortgekomen B' op het begin van B. Dezelfde
    wijziging staat vaak aan beide kanten; die uitspraken vallen dan samen.
    """
    changes = collections.defaultdict(set)
    known = lambda iri: records.get(iri, {})
    for iri, record in records.items():
        for other in record['relations']['absorbedBy']:
            changes[(iri, other, record['end'])].add('absorbedBy')
        for other in record['relations']['absorbed']:
            changes[(other, iri, known(other).get('end'))].add('absorbed')
        for other in record['relations']['originatedFrom']:
            changes[(other, iri, record['start'])].add('originatedFrom')
        for other in record['relations']['originated']:
            changes[(iri, other, known(other).get('start'))].add('originated')
    return changes


def classify(changes, records):
    """Kiest per wijziging het PLATO-relatietype, volgens de definities van PLATO.

    De bron zegt alleen 'opgegaan in' of 'ontstaan uit'. PLATO onderscheidt wat
    er feitelijk gebeurde, en dat volgt uit de bestaansdata in dezelfde bron:

    - de eerdere gemeente bestaat door               -> TransferredTo
    - zij houdt op, de latere bestond al             -> AbsorbedBy
    - zij houdt op, de latere is nieuw, en er zijn
      meer gemeenten die tegelijk in haar opgaan     -> MergedInto
    - zij houdt op en valt uiteen in meer nieuwe     -> SplitInto
    - anders, of als de data ontbreken               -> SucceededBy (algemeen)
    """
    ceased_into = collections.defaultdict(set)   # (later, datum) -> opgehouden voorgangers
    new_from = collections.defaultdict(set)      # (eerder, datum) -> nieuwe opvolgers
    facts = {}
    for earlier, later, date in changes:
        ceased = date is not None and records.get(earlier, {}).get('end') == date
        new = date is not None and records.get(later, {}).get('start') == date
        facts[(earlier, later, date)] = (ceased, new)
        if ceased and new:
            ceased_into[(later, date)].add(earlier)
            new_from[(earlier, date)].add(later)
    result = {}
    for key, (ceased, new) in facts.items():
        earlier, later, date = key
        if date is None or earlier not in records or later not in records:
            result[key] = PLATO.SucceededBy
        elif not ceased:
            result[key] = PLATO.TransferredTo
        elif not new:
            result[key] = PLATO.AbsorbedBy
        elif len(ceased_into[(later, date)]) > 1:
            result[key] = PLATO.MergedInto
        elif len(new_from[(earlier, date)]) > 1:
            result[key] = PLATO.SplitInto
        else:
            result[key] = PLATO.SucceededBy
    return result


def convert_gg(records):
    out = PlatoGraph('gemeentegeschiedenis')
    source = out.authority(PLATO.Dataset, 'gemeentegeschiedenis', 'Gemeentegeschiedenis.nl', GG_SITE + '/')

    for iri, record in records.items():
        entity = out.entity(iri, record['slug'], 'gemeentegeschiedenis')
        for link in record['links']:
            out.add(entity, RDFS.seeAlso, URIRef(link))
        key = urllib.parse.quote(record['slug'], safe='')
        record['key'] = key

        # Bestaan: naam, soort, tijdvak en codes volgens het gemeentedocument.
        existence = out.attestation(key, entity, source)
        out.name(existence, record['label'], 'nl', PLATO.Headword)
        out.type(existence, 'gemeente', GG.Municipality)
        out.timespan(existence, record['start'], record['end'], 'day')
        if record['amco']:
            out.property_value(existence, 'amsterdamse-code', GG.amsterdamCode, 'Amsterdamse code', record['amco'])
        for code in record['cbs']:
            out.property_value(existence, f'cbs-code-{code}', GG.cbsCode, 'CBS-code', code)

        # Ligging in provincie en (Franse tijd) departement.
        for kind, names in (('provincie', record['provinces']), ('departement', record['departments'])):
            for name in names:
                target = f'{GG_SITE}/{kind}/{urllib.parse.quote(name)}'
                out.entity(target, name, 'gemeentegeschiedenis')
                attestation = out.attestation(f'{key}/{kind}-{slugify(name)}', entity, source)
                out.relation(attestation, target, PLATO.ContainedIn, target_label=name)

        # Grenzen: de bron geeft een grens voor elk jaar waarin die veranderde,
        # met de naam die de gemeente in dat jaar droeg.
        per_year = collections.Counter(year for year, _, _ in record['geometries'])
        seen = collections.Counter()
        for year, name, wkt in record['geometries']:
            # Een enkele gemeente heeft twee grenzen in hetzelfde jaar.
            seen[year] += 1
            suffix = f'-{seen[year]}' if per_year[year] > 1 else ''
            attestation = out.attestation(f'{key}/grens-{year}{suffix}', entity, source)
            out.geometry(attestation, wkt, PLATO.Extent)
            if name:
                out.name(attestation, name, 'nl')
            out.timespan(attestation, year, None, 'year')

    changes = gg_changes(records)
    types = classify(changes, records)
    counts = collections.Counter()
    for (earlier, later, date), statements in sorted(changes.items(), key=lambda item: tuple(map(str, item[0]))):
        relation_type = types[(earlier, later, date)]
        counts[relation_type.split('#')[1]] += 1
        if earlier not in records:
            # Verwijzing naar een gemeente waarvan geen document is opgehaald.
            out.entity(earlier, last_segment(earlier), 'gemeentegeschiedenis')
        quoted = lambda iri: urllib.parse.quote(last_segment(iri), safe='')
        local = f'{quoted(earlier)}/naar-{quoted(later)}-{date or "ongedateerd"}'
        attestation = out.attestation(local, URIRef(earlier), source)
        wording = '; '.join(GG_WORDING[s] for s in sorted(statements))
        out.relation(attestation, later, relation_type,
                     target_label=records.get(later, {}).get('label') or last_segment(later),
                     source_label=wording)
        out.timespan(attestation, date, None, 'day')
    return out, counts


# --------------------------------------------------------------------------
# TOOI (met OWMS)
# --------------------------------------------------------------------------

def load_trig_gz(path):
    dataset = Dataset()
    with gzip.open(path, 'rt', encoding='utf-8') as handle:
        dataset.parse(data=handle.read(), format='trig')
    merged = Graph()
    for s, p, o, _ in dataset.quads((None, None, None, None)):
        merged.add((s, p, o))
    return merged


def local_date(moment):
    """Datum in Nederlandse tijd van een tijdstip dat op middernacht valt.

    TOOI geeft '2015-01-01T00:00:00+01:00'; de LDV bewaart hetzelfde tijdstip
    in UTC als '2014-12-31T23:00:00Z'. Middernacht in Nederland is 23:00 of
    22:00 UTC, dus twee uur erbij geeft in beide gevallen de juiste dag.
    """
    parsed = datetime.datetime.fromisoformat(str(moment).replace('Z', '+00:00'))
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(datetime.timezone.utc) + datetime.timedelta(hours=2)
    return parsed.date().isoformat()


def read_tooi():
    graph = load_trig_gz(ROOT / 'bron' / 'tooi' / 'gemeenten.trig.gz')
    provinces = load_trig_gz(ROOT / 'bron' / 'tooi' / 'provincies.trig.gz')
    version = str(next(graph.objects(None, TOOIWL.volgnummer)))
    return graph, version, provinces


def convert_tooi(graph, version, provinces):
    out = PlatoGraph('tooi')
    source = out.authority(PLATO.Dataset, 'tooi-gemeenten', 'TOOI-waardelijst gemeenten (compleet)',
                           'https://identifier.overheid.nl/tooi/set/rwc_gemeenten_compleet', version)
    out.add(source, RDFS.seeAlso, URIRef(TOOI_LDV))
    municipalities = {}
    for subject in sorted(graph.subjects(RDF.type, TOOI.Gemeente)):
        value = lambda p: graph.value(subject, p)
        code = str(value(TOOI.organisatiecode))
        record = {
            'iri': str(subject), 'code': str(value(TOOI.gemeentecode)),
            'name': str(value(TOOI.officieleNaamExclSoort)),
            'start': str(value(TOOI.begindatum)) if value(TOOI.begindatum) else None,
            'end': str(value(TOOI.einddatum)) if value(TOOI.einddatum) else None,
        }
        municipalities[str(subject)] = record
        entity = out.entity(subject, code, 'tooi')
        existence = out.attestation(code, entity, source)
        out.name(existence, record['name'], 'nl', PLATO.Headword)
        out.type(existence, 'gemeente', TOOI.Gemeente)
        # Geen einddatum in een lijst van bestaande en opgeheven gemeenten
        # betekent: bestaat op de zichtdatum nog.
        out.timespan(existence, record['start'], record['end'], 'day', open_end=record['end'] is None)
        out.property_value(existence, 'gemeentecode', TOOI.gemeentecode, 'gemeentecode', record['code'])

        for province in graph.objects(subject, TOOI.ligtInProvincie):
            name = provinces.value(province, TOOI.officieleNaamExclSoort)
            out.entity(province, last_segment(province), 'tooi')
            attestation = out.attestation(f'{code}/provincie-{last_segment(province)}', entity, source)
            out.relation(attestation, province, PLATO.ContainedIn, target_label=str(name) if name else None)

        # TOOI noemt bij elke gemeente de OWMS-identifier. Dat is een
        # identiteitsuitspraak van TOOI zelf.
        owms = value(TOOI.owmsId)
        if owms is not None:
            out.entity(str(owms), last_segment(owms), 'owms')
            out.identity(f'{code}-owms', subject, str(owms), 'exactMatch',
                         basis='TOOI noemt deze OWMS-term als identifier van de gemeente (tooiont:owmsId).',
                         authority=source)

    # Wijzigingen. TOOI kent drie soorten; PLATO beschrijft elke wijziging als
    # een attestatie over de eerdere gemeente die naar de latere wijst.
    counts = collections.Counter()
    plans = (
        (TOOI.Samenvoeging, PROV.generated, PLATO.MergedInto, 'Samenvoeging'),
        (TOOI.Uitbreiding, PROV.used, PLATO.AbsorbedBy, 'Uitbreiding'),
        (TOOI.Herschikking, PROV.generated, PLATO.SucceededBy, 'Herschikking'),
    )
    for event_class, target_property, relation_type, wording in plans:
        for event in sorted(graph.subjects(RDF.type, event_class)):
            date = local_date(graph.value(event, TOOI.tijdstipWijziging))
            legal = []
            for basis in sorted(graph.objects(event, TOOI.heeftJuridischeGrondslag)):
                node = out.iri('authority', 'grondslag-' + slugify(last_segment(basis)))
                out.add(node, RDF.type, PLATO.Source)
                out.add(node, PLATO.authority_uri, Literal(str(basis), datatype=XSD.anyURI))
                legal.append(node)
            for earlier in sorted(graph.objects(event, PROV.invalidated)):
                for later in sorted(graph.objects(event, target_property)):
                    local = f'{last_segment(earlier)}/naar-{last_segment(later)}-{date}'
                    attestation = out.attestation(local, earlier, source, *legal)
                    out.add(attestation, PROV.wasDerivedFrom, event)
                    out.relation(attestation, later, relation_type,
                                 target_label=municipalities.get(str(later), {}).get('name'),
                                 source_label=wording)
                    out.timespan(attestation, date, None, 'day')
                    counts[relation_type.split('#')[1]] += 1
    return out, municipalities, counts


# --------------------------------------------------------------------------
# Identiteit tussen de bronnen
# --------------------------------------------------------------------------

def plain(name):
    """Naam om te vergelijken, zonder de toevoeging waarmee een bron gelijknamige
    gemeenten onderscheidt ('Abcoude [2]', 'Bergen [NH]', 'Bergen (NH)') en
    zonder verschil in streepjes ('Súdwest Fryslân', 'Súdwest-Fryslân')."""
    name = re.sub(r'\s*(\[[^\]]*\]|\([^)]*\))$', '', name)
    return re.sub(r'\W+', ' ', name).strip().casefold()


def convert_identity(gg_records, tooi_records):
    """Koppelt een TOOI-gemeente aan een gemeente van gemeentegeschiedenis.nl
    wanneer de gemeentecode gelijk is en de bestaansperioden elkaar raken.

    - één kandidaat met dezelfde naam   -> exactMatch
    - één kandidaat met een andere naam -> closeMatch
    - meer kandidaten                   -> elk 'unspecified'; de code alleen beslist niet
    """
    out = PlatoGraph('identiteit')
    by_code = collections.defaultdict(list)
    for record in gg_records.values():
        for code in record['cbs']:
            by_code[code].append(record)
    counts = collections.Counter()
    for tooi in sorted(tooi_records.values(), key=lambda r: r['iri']):
        candidates = [
            gg for gg in by_code.get(tooi['code'], [])
            # TOOI begint in 1999; een gemeente die daarvoor ophield is een andere drager van de code.
            if (gg['end'] is None or gg['end'] >= (tooi['start'] or '1999-01-01'))
            and (tooi['end'] is None or gg['start'] is None or gg['start'] <= tooi['end'])
        ]
        if not candidates:
            counts['geen kandidaat'] += 1
            continue
        for gg in candidates:
            same_name = plain(gg['label']) == plain(tooi['name'])
            if len(candidates) > 1:
                kind = 'unspecified'
            else:
                kind = 'exactMatch' if same_name else 'closeMatch'
            counts[kind] += 1
            basis = (f"Zelfde gemeentecode {tooi['code']}; namen '{gg['label']}' en '{tooi['name']}'; "
                     f"bestaan volgens gemeentegeschiedenis.nl {gg['start'] or '?'}/{gg['end'] or '..'}, "
                     f"volgens TOOI {tooi['start'] or '?'}/{tooi['end'] or '..'}.")
            if len(candidates) > 1:
                basis += f' Er zijn {len(candidates)} kandidaten met deze code.'
            out.identity(f"{last_segment(tooi['iri'])}-{gg['key']}", gg['iri'], tooi['iri'], kind, basis=basis)
    return out, counts


def main():
    target = ROOT / 'data'
    target.mkdir(exist_ok=True)

    gg_records = read_gg()
    gg, gg_counts = convert_gg(gg_records)
    print(f'gemeentegeschiedenis: {len(gg_records)} gemeenten, '
          f'{gg.save(target / "gemeentegeschiedenis.trig"):,} triples; wijzigingen {dict(gg_counts)}')

    tooi_graph, version, provinces = read_tooi()
    tooi, tooi_records, tooi_counts = convert_tooi(tooi_graph, version, provinces)
    print(f'tooi (versie {version}): {len(tooi_records)} gemeenten, '
          f'{tooi.save(target / "tooi.trig"):,} triples; wijzigingen {dict(tooi_counts)}')

    identity, identity_counts = convert_identity(gg_records, tooi_records)
    print(f'identiteit: {identity.save(target / "identiteit.trig"):,} triples; {dict(identity_counts)}')


if __name__ == '__main__':
    main()
