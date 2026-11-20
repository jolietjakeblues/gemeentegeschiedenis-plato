# Gemeentegeschiedenis in PLATO

De geschiedenis van de Nederlandse gemeenten van 1812 tot en met de herindeling van 1 januari 2027, gemodelleerd met PLATO (Place Attestation Ontology, versie 0.9.0-alpha.3).

Twee bronnen zijn omgezet, elk naar een eigen named graph. Een derde graph legt vast welke gemeenten uit beide bronnen dezelfde zijn.

| Graph | Bron | Gemeenten | Dekking | Triples |
|---|---|---|---|---|
| `gemeentegeschiedenis` | gemeentegeschiedenis.nl | 1.693 | 1812 – 2021 | 142.132 |
| `tooi` | TOOI-waardelijst gemeenten, versie 6 (LDV, `rce/tooi`) | 605 | 1999 – 2027 | 26.089 |
| `identiteit` | afgeleid uit beide | 601 koppelingen | | 3.005 |

OWMS is geen aparte bron: de OWMS-waardelijst is gearchiveerd en TOOI is de opvolger. TOOI noemt bij elke gemeente wel de OWMS-identifier; die staat in de graph `tooi` als identiteitsrelatie.

## Model

- **Entiteit.** Elke gemeente is een `plato:SpatialEntity` met de IRI van haar bron: `https://www.gemeentegeschiedenis.nl/gemeentenaam/<slug>` of `https://identifier.overheid.nl/tooi/id/gemeente/gm<code>`. Dezelfde gemeente bestaat dus twee keer, één keer per bron. Records worden niet samengevoegd.
- **Bestaan.** Per gemeente één `plato:Attestation` met naam, soort, tijdvak en codes (CBS-code, Amsterdamse code, gemeentecode) zoals de bron ze geeft.
- **Grenzen.** gemeentegeschiedenis.nl geeft een grens voor elk jaar waarin die veranderde, 3.247 in totaal. Elke grens is een attestatie met geometrie (`plato:Extent`), de naam in dat jaar en het beginjaar.
- **Ligging.** Provincie en, voor de Franse tijd, departement zijn attestaties met relatietype `plato:ContainedIn`.
- **Wijzigingen.** Elke herindeling is een attestatie over de eerdere gemeente die naar de latere wijst, gedateerd op de dag waarop de wijziging inging. De formulering van de bron staat in `plato:source_label`.
- **Identiteit.** Een `plato:IdentityRelation` koppelt een gemeente van gemeentegeschiedenis.nl aan een TOOI-gemeente wanneer de gemeentecode gelijk is en de bestaansperioden elkaar raken. De onderbouwing staat in `plato:identity_basis`.

### Relatietypen

TOOI typeert wijzigingen zelf:

| TOOI | PLATO | Aantal |
|---|---|---|
| Samenvoeging | `MergedInto` | 170 |
| Uitbreiding | `AbsorbedBy` | 88 |
| Herschikking | `SucceededBy` | 12 |

gemeentegeschiedenis.nl zegt alleen "opgegaan in" of "ontstaan uit". Het PLATO-type volgt uit de bestaansdata in dezelfde bron, volgens de definities van PLATO:

| Situatie | PLATO | Aantal |
|---|---|---|
| De eerdere gemeente houdt op, de latere bestond al | `AbsorbedBy` | 646 |
| De eerdere houdt op, de latere is nieuw, en er gaan meer gemeenten tegelijk in op | `MergedInto` | 621 |
| De eerdere gemeente bestaat door | `TransferredTo` | 209 |
| Eén gemeente wordt één nieuwe, of de data ontbreken | `SucceededBy` | 105 |
| De eerdere houdt op en valt uiteen in meer nieuwe | `SplitInto` | 47 |

## Hoe goed kloppen de bronnen met elkaar?

Voor de periode die beide bronnen dekken (1 januari 2000 tot en met 1 januari 2021) zijn de wijzigingen naast elkaar gelegd, zie `rapport/vergelijking-bronnen.txt`:

- TOOI heeft 255 wijzigingen; 253 daarvan staan ook in gemeentegeschiedenis.nl, met dezelfde gemeenten en dezelfde datum.
- Bij 249 van die 253 is het afgeleide relatietype gelijk aan het type dat TOOI zelf geeft. Bij 4 zegt TOOI `AbsorbedBy` waar de afleiding op `MergedInto` uitkomt.
- 2 wijzigingen staan alleen in TOOI en 13 alleen in gemeentegeschiedenis.nl. Een deel is een verschil van één dag in de datum, een deel betreft gemeenten die over meer buren zijn verdeeld.

