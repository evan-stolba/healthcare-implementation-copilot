"""Generate a simulated question history so the dashboard has something to show.

All clients are fictional and every entry is flagged demo=True. No API calls are made:
in-scope questions are answered in extractive mode (which sets the topic), and the
out-of-scope questions are recorded as unanswered, which is what full mode does when
Claude reports the documents don't cover a question.

Run:  python -m scripts.seed_demo_log
"""

import random
from datetime import datetime, timedelta, timezone

from copilot.answer import Answer, extractive_answer
from copilot.question_log import LOG_PATH, load, record
from copilot.retrieval import load_index

# Fictional client accounts at different stages of a rollout.
CLIENTS = {
    "Lakeshore Regional Health (fictional)": 1.6,   # weight = relative question volume
    "Prairie Valley Clinics (fictional)": 1.0,
    "Summit Orthopedic Partners (fictional)": 0.6,
    "Bayside Children's Hospital (fictional)": 1.2,
}

IN_SCOPE = [
    "What safeguards does the HIPAA Security Rule require us to have in place?",
    "Do we need to do a formal risk analysis before go-live?",
    "How long do we have to notify patients after a breach?",
    "If a laptop with patient data is stolen but it was encrypted, is that a reportable breach?",
    "Who do we notify if a breach affects more than 500 patients?",
    "When do small breaches under 500 people get reported to HHS?",
    "What does minimum necessary mean for our front-desk staff?",
    "Does minimum necessary apply to sharing records with a referring physician?",
    "How fast do we have to respond when a patient requests their records?",
    "Can we charge patients for electronic copies of their records?",
    "Can a patient ask us to send their records to a third-party app?",
    "What's the difference between Safe Harbor and Expert Determination de-identification?",
    "Which identifiers need to be removed to de-identify a dataset?",
    "Does our vendor need to sign a business associate agreement?",
    "What has to be in a business associate contract?",
    "What counts as information blocking?",
    "Are health IT developers subject to information blocking rules?",
    "What is FHIR and why does our integration team keep mentioning it?",
    "What is a FHIR resource?",
    "Can we use patient data for treatment and billing without written authorization?",
    "Does HIPAA cover paper records and verbal conversations too?",
]

# Out of scope: these become the content gaps the TSM follows up on
OUT_OF_SCOPE = [
    "How do we configure single sign-on with our identity provider?",
    "What is the training schedule for our nurses on the new module?",
    "Can we extend our go-live date by two weeks?",
    "What CPT codes are supported in the billing module?",
    "How many concurrent users does our license include?",
    "Who is our support escalation contact after hours?",
]


def main() -> None:
    if any(e.get("demo") for e in load()):
        print(f"Demo entries already exist in {LOG_PATH}; delete that file to regenerate.")
        return

    rng = random.Random(42)
    index = load_index()
    now = datetime.now(timezone.utc)
    clients, weights = list(CLIENTS), list(CLIENTS.values())

    n = 0
    for day in range(56, 0, -1):                     # eight weeks of history
        for _ in range(rng.choices([0, 1, 2, 3, 4], [2, 3, 3, 2, 1])[0]):
            client = rng.choices(clients, weights)[0]
            question = rng.choice(IN_SCOPE + OUT_OF_SCOPE)
            ts = now - timedelta(days=day, hours=rng.randint(0, 9), minutes=rng.randint(0, 59))
            if question in OUT_OF_SCOPE:
                ans = Answer(question, "Not covered by the knowledge base.", False, mode="abstained")
            else:
                ans = extractive_answer(index, question)
            record(ans, client, timestamp=ts, demo=True)
            n += 1
    print(f"Wrote {n} simulated questions to {LOG_PATH}")


if __name__ == "__main__":
    main()
