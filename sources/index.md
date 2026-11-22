# Climate research sources

Local PDF copies of the 18 sources listed in the **Climate Chat Bot Research & Design** doc
([Climate research sources](https://claude.ai/artifact/A6XhdN8L4E9XcqTUe6YRcu) tab), for loading into the vector database.

PDFs are in [`docs/`](docs/). Where a source is a web page or data portal, not a published
document, the PDF is a snapshot of that page captured on 2026-11-22. Re-capture these pages
before each ingest, because the data changes.

| # | Type | Source | Local copy | Notes |
|---|------|--------|------------|-------|
| 1 | Assessment | [IPCC AR6 Synthesis Report: Summary for Policymakers (2023)](https://www.ipcc.ch/report/ar6/syr/summary-for-policymakers/) | [PDF](docs/01-ipcc-ar6-syr-spm.pdf) | |
| 2 | Assessment | [IPCC AR6 WGI: The Physical Science Basis, SPM (2021)](https://www.ipcc.ch/report/ar6/wg1/downloads/report/IPCC_AR6_WGI_SPM.pdf) | [PDF](docs/02-ipcc-ar6-wg1-spm.pdf) | |
| 3 | Assessment | [Climate Change: Evidence and Causes, Update 2020 (Royal Society & US NAS)](https://nap.nationalacademies.org/catalog/25733) | [PDF](docs/03-royal-society-nas-evidence-causes-2020.pdf) | Royal Society copy |
| 4 | Assessment | [Indicators of Global Climate Change 2025 (Forster et al., ESSD 2026)](https://essd.copernicus.org/articles/18/3889/2026/) | [PDF](docs/04-forster-2026-indicators-global-climate-change-2025.pdf) | |
| 5 | Annual report | [WMO State of the Global Climate 2025](https://www.wmo.int/publication-series/state-of-global-climate/state-of-global-climate-2025) | [PDF](docs/05-wmo-state-of-global-climate-2025.pdf) | Full report (WMO-No. 1391) from the [WMO e-Library](https://library.wmo.int/idurl/4/69807) |
| 6 | Annual report | [Copernicus Global Climate Highlights 2025](https://climate.copernicus.eu/sites/default/files/custom-uploads/GCH-2025/GCH2025-full-report.pdf) | [PDF](docs/06-copernicus-global-climate-highlights-2025.pdf) | |
| 7 | Data | [NASA GISS Surface Temperature Analysis (GISTEMP v4)](https://data.giss.nasa.gov/gistemp/) | [PDF](docs/07-nasa-giss-gistemp-v4.pdf) | Page snapshot |
| 8 | Data | [Berkeley Earth temperature data](https://berkeleyearth.org/data/) | [PDF](docs/08-berkeley-earth-temperature-data.pdf) | Page snapshot |
| 9 | Data | [NOAA GML: Trends in Atmospheric CO2](https://gml.noaa.gov/ccgg/trends/) | [PDF](docs/09-noaa-gml-co2-trends.pdf) | Page snapshot |
| 10 | Data | [NASA: Sea Level Rise](https://www.nasa.gov/earth/climate-change/sea-level-rise/) | [PDF](docs/10-nasa-sea-level-rise.pdf) | Page snapshot. The original [Vital Signs: Sea Level](https://climate.nasa.gov/vital-signs/sea-level/) link now returns 404. This replacement is a news hub, not the data page, so a better source is needed |
| 11 | Data / paper | [Global Carbon Budget 2025 (Friedlingstein et al., ESSD)](https://essd.copernicus.org/articles/18/3211/2026/essd-18-3211-2026-assets.html) | [PDF](docs/11-global-carbon-budget-2025.pdf) | |
| 12 | Paper | [Hausfather et al. 2020, Evaluating past climate model projections (GRL)](https://doi.org/10.1029/2019GL085378) | [PDF](docs/12-hausfather-2020-model-projections.pdf) | |
| 13 | Consensus | [Cook et al. 2013, Quantifying the consensus (ERL)](https://iopscience.iop.org/article/10.1088/1748-9326/8/2/024024) | [PDF](docs/13-cook-2013-quantifying-consensus.pdf) | Published version, copy hosted by Skeptical Science |
| 14 | Consensus | [Lynas et al. 2021, Greater than 99% consensus (ERL)](https://doi.org/10.1088/1748-9326/ac2966) | [PDF](docs/14-lynas-2021-99-percent-consensus.pdf) | |
| 15 | Paper | [Cook et al. 2026, Impact of Skeptical Science rebuttals (Geoscience Communication)](https://gc.copernicus.org/articles/9/145/2026/) | [PDF](docs/15-cook-2026-skeptical-science-rebuttals.pdf) | |
| 16 | Method | [The Debunking Handbook 2020 (Lewandowsky, Cook et al.)](https://www.climatechangecommunication.org/debunking-handbook-2020/) | [PDF](docs/16-debunking-handbook-2020.pdf) | Copy hosted by Skeptical Science. The original site had an SSL error when this was captured |
| 17 | Paper | [Cook, Lewandowsky & Ecker 2017, Neutralizing misinformation through inoculation (PLOS ONE)](https://doi.org/10.1371/journal.pone.0175799) | [PDF](docs/17-cook-2017-inoculation.pdf) | |
| 18 | Taxonomy / dataset | [Coan et al. 2021, Computer-assisted classification of contrarian claims (CARDS)](https://www.nature.com/articles/s41598-021-01714-4) | [PDF](docs/18-coan-2021-cards-contrarian-claims.pdf) | |

## Related prior work

- [Climinator (2024)](https://arxiv.org/abs/2401.12566): an LLM-based fact-checker for climate claims. Not downloaded, because it is related work rather than a source for ingestion.
