# CGM input data dictionary

Definitions below distinguish supplier documentation from observed file properties. Missing-value conventions are **Not documented**; `NA` entries record literal tokens observed in the files.

## Participant CSVs

Files are `data/raw/cases/case  {n}.csv`, with two spaces after `case`. All have three columns; the supplier's readme describes the time and glucose columns.

| Original name | Meaning | Units or coding | Missing-value notation |
| --- | --- | --- | --- |
| `""` (empty header) | Reading index (observed); supplier definition: Not documented | Observed consecutive integers, starting at 1 except case 197, which retains 289–576. Not the participant identifier. | Not documented |
| `hora` | Time | Observed `H:MM:SS` or `HH:MM:SS`; calendar date and time zone: Not documented | Not documented |
| `glucemia` | Interstitial glucose | mg/dL, inferred from the paper's CGM noise and threshold units (see below) | `NA` (observed) |

## Clinical file

`data/raw/clinical_data.txt` is space-delimited. Its header names seven variables; each data row also starts with an unnamed row label.

| Original name | Meaning | Units or coding | Missing-value notation |
| --- | --- | --- | --- |
| No header (leading field) | Clinical row label (observed); supplier definition: Not documented | Observed labels 1–78 then 80–209; distinct from row position | Not documented |
| `gender` | Gender | 0 = male; 1 = female | Not documented |
| `age` | Age | Years | Not documented |
| `BMI` | Body mass index | kg/m² | `NA` (observed) |
| `glycaemia` | Basal glycaemia | mg/dL | Not documented |
| `HbA1c` | HbA1c measurement | % | `NA` (observed) |
| `follow.up` | Follow-up duration | Days | `NA` (observed) |
| `T2DM` | Final diagnosis of type 2 diabetes mellitus | Observed `TRUE` and `FALSE`; explicit code meanings: Not documented | Not documented |

## Participant mapping

[samples.tsv](samples.tsv) contains one row per participant:

- `case_id`: number in the original participant filename, from 1 to 208.
- `raw_file`: exact path relative to the repository root, preserving both spaces.
- `clinical_row_position`: clinical data row numbered from 1, excluding the header.
- `clinical_row_label`: label stored in that row's unnamed leading field.

The supplier states that participant files and clinical rows are in the same order. Thus case 79 maps to clinical row position 79 with label 80. The reading index inside a participant CSV is separate from all these identifiers.

## Definition sources

Variable descriptions, clinical units, gender codes and positional correspondence come from the [supplied readme](../data/raw/readme.txt). The glucose unit is supported by the [paper's Methods](https://journals.plos.org/plosone/article?id=10.1371/journal.pone.0225817), which express added CGM noise and glucose thresholds in mg/dL; the readme does not state this unit. File formats, labels, index sequences and literal tokens were observed directly. See [sources.tsv](sources.tsv) for the existing provenance and licence records.
