"use client";

import { useQueryClient } from "@tanstack/react-query";
import { Plus, Trash2, X } from "lucide-react";
import { useState } from "react";
import { useFieldArray, useForm, type UseFormRegister } from "react-hook-form";
import { toast } from "sonner";

import { FormField } from "@/components/auth/form-field";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import type { ResumeOut } from "@/lib/api/generated/model";
import {
  getResumesGetActiveResumeQueryKey,
  getResumesGetResumeQueryKey,
  getResumesListResumesQueryKey,
  useResumesUpdateProfile,
} from "@/lib/api/generated/resumes/resumes";
import { getUsersGetMeQueryKey } from "@/lib/api/generated/users/users";
import { errorMessage } from "@/lib/forms";
import {
  isValidDate,
  PROFICIENCIES,
  SKILL_CATEGORIES,
  toFormValues,
  toProfile,
  type ProfileFormValues,
} from "@/lib/profile-form";

const selectClass = "border-input bg-background h-9 rounded-md border px-2 text-sm capitalize";

function Section({
  title,
  description,
  onAdd,
  addLabel,
  children,
}: {
  title: string;
  description?: string;
  onAdd?: () => void;
  addLabel?: string;
  children: React.ReactNode;
}) {
  return (
    <Card>
      <CardHeader className="flex flex-row items-start justify-between gap-4">
        <div className="grid gap-1">
          <CardTitle className="text-base">{title}</CardTitle>
          {description && <CardDescription>{description}</CardDescription>}
        </div>
        {onAdd && (
          <Button type="button" variant="outline" size="sm" onClick={onAdd}>
            <Plus className="size-4" /> {addLabel}
          </Button>
        )}
      </CardHeader>
      <CardContent className="grid gap-4">{children}</CardContent>
    </Card>
  );
}

function RemoveButton({ onClick, label }: { onClick: () => void; label: string }) {
  return (
    <Button type="button" variant="ghost" size="icon" onClick={onClick} aria-label={label}>
      <Trash2 className="size-4" />
    </Button>
  );
}

function TextArea({
  label,
  name,
  register,
  rows = 3,
  hint,
}: {
  label: string;
  name: Parameters<UseFormRegister<ProfileFormValues>>[0];
  register: UseFormRegister<ProfileFormValues>;
  rows?: number;
  hint?: string;
}) {
  return (
    <div className="grid gap-2">
      <Label htmlFor={name}>{label}</Label>
      <Textarea id={name} rows={rows} {...register(name)} />
      {hint && <p className="text-muted-foreground text-xs">{hint}</p>}
    </div>
  );
}

