#!/usr/bin/env python3
"""Haalt de bronnen op: gemeentegeschiedenis.nl en de TOOI-waardelijst gemeenten.

gemeentegeschiedenis.nl: de lijst van gemeenten komt van de twaalf
provinciepagina's. Per gemeente wordt één RDF/XML-document opgehaald en
ongewijzigd bewaard in bron/rdfxml/.

TOOI: de graphs gemeenten (waardelijst met wijzigingen) en provincies uit de
dataset rce/tooi van de Linked Data Voorziening van de RCE, in bron/tooi/.

Wat er al staat wordt overgeslagen, dus het script is te hervatten.

Gebruik: python scripts/harvest.py [--refresh]
"""
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

SITE = 'https://www.gemeentegeschiedenis.nl'
PROVINCES = ('Groningen', 'Friesland', 'Drenthe', 'Overijssel', 'Gelderland',
             'Utrecht', 'Noord-Holland', 'Zuid-Holland', 'Zeeland',
             'Noord-Brabant', 'Limburg', 'Flevoland')
ROOT = Path(__file__).resolve().parent.parent
TARGET = ROOT / 'bron' / 'rdfxml'
USER_AGENT = 'gemeentegeschiedenis-plato-harvest/0.1'
PAUSE_SECONDS = 0.25

TOOI_GRAPH = 'https://linkeddata.cultureelerfgoed.nl/rce/tooi/graph/{name}'
TOOI_DOWNLOAD = 'https://api.linkeddata.cultureelerfgoed.nl/datasets/rce/tooi/download.trig.gz?graph={graph}'


def fetch(url):
    request = urllib.request.Request(url, headers={'User-Agent': USER_AGENT})
    for attempt in range(3):
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                return response.read()
        except (urllib.error.URLError, TimeoutError) as error:
            if attempt == 2:
                raise
            print(f'  opnieuw na fout: {error}', flush=True)
            time.sleep(5)


def municipality_slugs():
    """Slugs zoals ze in de links staan (al URL-gecodeerd), per provincie."""
    slugs = {}
    for province in PROVINCES:
        html = fetch(f'{SITE}/provincie/{province}').decode('utf-8', 'replace')
        found = set(re.findall(r'href="/gemeentenaam/([^"/]+)"', html))
        print(f'{province}: {len(found)} gemeenten', flush=True)
        for slug in found:
            slugs.setdefault(slug, province)
        time.sleep(PAUSE_SECONDS)
    return slugs


def harvest_tooi(refresh):
    target = ROOT / 'bron' / 'tooi'
    target.mkdir(parents=True, exist_ok=True)
    for name in ('gemeenten', 'provincies'):
        path = target / f'{name}.trig.gz'
        if refresh or not path.exists():
            graph = urllib.parse.quote(TOOI_GRAPH.format(name=name), safe='')
            path.write_bytes(fetch(TOOI_DOWNLOAD.format(graph=graph)))
            print(f'TOOI-graph {name} opgehaald', flush=True)


def main(refresh):
    harvest_tooi(refresh)
    TARGET.mkdir(parents=True, exist_ok=True)
    slugs = municipality_slugs()
    (ROOT / 'bron' / 'gemeenten.txt').write_text(
        '\n'.join(f'{slug}\t{province}' for slug, province in sorted(slugs.items())) + '\n',
        encoding='utf-8')
    fetched = skipped = 0
    for number, slug in enumerate(sorted(slugs), 1):
        # De slug is al URL-gecodeerd; als bestandsnaam coderen we hem nogmaals
        # zodat hij op elk bestandssysteem veilig is.
        path = TARGET / (urllib.parse.quote(slug, safe='') + '.rdf')
        if path.exists() and not refresh:
            skipped += 1
            continue
        path.write_bytes(fetch(f'{SITE}/gemeentenaam/rdfxml/{slug}'))
        fetched += 1
        if number % 100 == 0:
            print(f'{number}/{len(slugs)}', flush=True)
        time.sleep(PAUSE_SECONDS)
    print(f'{len(slugs)} gemeenten: {fetched} opgehaald, {skipped} al aanwezig')


if __name__ == '__main__':
    main('--refresh' in sys.argv)
