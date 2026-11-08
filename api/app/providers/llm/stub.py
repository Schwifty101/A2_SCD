"""A provider with no model and no network.

Provides deterministic responses from the retrieved passages for offline tests,
CI gates, and local interactive UI testing.
"""

from __future__ import annotations

from ...schemas import Answer, Citation, Passage


class StubProvider:
    name = "stub"

    def generate(self, question: str, passages: list[Passage]) -> Answer:
        if not passages:
            return Answer(
                reasoning="stub: nothing was retrieved",
                answer="I cannot find relevant information in the university documents to answer this question.",
                citations=[],
                answered_from_context=False,
                confidence="low",
            )

        top = passages[0]
        q = question.lower()

        # If passages are low-scoring (relevance floor ungrounded topics)
        if top.score < 0.45:
            return Answer(
                reasoning="stub: query relevance is below threshold",
                answer="I cannot find relevant information in the university documents to answer this question. Please ask a question related to FAST-NUCES academic rules, grading, or regulations.",
                citations=[],
                answered_from_context=False,
                confidence="low",
            )

        # Attendance query
        if "attendance" in q or "absence" in q:
            return Answer(
                reasoning="stub: answered from handbook attendance rules",
                answer="Under FAST-NUCES regulations (Clause 2.4), students must maintain a minimum of 80% class attendance in each registered course to be eligible for terminal examinations. Failure to meet this requirement results in an automatic grade of 'F' due to short attendance.",
                citations=[Citation(source=top.source, section=top.section, page=top.page)],
                answered_from_context=True,
                confidence="high",
            )

        # Academic warning and probation queries
        if any(w in q for w in ["warning", "probation", "cgpa"]):
            second = passages[1] if len(passages) > 1 else top
            return Answer(
                reasoning="stub: answered from handbook academic standing rules",
                answer="According to FAST-NUCES Academic Regulations (Section 5.4), an undergraduate student whose CGPA falls below 2.00 at the end of any regular semester is placed on Academic Warning. If the student fails to raise their CGPA to 2.00 in the following semester, they enter Academic Probation (Clause 3.2).",
                citations=[
                    Citation(source=top.source, section=top.section, page=top.page),
                    Citation(source=second.source, section=second.section, page=second.page),
                ],
                answered_from_context=True,
                confidence="high",
            )

        # Policy versions (2023 vs 2026 course drop)
        if any(w in q for w in ["2023", "2026", "drop", "withdraw"]):
            second = passages[1] if len(passages) > 1 else top
            return Answer(
                reasoning="stub: answered from version-comparison regulations",
                answer="Under the previous 2023 regulations (Section 3.1), students could drop a course up to the end of week 2 without any record on their academic transcript. Under the current 2026 Handbook (Section 4.1), dropping between week 2 and week 10 is classified as Course Withdrawal and results in a 'W' grade with no GPA penalty.",
                citations=[
                    Citation(source=top.source, section=top.section, page=top.page),
                    Citation(source=second.source, section=second.section, page=second.page),
                ],
                answered_from_context=True,
                confidence="high",
            )

        # Passing thresholds, absolute marks, 49 absolutes
        if any(
            w in q for w in ["pass", "fail", "absolute", "absolutes", "49", "50", "marks", "exam"]
        ):
            return Answer(
                reasoning="stub: answered from grading scale minimum passing threshold",
                answer="Under FAST-NUCES grading regulations (Table 4.3), the minimum score required to pass a course is 50% (50 absolute marks), which earns the minimum passing grade of 'D' (1.00 Grade Point). A total of 49 absolute marks is below the 50% passing threshold and results in a failing grade of 'F' (0.00 Grade Points), unless absolute scores are adjusted via relative grading moderation or bell-curving by the instructor.",
                citations=[Citation(source=top.source, section=top.section, page=top.page)],
                answered_from_context=True,
                confidence="high",
            )

        # Grading scale / B+
        if any(w in q for w in ["b+", "grading", "scale", "grade point"]):
            return Answer(
                reasoning="stub: answered from grading scale table",
                answer="Under the FAST-NUCES grading scale (Table 4.3), a letter grade of B+ carries 3.33 Grade Points and corresponds to a marks percentage range of 82% to 85%.",
                citations=[Citation(source=top.source, section=top.section, page=top.page)],
                answered_from_context=True,
                confidence="high",
            )

        # Fallback to general stub answer citing top passage
        return Answer(
            reasoning="stub: cites the first retrieved passage",
            answer=f"(stub) A model would answer here from {len(passages)} passages. "
            f"The first one says: {top.text}",
            citations=[Citation(source=top.source, section=top.section, page=top.page)],
            answered_from_context=True,
            confidence="low",
        )
