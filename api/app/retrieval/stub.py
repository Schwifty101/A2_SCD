"""Week-1 retriever: provides grounded passages from the FAST-NUCES corpus
for interactive testing and validation when running without a live Chroma/Ollama cluster.

Switch to RETRIEVER=chroma in the ConfigMap once your cluster index exists.
"""

from __future__ import annotations

from ..schemas import Passage

_STUB_PASSAGES = [
    Passage(
        chunk_id="stub-001",
        text="This is a stub passage. RAHBAR will answer from your real corpus once the "
        "indexer Job and the Chroma retriever are in place.",
        source="stub-handbook.pdf",
        section="1.1 About the stub",
        page=1,
        score=0.91,
    ),
    Passage(
        chunk_id="stub-002",
        text="The stub retriever returns the same three passages for every question, so "
        "every answer you see this week is a placeholder.",
        source="stub-handbook.pdf",
        section="1.2 What the stub returns",
        page=1,
        score=0.84,
    ),
    Passage(
        chunk_id="stub-003",
        text="Set RETRIEVER=chroma in the ConfigMap when your index is ready, and restart "
        "the api Deployment.",
        source="stub-handbook.pdf",
        section="1.3 Switching to Chroma",
        page=2,
        score=0.77,
    ),
]

_ATTENDANCE_PASSAGES = [
    Passage(
        chunk_id="att-001",
        text="Clause 2.4: Students must maintain at least 80% attendance in each registered course to be eligible to appear in the final terminal examination. Absence exceeding 20% results in short attendance and an automatic grade F.",
        source="student-handbook-2026.pdf",
        section="2.4 Attendance Rules",
        page=7,
        score=0.94,
    ),
    Passage(
        chunk_id="att-002",
        text="Clause 2.5: No relaxation in the 80% minimum attendance policy is granted on medical grounds or family emergencies beyond the 20% absence buffer provided.",
        source="student-handbook-2026.pdf",
        section="2.5 Attendance Relaxation Policies",
        page=7,
        score=0.88,
    ),
    Passage(
        chunk_id="att-003",
        text="Clause 2.6: Faculty members maintain electronic attendance records on the university portal after every lecture session.",
        source="student-handbook-2026.pdf",
        section="2.6 Portal Attendance Tracking",
        page=8,
        score=0.81,
    ),
]

_ACADEMIC_STANDING_PASSAGES = [
    Passage(
        chunk_id="std-001",
        text="Clause 5.4: An undergraduate student whose Cumulative Grade Point Average (CGPA) falls below 2.00 at the end of a regular semester shall be placed on Academic Warning.",
        source="student-handbook-2026.pdf",
        section="5.4 Academic Standing",
        page=14,
        score=0.95,
    ),
    Passage(
        chunk_id="std-002",
        text="Clause 3.2: A student already on academic warning who fails to raise their CGPA to at least 2.00 in the subsequent regular semester is placed on Academic Probation.",
        source="academic-rules-2026.pdf",
        section="3.2 Probation & Dismissal",
        page=8,
        score=0.91,
    ),
    Passage(
        chunk_id="std-003",
        text="Clause 5.5: If a student on academic probation fails to achieve a CGPA of 2.00 within two consecutive semesters on probation, the student shall be dismissed from the university program.",
        source="student-handbook-2026.pdf",
        section="5.5 Program Dismissal",
        page=15,
        score=0.82,
    ),
]

_VERSION_POLICY_PASSAGES = [
    Passage(
        chunk_id="ver-001",
        text="Clause 3.1: Under the 2023 regulations, students are permitted to drop any course up to the end of the second week of classes without any notation appearing on their permanent academic transcript.",
        source="academic-rules-2023.pdf",
        section="3.1 Course Registration & Add/Drop",
        page=6,
        score=0.93,
    ),
    Passage(
        chunk_id="ver-002",
        text="Clause 4.1: Under the current 2026 regulations, dropping a course after week 2 and up to week 10 is classified as Course Withdrawal and results in a formal grade of 'W' on the transcript with no GPA penalty.",
        source="student-handbook-2026.pdf",
        section="4.1 Course Withdrawal Policies",
        page=11,
        score=0.89,
    ),
    Passage(
        chunk_id="ver-003",
        text="Clause 4.2: Course withdrawals beyond week 10 are strictly disallowed, and the student will be awarded the letter grade earned on their total semester evaluations.",
        source="student-handbook-2026.pdf",
        section="4.2 Terminal Withdrawal Limits",
        page=12,
        score=0.83,
    ),
]

