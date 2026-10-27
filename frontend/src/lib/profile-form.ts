import type { ResumeProfile, SkillCategory, SkillProficiency } from "@/lib/api/generated/model";

/** Editor-friendly shape: lists of lines/tags become plain strings in the form. */
export interface ProfileFormValues {
  name: string;
  email: string;
  phone: string;
  location: string;
  summary: string;
  preferredRoles: string; // comma-separated
  skills: {
    name: string;
    category: SkillCategory;
    proficiency: SkillProficiency;
    evidence: string;
  }[];
  work: {
    title: string;
    company: string;
    location: string;
    start: string;
    end: string;
    bullets: string; // one per line
  }[];
  education: {
    institution: string;
    degree: string;
    field: string;
    start: string;
    end: string;
    gpa: string;
  }[];
  projects: {
    name: string;
    description: string;
    technologies: string; // comma-separated
    url: string;
    bullets: string; // one per line
  }[];
  certifications: { name: string; issuer: string; date: string }[];
}

export const SKILL_CATEGORIES: SkillCategory[] = [
  "language",
  "framework",
  "tool",
  "cloud",
  "database",
  "domain",
  "soft",
  "other",
];
export const PROFICIENCIES: SkillProficiency[] = ["beginner", "intermediate", "advanced", "expert"];

const lines = (text: string) =>
  text
    .split("\n")
    .map((l) => l.replace(/^\s*[-•*]\s*/, "").trim())
    .filter(Boolean);
const tags = (text: string) =>
  text
    .split(",")
    .map((t) => t.trim())
    .filter(Boolean);
const orNull = (text: string) => text.trim() || null;

export function toFormValues(p: ResumeProfile): ProfileFormValues {
  return {
    name: p.name ?? "",
    email: p.contact?.email ?? "",
    phone: p.contact?.phone ?? "",
    location: p.contact?.location ?? "",
    summary: p.summary ?? "",
    preferredRoles: (p.preferred_roles ?? []).join(", "),
    skills: (p.skills ?? []).map((s) => ({
      name: s.name,
      category: s.category ?? "other",
      proficiency: s.proficiency ?? "intermediate",
      evidence: s.evidence ?? "",
    })),
    work: (p.work_history ?? []).map((w) => ({
      title: w.title,
      company: w.company,
      location: w.location ?? "",
      start: w.start ?? "",
      end: w.end ?? "",
      bullets: (w.bullets ?? []).join("\n"),
    })),
    education: (p.education ?? []).map((e) => ({
      institution: e.institution,
      degree: e.degree ?? "",
      field: e.field ?? "",
      start: e.start ?? "",
      end: e.end ?? "",
      gpa: e.gpa ?? "",
    })),
    projects: (p.projects ?? []).map((pr) => ({
      name: pr.name,
      description: pr.description ?? "",
      technologies: (pr.technologies ?? []).join(", "),
      url: pr.url ?? "",
      bullets: (pr.bullets ?? []).join("\n"),
    })),
    certifications: (p.certifications ?? []).map((c) => ({
      name: c.name,
      issuer: c.issuer ?? "",
      date: c.date ?? "",
    })),
  };
}

/** Back to the API shape. Fields the editor doesn't show (links, seniority) are kept. */
export function toProfile(v: ProfileFormValues, original: ResumeProfile): ResumeProfile {
  return {
    ...original,
    name: v.name.trim(),
    contact: {
      ...original.contact,
      email: orNull(v.email),
      phone: orNull(v.phone),
      location: orNull(v.location),
    },
    summary: v.summary.trim(),
    preferred_roles: tags(v.preferredRoles),
    skills: v.skills
      .filter((s) => s.name.trim())
      .map((s) => ({
        name: s.name.trim(),
        category: s.category,
        proficiency: s.proficiency,
        evidence: orNull(s.evidence),
      })),
    work_history: v.work
      .filter((w) => w.title.trim() || w.company.trim())
      .map((w) => ({
        title: w.title.trim(),
        company: w.company.trim(),
        location: orNull(w.location),
        start: orNull(w.start),
        end: orNull(w.end),
        bullets: lines(w.bullets),
      })),
    education: v.education
      .filter((e) => e.institution.trim())
      .map((e) => ({
        institution: e.institution.trim(),
        degree: orNull(e.degree),
        field: orNull(e.field),
        start: orNull(e.start),
        end: orNull(e.end),
        gpa: orNull(e.gpa),
      })),
    projects: v.projects
      .filter((p) => p.name.trim())
      .map((p) => ({
        name: p.name.trim(),
        description: orNull(p.description),
        technologies: tags(p.technologies),
        url: orNull(p.url),
        bullets: lines(p.bullets),
      })),
    certifications: v.certifications
      .filter((c) => c.name.trim())
      .map((c) => ({ name: c.name.trim(), issuer: orNull(c.issuer), date: orNull(c.date) })),
  };
}

/** YYYY, YYYY-MM, "present" or empty. Mirrors the backend's date rule. */
export function isValidDate(value: string, allowPresent: boolean) {
  const v = value.trim().toLowerCase();
  if (!v) return true;
  if (allowPresent && v === "present") return true;
  return /^\d{4}(-(0[1-9]|1[0-2]))?$/.test(v);
}