export function ProfileEditor({
  resume,
  onSaved,
  saveLabel = "Save profile",
}: {
  resume: ResumeOut;
  onSaved?: (resume: ResumeOut) => void;
  saveLabel?: string;
}) {
  const queryClient = useQueryClient();
  const original = resume.profile ?? {};
  const form = useForm<ProfileFormValues>({ defaultValues: toFormValues(original) });
  const { register, control, handleSubmit, formState } = form;
  const skills = useFieldArray({ control, name: "skills" });
  const work = useFieldArray({ control, name: "work" });
  const education = useFieldArray({ control, name: "education" });
  const projects = useFieldArray({ control, name: "projects" });
  const certifications = useFieldArray({ control, name: "certifications" });
  const [newSkill, setNewSkill] = useState("");
  const update = useResumesUpdateProfile();

  const addSkill = () => {
    const name = newSkill.trim();
    if (!name) return;
    const exists = form
      .getValues("skills")
      .some((s) => s.name.toLowerCase() === name.toLowerCase());
    if (!exists)
      skills.append({ name, category: "other", proficiency: "intermediate", evidence: "" });
    setNewSkill("");
  };

  const onSubmit = handleSubmit((values) => {
    const badDate = values.work.find(
      (w) => !isValidDate(w.start, false) || !isValidDate(w.end, true),
    );
    if (badDate) {
      toast.error(
        `Check the dates for “${badDate.title || badDate.company}”: use YYYY or YYYY-MM (or "present").`,
      );
      return;
    }
    update.mutate(
      { resumeId: resume.id, data: toProfile(values, original) },
      {
        onSuccess: (saved) => {
          queryClient.setQueryData(getResumesGetResumeQueryKey(saved.id), saved);
          queryClient.invalidateQueries({ queryKey: getResumesGetActiveResumeQueryKey() });
          queryClient.invalidateQueries({ queryKey: getResumesListResumesQueryKey() });
          queryClient.invalidateQueries({ queryKey: getUsersGetMeQueryKey() });
          form.reset(toFormValues(saved.profile ?? {}));
          toast.success("Profile saved");
          onSaved?.(saved);
        },
        onError: (e) => toast.error(errorMessage(e)),
      },
    );
  });

  return (
    <form onSubmit={onSubmit} className="grid gap-6" noValidate>
      <div className="flex flex-wrap items-center gap-2 text-sm">
        {resume.total_years_experience != null && (
          <Badge variant="secondary">{resume.total_years_experience} yrs experience</Badge>
        )}
        {resume.seniority && (
          <Badge variant="secondary" className="capitalize">
            {resume.seniority}
          </Badge>
        )}
        <Badge variant="outline">{resume.skills_count} skills</Badge>
        <span className="text-muted-foreground">
          Years and seniority are recalculated from your job dates when you save.
        </span>
      </div>

      <Section title="Basics" description="Contact details are never sent to the AI for scoring.">
        <div className="grid gap-4 sm:grid-cols-2">
          <FormField label="Full name" {...register("name")} />
          <FormField label="Email" type="email" {...register("email")} />
          <FormField label="Phone" {...register("phone")} />
          <FormField label="Location" {...register("location")} />
        </div>
        <TextArea label="Summary" name="summary" register={register} rows={3} />
        <FormField
          label="Target roles"
          placeholder="Backend Engineer, Python Developer"
          hint={<span className="text-muted-foreground text-xs">Comma-separated</span>}
          {...register("preferredRoles")}
        />
      </Section>

      <Section
        title={`Skills (${skills.fields.length})`}
        description="Matching compares these against each job's requirements. Remove anything you wouldn't want to be interviewed on."
      >
        <div className="flex gap-2">
          <Input
            value={newSkill}
            placeholder="Add a skill, e.g. Terraform"
            aria-label="New skill"
            onChange={(e) => setNewSkill(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") {
                e.preventDefault();
                addSkill();
              }
            }}
          />
          <Button type="button" variant="outline" onClick={addSkill}>
            <Plus className="size-4" /> Add
          </Button>
        </div>
        {skills.fields.length === 0 ? (
          <p className="text-muted-foreground text-sm">No skills yet.</p>
        ) : (
          <ul className="grid gap-2">
            {skills.fields.map((field, i) => (
              <li
                key={field.id}
                className="grid grid-cols-[1fr_auto] items-center gap-2 sm:grid-cols-[1fr_9rem_9rem_auto]"
              >
                <Input aria-label="Skill name" {...register(`skills.${i}.name`)} />
                <select
                  aria-label="Category"
                  className={`${selectClass} hidden sm:block`}
                  {...register(`skills.${i}.category`)}
                >
                  {SKILL_CATEGORIES.map((c) => (
                    <option key={c} value={c}>
                      {c}
                    </option>
                  ))}
                </select>
                <select
                  aria-label="Proficiency"
                  className={`${selectClass} hidden sm:block`}
                  {...register(`skills.${i}.proficiency`)}
                >
                  {PROFICIENCIES.map((p) => (
                    <option key={p} value={p}>
                      {p}
                    </option>
                  ))}
                </select>
                <Button
                  type="button"
                  variant="ghost"
                  size="icon"
                  aria-label={`Remove ${field.name}`}
                  onClick={() => skills.remove(i)}
                >
                  <X className="size-4" />
                </Button>
              </li>
            ))}
          </ul>
        )}
      </Section>

      <Section
        title="Experience"
        description="Newest first. Dates as YYYY-MM (or YYYY); use “present” for your current role."
        addLabel="Add role"
        onAdd={() =>
          work.prepend({ title: "", company: "", location: "", start: "", end: "", bullets: "" })
        }
      >
        {work.fields.length === 0 && (
          <p className="text-muted-foreground text-sm">No work history yet.</p>
        )}
        {work.fields.map((field, i) => (
          <div key={field.id} className="grid gap-3 rounded-lg border p-4">
            <div className="flex items-start gap-2">
              <div className="grid flex-1 gap-3 sm:grid-cols-2">
                <FormField label="Title" {...register(`work.${i}.title`)} />
                <FormField label="Company" {...register(`work.${i}.company`)} />
                <FormField label="Location" {...register(`work.${i}.location`)} />
                <div className="grid grid-cols-2 gap-3">
                  <FormField label="Start" placeholder="2021-03" {...register(`work.${i}.start`)} />
                  <FormField label="End" placeholder="present" {...register(`work.${i}.end`)} />
                </div>
              </div>
              <RemoveButton label="Remove role" onClick={() => work.remove(i)} />
            </div>
            <TextArea
              label="Achievements"
              name={`work.${i}.bullets`}
              register={register}
              rows={4}
              hint="One per line. These are quoted when tailoring applications, so keep them accurate."
            />
          </div>
        ))}
      </Section>

      <Section
        title="Education"
        addLabel="Add"
        onAdd={() =>
          education.append({ institution: "", degree: "", field: "", start: "", end: "", gpa: "" })
        }
      >
        {education.fields.length === 0 && (
          <p className="text-muted-foreground text-sm">No education listed.</p>
        )}
        {education.fields.map((field, i) => (
          <div key={field.id} className="flex items-start gap-2 rounded-lg border p-4">
            <div className="grid flex-1 gap-3 sm:grid-cols-3">
              <FormField label="Institution" {...register(`education.${i}.institution`)} />
              <FormField label="Degree" {...register(`education.${i}.degree`)} />
              <FormField label="Field" {...register(`education.${i}.field`)} />
              <FormField label="Start" {...register(`education.${i}.start`)} />
              <FormField label="End" {...register(`education.${i}.end`)} />
              <FormField label="GPA" {...register(`education.${i}.gpa`)} />
            </div>
            <RemoveButton label="Remove education" onClick={() => education.remove(i)} />
          </div>
        ))}
      </Section>

      <Section
        title="Projects"
        addLabel="Add"
        onAdd={() =>
          projects.append({ name: "", description: "", technologies: "", url: "", bullets: "" })
        }
      >
        {projects.fields.length === 0 && (
          <p className="text-muted-foreground text-sm">No projects listed.</p>
        )}
        {projects.fields.map((field, i) => (
          <div key={field.id} className="grid gap-3 rounded-lg border p-4">
            <div className="flex items-start gap-2">
              <div className="grid flex-1 gap-3 sm:grid-cols-2">
                <FormField label="Name" {...register(`projects.${i}.name`)} />
                <FormField label="URL" {...register(`projects.${i}.url`)} />
              </div>
              <RemoveButton label="Remove project" onClick={() => projects.remove(i)} />
            </div>
            <FormField
              label="Technologies"
              placeholder="Python, FastAPI, PostgreSQL"
              {...register(`projects.${i}.technologies`)}
            />
            <TextArea label="Description" name={`projects.${i}.description`} register={register} />
            <TextArea
              label="Highlights"
              name={`projects.${i}.bullets`}
              register={register}
              hint="One per line."
            />
          </div>
        ))}
      </Section>

      <Section
        title="Certifications"
        addLabel="Add"
        onAdd={() => certifications.append({ name: "", issuer: "", date: "" })}
      >
        {certifications.fields.length === 0 && (
          <p className="text-muted-foreground text-sm">No certifications listed.</p>
        )}
        {certifications.fields.map((field, i) => (
          <div key={field.id} className="flex items-start gap-2">
            <div className="grid flex-1 gap-3 sm:grid-cols-3">
              <FormField label="Name" {...register(`certifications.${i}.name`)} />
              <FormField label="Issuer" {...register(`certifications.${i}.issuer`)} />
              <FormField label="Date" {...register(`certifications.${i}.date`)} />
            </div>
            <RemoveButton label="Remove certification" onClick={() => certifications.remove(i)} />
          </div>
        ))}
      </Section>

      <div className="bg-background/90 sticky bottom-0 -mx-4 flex items-center justify-end gap-3 border-t px-4 py-3 backdrop-blur md:-mx-8 md:px-8">
        {formState.isDirty && (
          <span className="text-muted-foreground text-sm">You have unsaved changes</span>
        )}
        <Button type="submit" disabled={update.isPending}>
          {update.isPending ? "Saving…" : saveLabel}
        </Button>
      </div>
    </form>
  );
}
