# SpreadsheetBench code-generation guidance

1. Read the instruction and the answer position first; identify the target sheet, the answer range, and what each answer cell must contain.
2. Use the workbook preview only to learn the layout: header row, data columns, value types, and where the data ends. Do not hardcode previewed values or row counts; discover them from the workbook at run time.
3. Load the workbook from `INPUT_PATH` with openpyxl, compute the requested values in Python, write them into exactly the answer cells, leave every other cell, sheet, and format untouched, and save to `OUTPUT_PATH`.
