import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

type FormFieldProps = React.ComponentProps<typeof Input> & {
  label: string;
  error?: string;
  hint?: React.ReactNode;
};

export function FormField({ label, error, hint, id, ...inputProps }: FormFieldProps) {
  const fieldId = id ?? inputProps.name;
  return (
    <div className="grid gap-2">
      <div className="flex items-center justify-between">
        <Label htmlFor={fieldId}>{label}</Label>
        {hint}
      </div>
      <Input id={fieldId} aria-invalid={error ? true : undefined} {...inputProps} />
      {error && <p className="text-destructive text-sm">{error}</p>}
    </div>
  );
}