De bronnen verschillen stelselmatig in de einddatum: gemeentegeschiedenis.nl geeft de eerste dag waarop de gemeente niet meer bestaat (1 januari 2011), TOOI de laatste dag waarop zij bestond (31 december 2010). Beide staan in de data zoals de bron ze geeft.

Vier TOOI-gemeenten hebben geen tegenhanger in gemeentegeschiedenis.nl: Dijk en Waard, Land van Cuijk en Maashorst (2022) en Voorne aan Zee (2023). Dat is waar gemeentegeschiedenis.nl ophoudt en TOOI doorloopt.

## Eigenaardigheden van de bronnen

**gemeentegeschiedenis.nl**

- Dezelfde gemeente wordt geschreven met `http://www.` en met `https://` zonder `www.`. De conversie gebruikt één vaste vorm.
- De CBS-code staat in een URI die leeg kan zijn (225 gemeenten zonder code) of twee codes met toelichting kan bevatten (Steenbergen, Wissenkerke).
- 13 verwijzingen wijzen naar iets waar geen gemeentedocument van bestaat, zoals `Duitsland`, `(inpoldering)` en `voorheen_Belgisch_grondgebied`. Ze blijven als doel van de relatie staan.
- 4 wijzigingen hebben geen datum.
- Eén gemeente is onder twee adressen op te vragen (`Neuzen` en `Ter_Neuzen`); `Oosterwolde_Ge` heeft in vier jaren twee grenzen.
- 1.144 gemeenten hebben geen begindatum. Het tijdvak heeft dan alleen een einde.

**TOOI in de LDV**

- Tijdstippen van wijzigingen staan in UTC (`2014-12-31T23:00:00Z` voor 1 januari 2015). De conversie rekent terug naar de Nederlandse datum.
- Een gemeente zonder einddatum bestaat op de zichtdatum van de lijst nog; haar tijdvak is open (`plato:open_end`).

## Mappen

- `bron/rdfxml/`: één RDF/XML-document per gemeente van gemeentegeschiedenis.nl, ongewijzigd.
- `bron/tooi/`: de graphs `gemeenten` en `provincies` uit `rce/tooi`.
- `data/`: de drie PLATO-graphs.
- `vocab/plato.skos.ttl`: de SKOS-vocabulaires van PLATO, met de relatietypen.
- `rapport/`: de vergelijking tussen de bronnen.
- `scripts/`: oogsten, omzetten, controleren en vergelijken.

## Opnieuw maken

```powershell
python -m pip install rdflib
python scripts/harvest.py
python scripts/convert.py
python scripts/check_plato.py data/gemeentegeschiedenis.trig data/tooi.trig data/identiteit.trig
python scripts/compare_sources.py
```

`harvest.py` slaat over wat er al staat; met `--refresh` haalt het alles opnieuw op. Het oogsten van gemeentegeschiedenis.nl duurt ongeveer een half uur.

PLATO publiceert geen SHACL-shapes. `check_plato.py` controleert daarom tegen de ontologie zelf: of elke term bestaat en of domein, bereik, datatype en functionaliteit kloppen. De drie graphs geven 0 problemen.

## IRI's

Entiteiten houden de IRI van hun bron. Alles wat de conversie zelf aanmaakt (attestaties, namen, tijdvakken, identiteitsrelaties) en de graphnamen staan onder `https://linkeddata.cultureelerfgoed.nl/erfgeo/gemeentegeschiedenis/`. Die basis staat als `BASE` in `scripts/platolib.py`; wie de data in een andere dataset publiceert, past haar daar aan en draait `convert.py` opnieuw.

## Grenzen van dit model

- Een grens heeft alleen een beginjaar. Dat zij geldt tot de volgende grens volgt uit de opzet van de bron, maar is niet als einde vastgelegd.
- Het relatietype bij gemeentegeschiedenis.nl is afgeleid, niet door de bron gegeven. De overeenstemming met TOOI (249 van 253) geldt voor 2000 – 2021; voor de negentiende eeuw is er geen tweede bron om tegen te toetsen.
- Het overgedragen gebied bij een grenswijziging is niet vastgelegd; PLATO kent daar geen plaats voor.
- De identiteitsrelaties berusten op gemeentecode, naam en bestaansperiode. Ze zijn een uitspraak van deze conversie, niet van een van de bronnen.