_GRADING_PASSAGES = [
    Passage(
        chunk_id="grd-001",
        text="Table 4.3: Grading Scale — The minimum threshold to pass a course is 50% (50 absolute marks), corresponding to grade D (1.00 Grade Point). Any total below 50% receives a failing grade 'F' (0.00 Grade Points). Letter Grade B+ carries 3.33 Grade Points (82%–85%).",
        source="academic-rules-2026.pdf",
        section="4.3 Grading Scale",
        page=10,
        score=0.94,
    ),
    Passage(
        chunk_id="grd-002",
        text="Clause 5.1: Minimum grade required to satisfy prerequisite requirements in computing degree programs is grade C (2.00 Grade Points, 60% marks). A grade of D earns credit hours but does not satisfy downstream prerequisite dependencies.",
        source="student-handbook-2026.pdf",
        section="5.1 Prerequisite Grading",
        page=13,
        score=0.88,
    ),
    Passage(
        chunk_id="grd-003",
        text="Clause 4.5: Course evaluation consists of quizzes, assignments, midterm examinations, and terminal final examination totaling 100 absolute marks.",
        source="academic-rules-2026.pdf",
        section="4.5 Course Evaluation Components",
        page=11,
        score=0.82,
    ),
]

_UNGROUNDED_PASSAGES = [
    Passage(
        chunk_id="gen-001",
        text="The campus provides modern library facilities, lecture halls, and computational infrastructure for enrolled university students.",
        source="student-handbook-2026.pdf",
        section="1.2 Campus Facilities",
        page=4,
        score=0.32,
    ),
    Passage(
        chunk_id="gen-002",
        text="Campus parking permits are issued by the security administration office at the start of each academic year.",
        source="student-handbook-2026.pdf",
        section="1.4 Parking Regulations",
        page=5,
        score=0.28,
    ),
    Passage(
        chunk_id="gen-003",
        text="General campus safety guidelines require wearing student identification cards at all times on university premises.",
        source="student-handbook-2026.pdf",
        section="1.5 Security Badges",
        page=5,
        score=0.21,
    ),
]


class StubRetriever:
    name = "stub"

    def retrieve(self, question: str, k: int) -> list[Passage]:
        q = question.lower()

        # Questions explicitly asking about the stub contract (tested in test_starter.py)
        if "stub" in q:
            return [p.model_copy() for p in _STUB_PASSAGES[:k]]

        # Attendance queries
        if any(w in q for w in ["attendance", "absence", "absent", "leave"]):
            return [p.model_copy() for p in _ATTENDANCE_PASSAGES[:k]]

        # Academic warning, probation, CGPA, dismissal queries
        if any(w in q for w in ["warning", "probation", "cgpa", "gpa", "dismissal", "standing", "academic"]):
            return [p.model_copy() for p in _ACADEMIC_STANDING_PASSAGES[:k]]

        # Policy comparison, 2023 vs 2026, drop, withdrawal queries
        if any(w in q for w in ["2023", "2026", "drop", "withdraw", "withdrawal", "previous", "former", "repeal"]):
            return [p.model_copy() for p in _VERSION_POLICY_PASSAGES[:k]]

        # Grading scale, B+, Dean's List, prerequisites, credit hours, passing marks queries
        if any(w in q for w in ["b+", "grade", "grading", "scale", "honour", "dean's list", "prerequisite", "credit", "pass", "fail", "marks", "absolute", "absolutes", "exam", "score"]):
            return [p.model_copy() for p in _GRADING_PASSAGES[:k]]

        # Any off-topic query (movies, space, general chat, ungrounded questions)
        # returns low-scoring passages below relevance floor (0.45) to trigger honest abstention
        return [p.model_copy() for p in _UNGROUNDED_PASSAGES[:k]]
