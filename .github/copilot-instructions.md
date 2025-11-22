# Copilot instructions for CourseRatingsConverter-app

This repository is a small Streamlit app that parses HTML instructor-evaluation files and produces a downloadable CSV. The goal of these instructions is to give an AI coding agent the essential, actionable knowledge to be productive quickly.

**Big Picture**
- **App type:** Single-file Streamlit app at `streamlit_app.py` that handles upload -> parse -> transform -> download.
- **Primary flow:** user uploads HTML files -> `process_files()` reads and decodes each file -> `parse_evaluation_content()` extracts data (uses regex on `<pre>` contents) -> `create_dataframe()` maps parsed values to descriptive columns -> CSV download.

**Key files & functions**
- `streamlit_app.py`: entire app UI and logic. Important functions:
  - `parse_evaluation_content(content, filename="")` — parses a single HTML evaluation. Expects HTML with a `<pre>` block; returns dict or `None`.
  - `extract_survey_items(text)` — extracts numbered survey item descriptions using regex `Instructor Survey Items:` section.
  - `create_short_name(full_text)` — maps long survey text to CSV-friendly short names (see `item_mapping` dict inside).
  - `process_files(uploaded_files)` — orchestrates file decoding and calls `parse_evaluation_content` for each file.
  - `create_dataframe(all_data, survey_items)` — converts list-of-dicts into a pandas DataFrame and applies column naming conventions.

**Important patterns & conventions (project-specific)**
- Input expectation: parser looks for the content inside a `<pre>...</pre>` tag. If missing, `parse_evaluation_content` returns `None`.
- Encoding: files are decoded with UTF-8 in `process_files` (`uploaded_file.read().decode('utf-8')`). Keep that in mind when adding non-UTF-8 support.
- Regex-first parsing: most fields are extracted with regular expressions (see `item_pattern`, `overall_pattern`, and the course/instructor regexes). When modifying parsing, prefer updating or adding regex patterns rather than reworking the whole flow.
- Survey items count: `create_dataframe` currently maps `for item_num in range(1, 6):` — the app assumes 5 survey items by default. To support more items, update this range and the fallback `survey_items` block.
- Column naming: columns use the pattern `"<Short Item Name> - Mean"`, `"... - SD"`, `"... - N"`, and `"... - % Agree"`. Keep this naming when producing downstream CSVs.
- Semester ordering: the code uses `semester_order = {'Winter':1,'Spring':2,'Summer':3,'Fall':4}` for sorting. Preserve or update this mapping if adding semesters.

**Developer workflows & commands**
- Install dependencies (note: `requirements.txt` currently only lists `streamlit` but the code imports `pandas` — ensure `pandas` is installed when running locally):

```
pip install -r requirements.txt
pip install pandas
```

- Run the app locally:

```
streamlit run streamlit_app.py
```

**Common edit tasks & examples**
- Add support for a 6th survey item:
  - Update the loop in `create_dataframe` from `range(1, 6)` to `range(1, 7)`.
  - Add mapping in the fallback `survey_items` dict.

- Change how short names are generated:
  - Edit `create_short_name()` — update or expand `item_mapping` to canonicalize known item texts.

- Improve parsing robustness for missing `<pre>`:
  - `parse_evaluation_content` currently returns `None` when no `<pre>` is found. If you want to support raw-text HTML, extract body text and pass it through existing regexes instead.

**Integration points & external dependencies**
- Streamlit UI: file upload widget (`st.file_uploader`) and download button (`st.download_button`) are the external integration points to exercise.
- External libs: `streamlit`, `pandas`. Confirm `requirements.txt` before running CI or deployments.

**Notes for AI agents**
- Be conservative: preserve existing column names and the CSV format unless explicitly asked to change them — downstream users may rely on exact column names.
- When changing regexes, include unit-style examples (input snippet -> expected parsed dict) in the PR description or tests to make intent explicit.
- Small, focused patches are preferred — this repo is intentionally small and single-purpose.

If anything here is unclear or you'd like more detail (example inputs, additional sample HTML snippets, or a basic unit test harness), tell me which part to expand and I will update this file.
