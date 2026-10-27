"""Generated test documents and canned parser output (no binary files in the repo)."""

from __future__ import annotations

import io
from typing import Any

from docx import Document

RESUME_LINES = [
    "Ada Lovelace",
    "ada@example.com | +1 555 010 0199 | London, UK",
    "Summary",
    "Backend engineer focused on Python APIs and data pipelines.",
    "Experience",
    "Senior Software Engineer, Analytical Engines Ltd, 2021-03 to present",
    "- Built FastAPI services handling 2M requests per day on AWS.",
    "- Cut PostgreSQL query latency by 40% with indexing and caching in Redis.",
    "Software Engineer, Difference Labs, 2018-06 to 2021-02",
    "- Developed Django REST APIs and React dashboards for 30 clients.",
    "Software Engineering Intern, Babbage & Co, 2017-06 to 2017-09",
    "- Wrote Python scripts to automate reporting.",
    "Education",
    "BSc Computer Science, University of London, 2014-2018",
    "Skills",
    "Python, FastAPI, Django, React, PostgreSQL, Redis, AWS, Docker, k8s, JS",
]


def make_docx(lines: list[str] = RESUME_LINES) -> bytes:
    doc = Document()
    for line in lines:
        doc.add_paragraph(line)
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


def make_pdf(pages: list[list[str]] | None = None) -> bytes:
    """A minimal valid PDF with real text (Helvetica), one list of lines per page."""
    pages = pages if pages is not None else [RESUME_LINES]
    objects: list[bytes] = []

    def add(body: bytes) -> int:
        objects.append(body)
        return len(objects)

    catalog = add(b"")  # placeholder, filled below
    pages_obj = add(b"")
    font = add(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
    kids: list[int] = []
    for lines in pages:
        ops = ["BT", "/F1 10 Tf", "14 TL", "50 780 Td"]
        for line in lines:
            safe = line.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
            ops.append(f"({safe}) Tj T*")
        ops.append("ET")
        stream = "\n".join(ops).encode("latin-1")
        content = add(b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream")
        page = add(
            b"<< /Type /Page /Parent %d 0 R /MediaBox [0 0 612 842] "
            b"/Resources << /Font << /F1 %d 0 R >> >> /Contents %d 0 R >>"
            % (pages_obj, font, content)
        )
        kids.append(page)
    objects[catalog - 1] = b"<< /Type /Catalog /Pages %d 0 R >>" % pages_obj
    objects[pages_obj - 1] = b"<< /Type /Pages /Kids [%s] /Count %d >>" % (
        b" ".join(b"%d 0 R" % k for k in kids),
        len(kids),
    )

    out = io.BytesIO()
    out.write(b"%PDF-1.4\n")
    offsets = []
    for i, body in enumerate(objects, start=1):
        offsets.append(out.tell())
        out.write(b"%d 0 obj\n" % i + body + b"\nendobj\n")
    xref = out.tell()
    out.write(b"xref\n0 %d\n0000000000 65535 f \n" % (len(objects) + 1))
    for off in offsets:
        out.write(b"%010d 00000 n \n" % off)
    out.write(
        b"trailer\n<< /Size %d /Root %d 0 R >>\nstartxref\n%d\n%%%%EOF\n"
        % (len(objects) + 1, catalog, xref)
    )
    return out.getvalue()


def parsed_resume_json(**overrides: Any) -> dict[str, Any]:
    """What a well-behaved parser returns for RESUME_LINES (shape of the v1 schema)."""
    data: dict[str, Any] = {
        "name": "Ada Lovelace",
        "contact": {
            "email": "ada@example.com",
            "phone": "+1 555 010 0199",
            "location": "London, UK",
            "links": [],
        },
        "summary": "Backend engineer focused on Python APIs and data pipelines.",
        "total_years_experience": 9,  # wrong on purpose: dates say ~5.6
        "skills": [
            {"name": "python", "category": "language", "proficiency": "expert", "evidence": "x"},
            {"name": "FastAPI", "category": "framework", "proficiency": "advanced", "evidence": ""},
            {"name": "k8s", "category": "tool", "proficiency": "beginner", "evidence": ""},
            {"name": "JS", "category": "language", "proficiency": "intermediate", "evidence": ""},
            {"name": "Python", "category": "language", "proficiency": "advanced", "evidence": ""},
            {"name": "postgres", "category": "database", "proficiency": "advanced", "evidence": ""},
        ],
        "work_history": [
            {
                "title": "Senior Software Engineer",
                "company": "Analytical Engines Ltd",
                "location": "",
                "start": "2021-03",
                "end": "present",
                "bullets": ["Built FastAPI services handling 2M requests per day on AWS."],
            },
            {
                "title": "Software Engineer",
                "company": "Difference Labs",
                "location": "",
                "start": "2018-06",
                "end": "2021-02",
                "bullets": ["Developed Django REST APIs and React dashboards for 30 clients."],
            },
            {
                "title": "Software Engineering Intern",
                "company": "Babbage & Co",
                "location": "",
                "start": "2017-06",
                "end": "2017-09",
                "bullets": [],
            },
        ],
        "education": [
            {
                "institution": "University of London",
                "degree": "BSc",
                "field": "Computer Science",
                "start": "2014",
                "end": "2018",
                "gpa": "",
            }
        ],
        "projects": [],
        "certifications": [],
        "preferred_roles": ["Backend Engineer", "Senior Python Developer"],
        "seniority": "senior",
    }
    data.update(overrides)
    return data
