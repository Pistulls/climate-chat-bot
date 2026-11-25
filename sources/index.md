# Climate research sources

Local PDF copies of the 29 sources listed in the **Climate Chat Bot Research & Design** doc
([Climate research sources](https://claude.ai/artifact/A6XhdN8L4E9XcqTUe6YRcu) tab), for loading into the vector database.

PDFs go in [`docs/`](docs/), using the file names in the **File** column. The folder is
gitignored, so the PDFs are not in the repository: the file links only work on a machine where
they have been downloaded. To rebuild the folder, download each source from its link and save it
under the listed file name.

Where a source is a web page or data portal, not a published document, the PDF is a snapshot of
that page captured on 2026-11-22. Re-capture these pages before each ingest, because the data changes.

Reuse terms were checked on 2026-11-23 against the copyright notice in each PDF, or the publisher's
page where the PDF has none. The same terms are the `licence` key in [`manifest.toml`](manifest.toml).

**Check before launch:** #8 is non-commercial. #1, #5 and #12 allow only short extracts with credit.
No terms were found for #2, #3, #6 and #16.

| # | Type | Source | File | Reuse terms | Notes |
|---|------|--------|------|-------------|-------|
| 1 | Assessment | [IPCC AR6 Synthesis Report: Summary for Policymakers (2023)](https://www.ipcc.ch/report/ar6/syr/summary-for-policymakers/) | [`01-ipcc-ar6-syr-spm.pdf`](docs/01-ipcc-ar6-syr-spm.pdf) | IPCC copyright: short extracts with the source | |
| 2 | Assessment | [IPCC AR6 WGI: The Physical Science Basis, SPM (2021)](https://www.ipcc.ch/report/ar6/wg1/downloads/report/IPCC_AR6_WGI_SPM.pdf) | [`02-ipcc-ar6-wg1-spm.pdf`](docs/02-ipcc-ar6-wg1-spm.pdf) | Not found (likely as #1) | |
| 3 | Assessment | [Climate Change: Evidence and Causes, Update 2020 (Royal Society & US NAS)](https://nap.nationalacademies.org/catalog/25733) | [`03-royal-society-nas-evidence-causes-2020.pdf`](docs/03-royal-society-nas-evidence-causes-2020.pdf) | Not found | Royal Society copy |
| 4 | Assessment | [Indicators of Global Climate Change 2025 (Forster et al., ESSD 2026)](https://essd.copernicus.org/articles/18/3889/2026/) | [`04-forster-2026-indicators-global-climate-change-2025.pdf`](docs/04-forster-2026-indicators-global-climate-change-2025.pdf) | CC BY 4.0 | |
| 5 | Annual report | [WMO State of the Global Climate 2025](https://www.wmo.int/publication-series/state-of-global-climate/state-of-global-climate-2025) | [`05-wmo-state-of-global-climate-2025.pdf`](docs/05-wmo-state-of-global-climate-2025.pdf) | WMO copyright: short extracts with the source | Full report (WMO-No. 1391) from the [WMO e-Library](https://library.wmo.int/idurl/4/69807) |
| 6 | Annual report | [Copernicus Global Climate Highlights 2025](https://climate.copernicus.eu/sites/default/files/custom-uploads/GCH-2025/GCH2025-full-report.pdf) | [`06-copernicus-global-climate-highlights-2025.pdf`](docs/06-copernicus-global-climate-highlights-2025.pdf) | Not found (Copernicus licence likely) | |
| 7 | Data | [NASA GISS Surface Temperature Analysis (GISTEMP v4)](https://data.giss.nasa.gov/gistemp/) | [`07-nasa-giss-gistemp-v4.pdf`](docs/07-nasa-giss-gistemp-v4.pdf) | US government (NASA) | Page snapshot |
| 8 | Data | [Berkeley Earth temperature data](https://berkeleyearth.org/data/) | [`08-berkeley-earth-temperature-data.pdf`](docs/08-berkeley-earth-temperature-data.pdf) | CC BY-NC 4.0 (non-commercial) | Page snapshot |
| 9 | Data | [NOAA GML: Trends in Atmospheric CO2](https://gml.noaa.gov/ccgg/trends/) | [`09-noaa-gml-co2-trends.pdf`](docs/09-noaa-gml-co2-trends.pdf) | US government (NOAA), public domain | Page snapshot |
| 10 | Data | [NASA: Sea Level Rise](https://www.nasa.gov/earth/climate-change/sea-level-rise/) | [`10-nasa-sea-level-rise.pdf`](docs/10-nasa-sea-level-rise.pdf) | US government (NASA) | Page snapshot. The original [Vital Signs: Sea Level](https://climate.nasa.gov/vital-signs/sea-level/) link now returns 404. This replacement is a news hub, not the data page, so a better source is needed |
| 11 | Data / paper | [Global Carbon Budget 2025 (Friedlingstein et al., ESSD)](https://essd.copernicus.org/articles/18/3211/2026/essd-18-3211-2026-assets.html) | [`11-global-carbon-budget-2025.pdf`](docs/11-global-carbon-budget-2025.pdf) | CC BY 4.0 | |
| 12 | Paper | [Hausfather et al. 2020, Evaluating past climate model projections (GRL)](https://doi.org/10.1029/2019GL085378) | [`12-hausfather-2020-model-projections.pdf`](docs/12-hausfather-2020-model-projections.pdf) | © AGU, all rights reserved | |
| 13 | Consensus | [Cook et al. 2013, Quantifying the consensus (ERL)](https://iopscience.iop.org/article/10.1088/1748-9326/8/2/024024) | [`13-cook-2013-quantifying-consensus.pdf`](docs/13-cook-2013-quantifying-consensus.pdf) | CC BY 3.0 | Published version, copy hosted by Skeptical Science |
| 14 | Consensus | [Lynas et al. 2021, Greater than 99% consensus (ERL)](https://doi.org/10.1088/1748-9326/ac2966) | [`14-lynas-2021-99-percent-consensus.pdf`](docs/14-lynas-2021-99-percent-consensus.pdf) | CC BY 4.0 | |
| 15 | Paper | [Cook et al. 2026, Impact of Skeptical Science rebuttals (Geoscience Communication)](https://gc.copernicus.org/articles/9/145/2026/) | [`15-cook-2026-skeptical-science-rebuttals.pdf`](docs/15-cook-2026-skeptical-science-rebuttals.pdf) | CC BY 4.0 | |
| 16 | Method | [The Debunking Handbook 2020 (Lewandowsky, Cook et al.)](https://www.climatechangecommunication.org/debunking-handbook-2020/) | [`16-debunking-handbook-2020.pdf`](docs/16-debunking-handbook-2020.pdf) | Not found | Copy hosted by Skeptical Science. The original site had an SSL error when this was captured |
| 17 | Paper | [Cook, Lewandowsky & Ecker 2017, Neutralizing misinformation through inoculation (PLOS ONE)](https://doi.org/10.1371/journal.pone.0175799) | [`17-cook-2017-inoculation.pdf`](docs/17-cook-2017-inoculation.pdf) | CC BY 4.0 | |
| 18 | Taxonomy / dataset | [Coan et al. 2021, Computer-assisted classification of contrarian claims (CARDS)](https://www.nature.com/articles/s41598-021-01714-4) | [`18-coan-2021-cards-contrarian-claims.pdf`](docs/18-coan-2021-cards-contrarian-claims.pdf) | CC BY 4.0 | |

## Energy and economics sources

Sources for questions about battery prices, power growth by source, and petrol and diesel prices. Snapshots in this section were captured on 2026-11-22.

**Check before launch:** #21, #22 and #23 are licensed for non-commercial use only.

| # | Topic | Source | File | Reuse terms | Notes |
|---|-------|--------|------|-------------|-------|
| 19 | Battery prices | [IEA Global EV Outlook 2026](https://www.iea.org/reports/global-ev-outlook-2026/electric-vehicle-batteries) | [`19-iea-global-ev-outlook-2026.pdf`](docs/19-iea-global-ev-outlook-2026.pdf) | CC BY 4.0 | Full report (295 pages). Copy hosted by the [Clean Energy Ministerial](https://www.cleanenergyministerial.org/content/uploads/2026/05/globalevoutlook2026.pdf), because iea.org blocks automated downloads |
| 20 | Battery prices | [IEA commentary: Global battery markets are growing strongly (2026)](https://www.iea.org/commentaries/global-battery-markets-are-growing-strongly-and-so-are-the-supply-risks) | [`20-iea-global-battery-markets-commentary-2026.pdf`](docs/20-iea-global-battery-markets-commentary-2026.pdf) | CC BY 4.0 | Saved manually from a browser (13 pages), because iea.org shows a bot check to automated browsers |
| 21 | Battery prices | [Ziegler & Trancik 2021, Re-examining rates of lithium-ion battery improvement and cost decline](https://pubs.rsc.org/en/content/articlehtml/2021/ee/d0ee02681f) | [`21-ziegler-trancik-2021-battery-cost-decline.pdf`](docs/21-ziegler-trancik-2021-battery-cost-decline.pdf) | CC BY-NC 3.0 (non-commercial) | [arXiv preprint](https://arxiv.org/abs/2007.13920) (August 2020), not the published version, because RSC blocks automated downloads |
| 22 | Generation costs | [IRENA Renewable Power Generation Costs in 2024](https://www.irena.org/Publications/2025/Jun/Renewable-Power-Generation-Costs-in-2024) | [`22-irena-renewable-power-generation-costs-2024.pdf`](docs/22-irena-renewable-power-generation-costs-2024.pdf) | Non-commercial use, with credit to IRENA | Full report (216 pages, 51 MB) |
| 23 | Power growth | [IRENA Renewable Capacity Statistics 2026](https://www.irena.org/Publications) | [`23-irena-renewable-capacity-statistics-2026.pdf`](docs/23-irena-renewable-capacity-statistics-2026.pdf) | Non-commercial use, with credit to IRENA | Full statistics tables (69 pages) |
| 24 | Power growth | [Ember Global Electricity Review 2026](https://ember-energy.org/latest-insights/global-electricity-review-2026/) | [`24-ember-global-electricity-review-2026.pdf`](docs/24-ember-global-electricity-review-2026.pdf) | CC BY 4.0 | Full report (119 pages) |
| 25 | Power growth | [Ember Electricity Data Explorer](https://ember-energy.org/data/electricity-data-explorer/) | [`25-ember-electricity-data-explorer.pdf`](docs/25-ember-electricity-data-explorer.pdf) | CC BY 4.0 | Page snapshot. The data itself downloads as CSV |
| 26 | Long-run energy data | [Our World in Data: Energy dataset](https://github.com/owid/energy-data) | [`26-owid-energy-dataset.pdf`](docs/26-owid-energy-dataset.pdf) | CC BY 4.0 (OWID's own work) | Snapshot of the repository page and codebook. The data itself is a CSV/JSON file in the repository |
| 27 | Fuel prices (US) | [EIA Gasoline and Diesel Fuel Update](https://www.eia.gov/petroleum/gasdiesel/) | [`27-eia-gasoline-diesel-fuel-update.pdf`](docs/27-eia-gasoline-diesel-fuel-update.pdf) | US government statistics | Page snapshot, showing prices to 16 November 2026 |
| 28 | Fuel prices (UK) | [UK DESNZ Weekly road fuel prices](https://www.gov.uk/government/statistics/weekly-road-fuel-prices) | [`28-uk-desnz-weekly-road-fuel-prices.pdf`](docs/28-uk-desnz-weekly-road-fuel-prices.pdf) | UK government open data | Page snapshot. The data itself downloads as CSV/Excel |
| 29 | Fuel prices (EU) | [European Commission Weekly Oil Bulletin](https://energy.ec.europa.eu/data-and-analysis/weekly-oil-bulletin_en) | [`29-ec-weekly-oil-bulletin.pdf`](docs/29-ec-weekly-oil-bulletin.pdf) | Reproduction allowed with credit | Page snapshot. The data itself downloads as Excel |

**Left out because their reuse terms are unclear:** the BloombergNEF battery price survey (full report is paid) and the Energy Institute Statistical Review of World Energy 2026. Much of the Energy Institute's data is already included through Our World in Data (#26).

## UK sources

UK home efficiency, energy prices, heat pumps, EV running costs, generation costs, the power mix and storage, added in plan 06 to answer UK-specific comments (the heat-pump gap plan 05 found). All are published under the [Open Government Licence v3.0](https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/). Snapshots in this section were captured on 2026-11-24.

| # | Topic | Source | File | Reuse terms | Notes |
|---|-------|--------|------|-------------|-------|
| 30 | Home efficiency | [ONS: Energy efficiency of housing in England and Wales, 2025](https://www.ons.gov.uk/peoplepopulationandcommunity/housing/articles/energyefficiencyofhousinginenglandandwales/2025) | [`30-ons-energy-efficiency-housing-2025.pdf`](docs/30-ons-energy-efficiency-housing-2025.pdf) | Open Government Licence v3.0 | ONS's own PDF of the article (13 pages) |
| 31 | Home efficiency | [English Housing Survey 2024 to 2025: Housing quality and energy efficiency](https://www.gov.uk/government/statistics/chapters-for-english-housing-survey-2024-to-2025-headline-findings-on-housing-quality-and-energy-efficiency) | [`31-ehs-2024-25-housing-quality-energy-efficiency.pdf`](docs/31-ehs-2024-25-housing-quality-energy-efficiency.pdf) | Open Government Licence v3.0 | Headline report PDF (42 pages) |
| 32 | Home efficiency | [Energy Performance of Buildings Certificates statistics, October to December 2025 (MHCLG)](https://www.gov.uk/government/statistics/energy-performance-of-building-certificates-in-england-and-wales-october-to-december-2025/energy-performance-of-buildings-certificates-statistical-release-october-to-december-2025-england-and-wales) | [`32-epc-statistics-oct-dec-2025.pdf`](docs/32-epc-statistics-oct-dec-2025.pdf) | Open Government Licence v3.0 | Page snapshot of the statistical release (31 pages) |
| 33 | Energy prices | [Ofgem: Energy price cap explained](https://www.ofgem.gov.uk/information-consumers/energy-advice-households/energy-price-cap-explained) | [`33-ofgem-energy-price-cap.pdf`](docs/33-ofgem-energy-price-cap.pdf) | Open Government Licence v3.0 | Page snapshot (3 pages). Ofgem's copyright page applies the OGL |
| 34 | Energy prices | [DESNZ Quarterly Energy Prices, September 2026](https://assets.publishing.service.gov.uk/media/6aba2810fe72ed1e2b02f0e7/Quarterly_Energy_Prices_September_2026.pdf) | [`34-desnz-quarterly-energy-prices-sep-2026.pdf`](docs/34-desnz-quarterly-energy-prices-sep-2026.pdf) | Open Government Licence v3.0 | Full release (19 pages) |
| 35 | Heat pumps | [Boiler Upgrade Scheme statistics, September 2026 (DESNZ)](https://www.gov.uk/government/statistics/boiler-upgrade-scheme-statistics-september-2026) | [`35-bus-statistics-sep-2026.pdf`](docs/35-bus-statistics-sep-2026.pdf) | Open Government Licence v3.0 | **Not ingested:** the release is a spreadsheet, and this printout is its chart sheet (5 chart images, no figures as text). #36 covers the same installation numbers. Replace with a printout of the main tables to ingest it |
| 36 | Heat pumps | [Ofgem Boiler Upgrade Scheme Annual Report 2025 to 2026](https://www.ofgem.gov.uk/sites/default/files/2026-07/BUS_Annual_Report_2025-26-20260730085029.pdf) | [`36-ofgem-bus-annual-report-2025-26.pdf`](docs/36-ofgem-bus-annual-report-2025-26.pdf) | Open Government Licence v3.0 | Full report (53 pages) |
| 37 | EV running costs | [HMRC Advisory fuel rates](https://www.gov.uk/guidance/advisory-fuel-rates) | [`37-hmrc-advisory-fuel-rates.pdf`](docs/37-hmrc-advisory-fuel-rates.pdf) | Open Government Licence v3.0 | Page snapshot (11 pages) |
| 38 | Energy source costs | [DESNZ Electricity Generation Costs 2025](https://www.gov.uk/government/publications/electricity-generation-costs-2025) | [`38-desnz-electricity-generation-costs-2025.pdf`](docs/38-desnz-electricity-generation-costs-2025.pdf) | Open Government Licence v3.0 | Main report (43 pages); the Excel annexes are left out |
| 39 | Energy source costs | [Contracts for Difference Allocation Round 7 results](https://www.gov.uk/government/publications/contracts-for-difference-cfd-allocation-round-7-results) | [`39-cfd-allocation-round-7-results.pdf`](docs/39-cfd-allocation-round-7-results.pdf) | Open Government Licence v3.0 | Round 7 results PDF (5 pages); the separate Round 7a PDF is left out |
| 40 | Power mix | [DUKES 2026, Chapter 5: Electricity](https://www.gov.uk/government/statistics/electricity-chapter-5-digest-of-united-kingdom-energy-statistics-dukes) | [`40-dukes-2026-chapter-5-electricity.pdf`](docs/40-dukes-2026-chapter-5-electricity.pdf) | Open Government Licence v3.0 | Chapter PDF (11 pages); the 12 Excel tables are left out |
| 41 | Batteries | [DESNZ Energy Innovation Needs Assessment 2025: Energy storage](https://assets.publishing.service.gov.uk/media/69449d0c9273c48f554cf642/einas-2025-energy-storage.pdf) | [`41-desnz-eina-2025-energy-storage.pdf`](docs/41-desnz-eina-2025-energy-storage.pdf) | Open Government Licence v3.0 | Full report (76 pages) |

## Related prior work

- [Climinator (2024)](https://arxiv.org/abs/2401.12566): an LLM-based fact-checker for climate claims. Not downloaded, because it is related work rather than a source for ingestion.
