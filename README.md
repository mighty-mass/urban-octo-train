# Data Automation (Documents)

The goal of the assignment is to fetch the latest 10k documents related to a specific company and convert them into PDF format.


How to execute the code:
```
uv sync
uv run playwright install
uv run python main.py
```


Plan:
- [x] Learn about SEC Edgar API 
- [x] First manual mock up (try no AI for deep understanding)
- [ ] Collect pain points
    - Companies lookup questions (exact match?)
    - Metadata for documents?
    - Polling or pushing events? Why?
    - SEC Access to PDF content
    - Multi URL structure
- [ ] Refine code part and structure (with AI)
- [ ] Search database options
    - Postgres?
    - Why not something else?
    - What other people use and why?

For <ins>AI prompt</ins> used check [here](PromptList.md)

