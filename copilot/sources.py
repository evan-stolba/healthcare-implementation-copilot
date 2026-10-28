"""Public, government-published sources that make up the copilot's knowledge base.

HIPAA and information-blocking rules come straight from the regulation text in the
Electronic Code of Federal Regulations (eCFR), via its public API. Explanatory pages
come from ASTP/ONC and the HL7 FHIR specification (CC0). All of it is public; no
patient data is used anywhere in this project.

Source types:
  "ecfr" - one or more sections of Title 45, fetched from the eCFR API
  "html" - a public web page
"""

SOURCES = [
    {
        "id": "hipaa-definitions",
        "title": "45 CFR 160.103 - HIPAA Definitions",
        "type": "ecfr", "part": "160", "sections": ["160.103"],
        "topic": "Privacy",
    },
    {
        "id": "hipaa-uses-disclosures",
        "title": "45 CFR 164.502, 164.506 - Uses and Disclosures of PHI",
        "type": "ecfr", "part": "164", "sections": ["164.502", "164.506"],
        "topic": "Privacy",
    },
    {
        "id": "hipaa-deidentification",
        "title": "45 CFR 164.514 - De-identification and Minimum Necessary",
        "type": "ecfr", "part": "164", "sections": ["164.514"],
        "topic": "De-identification",
    },
    {
        "id": "hipaa-right-of-access",
        "title": "45 CFR 164.524 - Individuals' Access to PHI",
        "type": "ecfr", "part": "164", "sections": ["164.524"],
        "topic": "Patient Access",
    },
    {
        "id": "hipaa-business-associates",
        "title": "45 CFR 164.504, 164.314 - Business Associate Contracts",
        "type": "ecfr", "part": "164", "sections": ["164.504", "164.314"],
        "topic": "Business Associates",
    },
    {
        "id": "hipaa-security-rule",
        "title": "45 CFR 164.306-164.312 - HIPAA Security Rule Safeguards",
        "type": "ecfr", "part": "164", "sections": ["164.306", "164.308", "164.310", "164.312"],
        "topic": "Security",
    },
    {
        "id": "hipaa-breach-notification",
        "title": "45 CFR 164.402-164.408 - Breach Notification",
        "type": "ecfr", "part": "164", "sections": ["164.402", "164.404", "164.406", "164.408"],
        "topic": "Breach",
    },
    {
        "id": "info-blocking-rule",
        "title": "45 CFR 171.101-171.103 - Information Blocking",
        "type": "ecfr", "part": "171", "sections": ["171.101", "171.102", "171.103"],
        "topic": "Information Blocking",
    },
    {
        "id": "onc-information-blocking",
        "title": "ASTP/ONC - Information Blocking",
        "type": "html", "url": "https://www.healthit.gov/topic/information-blocking",
        "topic": "Information Blocking",
    },
    {
        "id": "hl7-fhir-overview",
        "title": "HL7 FHIR - Overview",
        "type": "html", "url": "https://hl7.org/fhir/overview.html",
        "topic": "Interoperability",
    },
    {
        "id": "hl7-fhir-summary",
        "title": "HL7 FHIR - Executive Summary",
        "type": "html", "url": "https://hl7.org/fhir/summary.html",
        "topic": "Interoperability",
    },
]

for _s in SOURCES:
    if _s["type"] == "ecfr":
        _s["url"] = f"https://www.ecfr.gov/current/title-45/section-{_s['sections'][0]}"

SOURCES_BY_ID = {s["id"]: s for s in SOURCES}
