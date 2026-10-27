"""Skill name canonicalization so "JS", "javascript" and "Java Script" compare equal."""

from __future__ import annotations

import re

# Lowercase alias -> canonical display name. Extend freely; keys must be lowercase.
_ALIASES: dict[str, str] = {
    "js": "JavaScript",
    "javascript": "JavaScript",
    "java script": "JavaScript",
    "ecmascript": "JavaScript",
    "ts": "TypeScript",
    "typescript": "TypeScript",
    "py": "Python",
    "python": "Python",
    "python3": "Python",
    "golang": "Go",
    "go": "Go",
    "c#": "C#",
    "csharp": "C#",
    "c++": "C++",
    "cpp": "C++",
    "node": "Node.js",
    "nodejs": "Node.js",
    "node.js": "Node.js",
    "react": "React",
    "reactjs": "React",
    "react.js": "React",
    "next": "Next.js",
    "nextjs": "Next.js",
    "next.js": "Next.js",
    "vue": "Vue.js",
    "vuejs": "Vue.js",
    "vue.js": "Vue.js",
    "angularjs": "Angular",
    "angular": "Angular",
    "express": "Express",
    "expressjs": "Express",
    "django": "Django",
    "flask": "Flask",
    "fastapi": "FastAPI",
    "spring boot": "Spring Boot",
    "springboot": "Spring Boot",
    ".net": ".NET",
    "dotnet": ".NET",
    "postgres": "PostgreSQL",
    "postgresql": "PostgreSQL",
    "psql": "PostgreSQL",
    "mysql": "MySQL",
    "mongo": "MongoDB",
    "mongodb": "MongoDB",
    "redis": "Redis",
    "sql": "SQL",
    "nosql": "NoSQL",
    "k8s": "Kubernetes",
    "kubernetes": "Kubernetes",
    "docker": "Docker",
    "aws": "AWS",
    "amazon web services": "AWS",
    "gcp": "Google Cloud",
    "google cloud platform": "Google Cloud",
    "google cloud": "Google Cloud",
    "azure": "Azure",
    "microsoft azure": "Azure",
    "ci/cd": "CI/CD",
    "cicd": "CI/CD",
    "git": "Git",
    "github": "GitHub",
    "ml": "Machine Learning",
    "machine learning": "Machine Learning",
    "dl": "Deep Learning",
    "deep learning": "Deep Learning",
    "nlp": "NLP",
    "llm": "LLMs",
    "llms": "LLMs",
    "tensorflow": "TensorFlow",
    "pytorch": "PyTorch",
    "scikit-learn": "scikit-learn",
    "sklearn": "scikit-learn",
    "pandas": "pandas",
    "numpy": "NumPy",
    "rest": "REST APIs",
    "rest api": "REST APIs",
    "rest apis": "REST APIs",
    "restful apis": "REST APIs",
    "graphql": "GraphQL",
    "html": "HTML",
    "html5": "HTML",
    "css": "CSS",
    "css3": "CSS",
    "tailwind": "Tailwind CSS",
    "tailwindcss": "Tailwind CSS",
    "tailwind css": "Tailwind CSS",
    "linux": "Linux",
    "terraform": "Terraform",
}

_SPACES = re.compile(r"\s+")


def canonical_skill(name: str) -> str:
    cleaned = _SPACES.sub(" ", name.strip().strip(".,;:"))
    if not cleaned:
        return ""
    key = cleaned.lower()
    if key in _ALIASES:
        return _ALIASES[key]
    # Keep the user's casing for unknown skills, but don't shout lowercase words.
    return cleaned if any(c.isupper() for c in cleaned) else cleaned[:1].upper() + cleaned[1:]


def skill_key(name: str) -> str:
    """Comparison key: canonical name, lowercased."""
    return canonical_skill(name).lower()


def unique_skills(names: list[str]) -> list[str]:
    seen: dict[str, str] = {}
    for name in names:
        canon = canonical_skill(name)
        if canon and canon.lower() not in seen:
            seen[canon.lower()] = canon
    return list(seen.values())
