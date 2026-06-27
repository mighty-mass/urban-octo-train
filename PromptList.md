1) I have all the metadata necessary to fetch the XLBR before converting it into PDF, I'm not sure if the the latest api actually fetch all the information I need that represent the 10-K format expected to be usuable (as balance sheet i think).
Can you double-check the output for the latest line

2) My pdf fetch works, but I get blocked even with the header sets.
Coudl you help me double-check why? Full error below from the PDF
Your Request Originates from an Undeclared Automated Tool
To allow for equitable access to all users, SEC reserves the right to limit requests
originating from undeclared automated tools. Your request has been identified as part of a
network of automated tools outside of the acceptable policy and will be managed until
action is taken to declare your traffic.
Please declare your traffic by updating your user agent to include company specific
information.
For best practices on efficiently downloading information from SEC.gov, including the latest
EDGAR filings, visit sec.gov/developer. You can also sign up for email updates on the SEC
open data program, including best practices that make it more efficient to download data,
and SEC.gov enhancements that may impact scripted downloading processes. For more
information, contact opendata@sec.gov.
For more information, please see the SEC’s Web Site Privacy and Security Policy. Thank you
for your interest in the U.S. Securities and Exchange Commission.
Reference ID: 0.e79b645f.1782578797.1944cbb6

3) Rework my code to apply the following re-structure:

single function reused everywhere for all the url calls that handle 10s rate/limit
slim big function into smaller codes for readability. keep logic and my code as much as possuible intact
Write a summary in Context.md of my code for futher reference and another AI agent inspection

4) I have something wrong for the last mile access, I have been using the sec url that is visibile as manual access in playwright but something is off. Please, help me refine the access with proper URL access. 
Latest error
raceback (most recent call last):
  File "/Users/s0002044/Documents/Workspace/urban-octo-train/main.py", line 299, in <module>
    info = get_10k_info_for_company(cik)
  File "/Users/s0002044/Documents/Workspace/urban-octo-train/main.py", line 283, in get_10k_info_for_company
    render_filing_pdf(
    ~~~~~~~~~~~~~~~~~^
        file_full_url=file_full_url,
        ^^^^^^^^^^^^^^^^^^^^^^^^^^^^
    ...<2 lines>...
        company_form=COMPANY_FORM,
        ^^^^^^^^^^^^^^^^^^^^^^^^^^
    )
    ^
  File "/Users/s0002044/Documents/Workspace/urban-octo-train/main.py", line 123, in render_filing_pdf
    raise RuntimeError(
        f"Failed to fetch filing HTML for PDF rendering. status={html_response.status_code} url={file_full_url}"
    )
RuntimeError: Failed to fetch filing HTML for PDF rendering. status=404 url=https://www.sec.gov/Archives/edgar/data/320193/000032019325000079/aapl-20240928.htm