# Diabetes CGM Analysis Project

This repository is a fork of [Martin Rivero’s CGM analysis project](https://github.com/martinrivero15/cgm-variability-analysis). It explores continuous glucose monitoring (CGM) data, drawing on the following paper:

[**Detrended Fluctuation Analysis in the prediction of type 2 diabetes mellitus in patients at risk: Model optimization and comparison with other metrics**](https://journals.plos.org/plosone/article?id=10.1371/journal.pone.0225817)

The original project aims to develop an analysis pipeline for future research into diabetes and distress. This fork focuses on improving its reproducibility as part of the "The Art of Reproducible and Open Science" course capstone project.

## Objectives
The project implements several analyses described in the article:

- Visualisation of glucose time series for individual patients
- Aggregated glucose curves by group
- Calculation of glucose variability metrics
- Entropy and non-linear measures
- Detrended Fluctuation Analysis (DFA)
- Quality reports per patient/day
- Summary tables
- Principal Component Analysis (PCA)

## Project Structure
- `data/raw` — Original data
- `data/processed` — Processed data
- `notebooks` — Jupyter notebooks for exploration, metrics and visualization
- `src` — Python scripts for utilities, metrics, DFA, plots and reports
- `results/figures` — Generated figures
- `results/tables` — Generated tables

## Planned Analyses

### Visualisations
- Glucose vs time for individual patients
- Clinical glucose range bands
- Aggregated curves by group (median + percentile bands)

### Metrics
- Mean glucose
- Standard deviation
- Coefficient of variation
- MAGE
- CONGA-2
- Glycaemic Fluctuation Index
- Time below 100 mg/dL (TU100)
- Area above 140 mg/dL (AO140)

### Non-linear measures

- Approximate entropy (ApEn)
- Sample entropy (SampEn)
- Poincaré plot measures (SD1 and SD2)

### DFA

- DFAraw
- DFAint
- Window and segment analysis

### Statistical Analysis
- Principal Component Analysis (PCA)

## Environment and initial validation

### Prerequisites
Install Pixi using the [official installation instructions](https://pixi.prefix.dev/#installation).

The environment is configured for 64-bit Windows (`win-64`) and has been tested on Windows AMD64 with Pixi 0.83.0. Pixi installs Python and the required packages for this project.

### Environment setup
Open PowerShell in the repository root and run:

```powershell
pixi install --locked
```